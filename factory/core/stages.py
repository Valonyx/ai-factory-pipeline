"""
AI Factory Pipeline v5.6 — Stage Gate & Pipeline Node Decorators

Implements:
  - §2.1.6 @stage_gate decorator (stage validation + distributed locking)
  - §2.7.2 @pipeline_node decorator (legal hook + snapshot wrapper)
  - §2.1.6 StageExecution idempotency context [C6]
  - Distributed locking via Postgres advisory locks

Spec Authority: v5.6 §2.1.6, §2.7.2
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Callable, Awaitable

from factory.core.state import (
    BudgetExceeded,
    IllegalTransition,
    PipelineState,
    Stage,
    transition_to,
)

logger = logging.getLogger("factory.core.stages")


# ═══════════════════════════════════════════════════════════════════
# §2.1.6 Distributed Locking (Postgres Advisory Locks)
# ═══════════════════════════════════════════════════════════════════


async def acquire_stage_lock(project_id: str, stage: Stage) -> bool:
    """Acquire advisory lock keyed by (project_id, stage).

    Spec: §2.1.6 [C6]
    Uses Postgres advisory locks (existing Supabase — no new dependency).
    Returns True if lock acquired, False if another worker holds it.

    In dry-run / local mode, always returns True.
    """
    try:
        from factory.integrations.supabase import supabase_execute_sql
        lock_key = hash(f"{project_id}:{stage.value}") % (2**31)
        result = await supabase_execute_sql(
            "SELECT pg_try_advisory_lock($1)", [lock_key]
        )
        return bool(result)
    except ImportError:
        # Supabase not yet configured — allow execution (dry-run)
        return True
    except Exception as e:
        logger.warning(f"Lock acquisition failed (allowing execution): {e}")
        return True


async def release_stage_lock(project_id: str, stage: Stage) -> None:
    """Release advisory lock. Auto-releases on connection drop.

    Spec: §2.1.6 [C6]
    """
    try:
        from factory.integrations.supabase import supabase_execute_sql
        lock_key = hash(f"{project_id}:{stage.value}") % (2**31)
        await supabase_execute_sql(
            "SELECT pg_advisory_unlock($1)", [lock_key]
        )
    except (ImportError, Exception) as e:
        logger.debug(f"Lock release skipped: {e}")


# ═══════════════════════════════════════════════════════════════════
# §2.1.6 @stage_gate Decorator
# ═══════════════════════════════════════════════════════════════════


def stage_gate(expected_stage: Stage):
    """Decorator verifying pipeline is in expected stage.

    Spec: §2.1.6
    Checks:
      1. Pipeline is at expected stage
      2. No legal halt active
      3. No circuit breaker triggered (without authorization)
      4. Advisory lock acquired (prevents concurrent execution)
      5. Lock released on completion or crash

    Usage:
        @stage_gate(Stage.S0_INTAKE)
        async def s0_intake_node(state: PipelineState) -> PipelineState:
            ...
    """
    def decorator(fn: Callable[..., Awaitable[PipelineState]]):
        @wraps(fn)
        async def wrapper(state: PipelineState, *args, **kwargs) -> PipelineState:
            # Validate stage
            if state.current_stage != expected_stage:
                raise IllegalTransition(
                    f"Expected stage {expected_stage.value}, "
                    f"got {state.current_stage.value}"
                )

            # Check legal halt
            if state.legal_halt:
                raise IllegalTransition(
                    f"Legal halt active: {state.legal_halt_reason}"
                )

            # Check circuit breaker
            if state.circuit_breaker_triggered:
                raise BudgetExceeded(
                    f"Circuit breaker triggered. "
                    f"Phase costs: {state.phase_costs}"
                )

            # Acquire distributed lock
            if not await acquire_stage_lock(state.project_id, expected_stage):
                logger.warning(
                    f"Stage {expected_stage.value} already running for "
                    f"{state.project_id}, skipping duplicate"
                )
                return state

            try:
                return await fn(state, *args, **kwargs)
            finally:
                await release_stage_lock(state.project_id, expected_stage)

        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════
# §2.7.2 @pipeline_node Decorator
# ═══════════════════════════════════════════════════════════════════


def pipeline_node(stage: Stage):
    """Decorator wrapping every DAG node with legal checks and snapshots.

    Spec: §2.7.2
    Order of operations:
      1. Pre-stage legal check
      2. Transition to stage
      3. Execute node logic
      4. Post-stage legal check
      5. Persist snapshot (time-travel)

    If legal halt fires at any point, pipeline transitions to HALTED.

    Usage:
        @pipeline_node(Stage.S0_INTAKE)
        async def s0_intake_node(state: PipelineState) -> PipelineState:
            ...
    """
    def decorator(fn: Callable[..., Awaitable[PipelineState]]):
        @wraps(fn)
        async def wrapper(state: PipelineState) -> PipelineState:
            # Pre-stage legal check
            await _legal_check_hook(state, stage, "pre")
            if state.legal_halt:
                transition_to(state, Stage.HALTED)
                return state

            # Transition to stage
            transition_to(state, stage)

            # Execute actual stage logic
            state = await fn(state)

            # Post-stage legal check
            await _legal_check_hook(state, stage, "post")
            if state.legal_halt:
                transition_to(state, Stage.HALTED)
                return state

            # Persist snapshot (time-travel)
            await _persist_snapshot(state)

            return state
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════
# Stub hooks (replaced by real implementations in later parts)
# ═══════════════════════════════════════════════════════════════════


async def _legal_check_hook(
    state: PipelineState, stage: Stage, phase: str,
) -> None:
    """Run legal checks for a given stage/phase.

    Spec: §2.7.3
    Delegates to factory.legal.checks.legal_check_hook().
    """
    try:
        from factory.legal.checks import legal_check_hook
        await legal_check_hook(state, stage, phase)
    except ImportError:
        logger.debug(
            f"[STUB] Legal check skipped: {stage.value}/{phase} "
            f"(legal module not loaded)"
        )


async def _persist_snapshot(state: PipelineState) -> None:
    """Persist state snapshot (triple-write).

    Spec: §2.9.1
    Stub — real implementation in state/persistence.py (Part 11).
    """
    try:
        from factory.state.persistence import persist_state
        await persist_state(state)
    except ImportError:
        logger.debug(
            f"[STUB] Snapshot skipped for {state.project_id} "
            f"(persistence module not loaded)"
        )


# ═══════════════════════════════════════════════════════════════════
# DAG Routing Functions (§2.7.1)
# ═══════════════════════════════════════════════════════════════════


def route_after_test(state: PipelineState) -> str:
    """Route after S5 Test: pass → S6, fail → S3 retry, fatal → halt.

    Spec: §2.7.1
    """
    if state.legal_halt or state.circuit_breaker_triggered:
        return "halt"

    test_output = state.s6_output or {}
    all_passed = test_output.get("all_passed", False)

    if all_passed:
        return "s7_deploy"

    # Check retry count
    max_retries = 3
    if state.retry_count >= max_retries:
        logger.warning(
            f"[{state.project_id}] Max retries ({max_retries}) reached at S5"
        )
        return "halt"

    state.retry_count += 1
    return "s4_codegen"


def route_after_verify(state: PipelineState) -> str:
    """Route after S7 Verify: pass → S8, fail → S6 redeploy, fatal → halt.

    Spec: §2.7.1
    """
    if state.legal_halt or state.circuit_breaker_triggered:
        return "halt"

    verify_output = state.s8_output or {}
    verified = verify_output.get("verified", False)

    if verified:
        return "s9_handoff"

    max_retries = 2
    if state.retry_count >= max_retries:
        return "halt"

    state.retry_count += 1
    return "s7_deploy"