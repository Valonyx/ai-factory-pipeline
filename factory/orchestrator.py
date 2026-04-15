"""
AI Factory Pipeline v5.8 — Pipeline Orchestrator

Implements:
  - §2.7.1 DAG construction (S0→S1→…→S8)
  - §2.7.2 pipeline_node decorator (legal hooks + snapshots)
  - §2.7.1 Conditional routing (S5→S3 retry, S7→S6 redeploy)
  - §2.7.1 halt_handler_node
  - run_pipeline() — main entry point

Wires all layers: Core, Telegram, Pipeline, Integrations,
Design, Monitoring, War Room, Legal, Delivery.

Spec Authority: v5.8 §2.7.1, §2.7.2, §4.0
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
from factory.telegram.notifications import send_telegram_message, notify_operator
from factory.core.state import NotificationType

logger = logging.getLogger("factory.orchestrator")

# Stage index for % complete calculation (0-based)
_STAGE_ORDER = [
    "S0_INTAKE", "S1_LEGAL", "S2_BLUEPRINT", "S3_DESIGN",
    "S4_CODEGEN", "S5_BUILD", "S6_TEST", "S7_DEPLOY", "S8_VERIFY", "S9_HANDOFF",
]

_STAGE_ARTIFACTS: dict[str, list[str]] = {
    "S0_INTAKE":    ["app_name", "app_description"],
    "S1_LEGAL":     ["legal_dossier_pdf_path", "overall_risk", "data_classification"],
    "S2_BLUEPRINT": ["blueprint_pdf_path", "selected_stack"],
    "S3_DESIGN":    ["design_type", "mockup_paths"],
    "S4_CODEGEN":   ["github_repo", "files_generated"],
    "S5_BUILD":     ["build_status", "build_artifacts"],
    "S6_TEST":      ["test_summary", "all_passed"],
    "S7_DEPLOY":    ["deployment_url", "deployment_status"],
    "S8_VERIFY":    ["passed", "health_check_url"],
    "S9_HANDOFF":   ["handoff_doc_path", "program_docs"],
}


async def _notify_stage_complete(state: PipelineState, stage_name: str) -> None:
    """Send structured stage-completion progress to the operator.

    Spec: §5.4 — every stage transition notifies operator with
    stage name, % complete, cost, and key artifact links.
    """
    if not state.operator_id:
        return

    idx = next(
        (i for i, s in enumerate(_STAGE_ORDER) if s == stage_name), -1,
    )
    pct = int((idx + 1) / len(_STAGE_ORDER) * 100) if idx >= 0 else 0

    # Build artifact summary line
    artifact_keys = _STAGE_ARTIFACTS.get(stage_name, [])
    output = getattr(state, f"s{idx}_output", None) if idx >= 0 else None
    artifact_parts = []
    for key in artifact_keys:
        val = None
        if output and isinstance(output, dict):
            val = output.get(key)
        if val is None:
            val = state.project_metadata.get(key)
        if val is not None:
            artifact_parts.append(f"{key}: {str(val)[:60]}")

    artifact_line = " | ".join(artifact_parts[:2]) if artifact_parts else ""

    progress_bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    msg = (
        f"[{progress_bar}] {pct}%\n"
        f"Stage {stage_name} complete\n"
        f"Cost: ${state.total_cost_usd:.3f}"
    )
    if artifact_line:
        msg += f"\n{artifact_line}"

    try:
        await notify_operator(state, NotificationType.STAGE_TRANSITION, msg)
    except Exception as e:
        logger.debug(f"Stage progress notification failed (non-fatal): {e}")


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
from factory.pipeline.s3_design import s3_design_node
from factory.pipeline.s4_codegen import s4_codegen_node
from factory.pipeline.s5_build import s5_build_node
from factory.pipeline.s6_test import s6_test_node
from factory.pipeline.s7_deploy import s7_deploy_node
from factory.pipeline.s8_verify import s8_verify_node
from factory.pipeline.s9_handoff import s9_handoff_node


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
    s5 = state.s6_output or {}
    test_passed = s5.get("all_passed", state.project_metadata.get("tests_passed", False))
    if test_passed:
        return "s7_deploy"
    if should_retry(state):
        increment_retry(state)
        logger.info(f"[{state.project_id}] Test failed → retry cycle {state.retry_count}")
        return "s4_codegen"
    logger.error(f"[{state.project_id}] Test failed, max retries exhausted")
    return "halt"


def route_after_verify(state: PipelineState) -> str:
    if state.current_stage == Stage.HALTED:
        return "halt"
    # Check s7_output first, then project_metadata fallback.
    # S7 writes "passed" (not "verified") — check both keys.
    s7 = state.s8_output or {}
    verify_passed = s7.get("passed", s7.get("verified", state.project_metadata.get("verify_passed", False)))
    if verify_passed:
        return "s9_handoff"
    deploy_retries = state.retry_count
    if deploy_retries < 2:
        increment_retry(state)
        return "s7_deploy"
    return "halt"


STAGE_SEQUENCE = [
    ("s0_intake",   s0_intake_node),
    ("s1_legal",    s1_legal_node),
    ("s2_blueprint", s2_blueprint_node),
    ("s3_design",   s3_design_node),   # Design before CodeGen (added in v5.8)
    ("s4_codegen",  s4_codegen_node),
    ("s5_build",    s5_build_node),
    ("s6_test",     s6_test_node),
    ("s7_deploy",   s7_deploy_node),
    ("s8_verify",   s8_verify_node),
    ("s9_handoff",  s9_handoff_node),
]


async def run_pipeline(state: PipelineState) -> PipelineState:
    logger.info(f"[{state.project_id}] Pipeline START (mode={state.autonomy_mode.value})")
    budget_governor.set_spend_source(cost_tracker.monthly_total_cents)

    for stage_name, stage_fn in STAGE_SEQUENCE[:7]:  # S0→S6 linear; S7+ handled by routing
        state = await stage_fn(state)
        if state.current_stage == Stage.HALTED:
            return await halt_handler_node(state)
        # stage_name format: "s0_intake" → "S0_INTAKE"
        await _notify_stage_complete(state, stage_name.upper())

    while True:
        route = route_after_test(state)
        if route == "halt":
            return await halt_handler_node(state)
        if route == "s4_codegen":
            state = await s4_codegen_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            await _notify_stage_complete(state, "S4_CODEGEN")
            state = await s5_build_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            await _notify_stage_complete(state, "S5_BUILD")
            state = await s6_test_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            await _notify_stage_complete(state, "S6_TEST")
            continue
        if route == "s7_deploy":
            break

    state = await s7_deploy_node(state)
    if state.current_stage == Stage.HALTED:
        return await halt_handler_node(state)
    await _notify_stage_complete(state, "S7_DEPLOY")

    state = await s8_verify_node(state)
    if state.current_stage == Stage.HALTED:
        return await halt_handler_node(state)
    await _notify_stage_complete(state, "S8_VERIFY")

    while True:
        route = route_after_verify(state)
        if route == "halt":
            return await halt_handler_node(state)
        if route == "s7_deploy":
            state = await s7_deploy_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            await _notify_stage_complete(state, "S7_DEPLOY")
            state = await s8_verify_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            await _notify_stage_complete(state, "S8_VERIFY")
            continue
        if route == "s9_handoff":
            break

    state = await s9_handoff_node(state)
    if state.current_stage == Stage.HALTED:
        return await halt_handler_node(state)
    await _notify_stage_complete(state, "S9_HANDOFF")

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
