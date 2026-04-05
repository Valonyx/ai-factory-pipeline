"""
AI Factory Pipeline v5.6 — Pipeline Orchestrator

Implements:
  - §2.7.1 DAG construction (S0→S1→…→S8)
  - §2.7.2 pipeline_node decorator (legal hooks + snapshots)
  - §2.7.1 Conditional routing (S5→S3 retry, S7→S6 redeploy)
  - §2.7.1 halt_handler_node
  - run_pipeline() — main entry point

Wires all layers: Core, Telegram, Pipeline, Integrations,
Design, Monitoring, War Room, Legal, Delivery.

Spec Authority: v5.6 §2.7.1, §2.7.2, §4.0
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Optional, Callable, Awaitable

from factory.core.state import PipelineState, Stage, AutonomyMode
from factory.legal.checks import legal_check_hook
from factory.monitoring.budget_governor import (
    budget_governor, BudgetExhaustedError, BudgetIntakeBlockedError,
)
from factory.monitoring.cost_tracker import cost_tracker
from factory.monitoring.health import HeartbeatMonitor
from factory.war_room.war_room import (
    war_room_escalate, should_retry, increment_retry,
)
from factory.telegram.notifications import send_telegram_message

logger = logging.getLogger("factory.orchestrator")


def pipeline_node(stage: Stage):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(state: PipelineState) -> PipelineState:
            await legal_check_hook(state, stage, "pre")
            if state.legal_halt:
                _transition_to(state, Stage.HALTED)
                return state
            _transition_to(state, stage)
            logger.info(f"[{state.project_id}] Stage {stage.value} START")
            try:
                state = await fn(state)
            except BudgetExhaustedError as e:
                logger.critical(f"[{state.project_id}] BLACK tier halt: {e}")
                _transition_to(state, Stage.HALTED)
                state.project_metadata["halt_reason"] = "budget_exhausted"
                return state
            except BudgetIntakeBlockedError as e:
                logger.warning(f"[{state.project_id}] RED tier intake blocked: {e}")
                _transition_to(state, Stage.HALTED)
                state.project_metadata["halt_reason"] = "intake_blocked"
                return state
            except Exception as e:
                logger.error(f"[{state.project_id}] Stage {stage.value} ERROR: {e}", exc_info=True)
                state.project_metadata["last_error"] = str(e)[:500]
            await legal_check_hook(state, stage, "post")
            if state.legal_halt:
                _transition_to(state, Stage.HALTED)
                return state
            await _persist_snapshot(state)
            logger.info(f"[{state.project_id}] Stage {stage.value} COMPLETE")
            return state
        return wrapper
    return decorator


def _transition_to(state: PipelineState, stage: Stage) -> None:
    prev = state.current_stage
    state.current_stage = stage
    state.stage_history.append({
        "stage": stage.value,
        "from": prev.value,
        "to": stage.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def _persist_snapshot(state: PipelineState) -> None:
    state.snapshot_id = (state.snapshot_id or 0) + 1
    state.snapshot_count = (getattr(state, "snapshot_count", 0) or 0) + 1
    logger.debug(f"[{state.project_id}] Snapshot #{state.snapshot_id} at {state.current_stage.value}")


# Import stage node functions directly (already decorated in their modules)
from factory.pipeline.s0_intake import s0_intake_node
from factory.pipeline.s1_legal import s1_legal_node
from factory.pipeline.s2_blueprint import s2_blueprint_node
from factory.pipeline.s3_codegen import s3_codegen_node
from factory.pipeline.s4_build import s4_build_node
from factory.pipeline.s5_test import s5_test_node
from factory.pipeline.s6_deploy import s6_deploy_node
from factory.pipeline.s7_verify import s7_verify_node
from factory.pipeline.s8_handoff import s8_handoff_node


async def halt_handler_node(state: PipelineState) -> PipelineState:
    _transition_to(state, Stage.HALTED)
    reason = (
        state.legal_halt_reason
        or state.project_metadata.get("halt_reason", "unknown")
        or state.project_metadata.get("last_error", "unknown")
    )
    logger.warning(f"[{state.project_id}] Pipeline HALTED: {reason}")
    await send_telegram_message(
        state.operator_id,
        f"⛔ Pipeline halted at {state.current_stage.value}\n\n"
        f"Reason: {reason}\n\n"
        f"Options:\n"
        f"  /continue — Resume after resolving\n"
        f"  /force_continue — Override and proceed\n"
        f"  /cancel — Cancel this project",
    )
    return state


def route_after_test(state: PipelineState) -> str:
    if state.current_stage == Stage.HALTED:
        return "halt"
    # Check s5_output first (direct stage output), then project_metadata fallback
    s5 = state.s5_output or {}
    test_passed = s5.get("all_passed", state.project_metadata.get("tests_passed", False))
    if test_passed:
        return "s6_deploy"
    if should_retry(state):
        increment_retry(state)
        logger.info(f"[{state.project_id}] Test failed → retry cycle {state.retry_count}")
        return "s3_codegen"
    logger.error(f"[{state.project_id}] Test failed, max retries exhausted")
    return "halt"


def route_after_verify(state: PipelineState) -> str:
    if state.current_stage == Stage.HALTED:
        return "halt"
    # Check s7_output first, then project_metadata fallback
    s7 = state.s7_output or {}
    verify_passed = s7.get("verified", state.project_metadata.get("verify_passed", False))
    if verify_passed:
        return "s8_handoff"
    deploy_retries = state.retry_count
    if deploy_retries < 2:
        increment_retry(state)
        return "s6_deploy"
    return "halt"


STAGE_SEQUENCE = [
    ("s0_intake", s0_intake_node),
    ("s1_legal", s1_legal_node),
    ("s2_blueprint", s2_blueprint_node),
    ("s3_codegen", s3_codegen_node),
    ("s4_build", s4_build_node),
    ("s5_test", s5_test_node),
    ("s6_deploy", s6_deploy_node),
    ("s7_verify", s7_verify_node),
    ("s8_handoff", s8_handoff_node),
]


async def run_pipeline(state: PipelineState) -> PipelineState:
    logger.info(f"[{state.project_id}] Pipeline START (mode={state.autonomy_mode.value})")
    budget_governor.set_spend_source(cost_tracker.monthly_total_cents)

    for stage_name, stage_fn in STAGE_SEQUENCE[:6]:
        state = await stage_fn(state)
        if state.current_stage == Stage.HALTED:
            return await halt_handler_node(state)

    while True:
        route = route_after_test(state)
        if route == "halt":
            return await halt_handler_node(state)
        if route == "s3_codegen":
            state = await s3_codegen_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            state = await s4_build_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            state = await s5_test_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            continue
        if route == "s6_deploy":
            break

    state = await s6_deploy_node(state)
    if state.current_stage == Stage.HALTED:
        return await halt_handler_node(state)

    state = await s7_verify_node(state)
    if state.current_stage == Stage.HALTED:
        return await halt_handler_node(state)

    while True:
        route = route_after_verify(state)
        if route == "halt":
            return await halt_handler_node(state)
        if route == "s6_deploy":
            state = await s6_deploy_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            state = await s7_verify_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            continue
        if route == "s8_handoff":
            break

    state = await s8_handoff_node(state)
    if state.current_stage == Stage.HALTED:
        return await halt_handler_node(state)

    logger.info(f"[{state.project_id}] Pipeline COMPLETE — cost=${state.total_cost_usd:.2f}")
    return state


async def run_pipeline_from_description(
    description: str,
    operator_id: str = "local-operator",
    autonomy_mode: str = "autopilot",
) -> PipelineState:
    import uuid
    project_id = f"proj-{uuid.uuid4().hex[:8]}"
    state = PipelineState(project_id=project_id, operator_id=operator_id)
    state.autonomy_mode = AutonomyMode(autonomy_mode)
    state.project_metadata["raw_input"] = description
    return await run_pipeline(state)


# ═══════════════════════════════════════════════════════════════════
# STAGE_NODES dict — maps stage name to node function (test export)
# ═══════════════════════════════════════════════════════════════════

from factory.pipeline.graph import _stage_nodes as _graph_stage_nodes

STAGE_NODES: dict = _graph_stage_nodes
