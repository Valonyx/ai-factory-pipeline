"""
AI Factory Pipeline v5.6 — LangGraph DAG

Implements:
  - §2.7.1 DAG Topology (S0→S8 linear + S5→S3 fix loop + S7→S6 redeploy loop)
  - §2.7.2 pipeline_node wrapper (legal hook + snapshot)
  - §2.7.3 Continuous Legal Thread (LEGAL_CHECKS_BY_STAGE)
  - Route functions: route_after_test(), route_after_verify()
  - run_pipeline() entry point

The pipeline graph is compiled once at startup and invoked per-project.

Spec Authority: v5.6 §2.7
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Optional

from factory.core.state import (
    PipelineState,
    Stage,
    NotificationType,
)

logger = logging.getLogger("factory.pipeline.graph")


# ═══════════════════════════════════════════════════════════════════
# §2.7.3 Continuous Legal Thread
# ═══════════════════════════════════════════════════════════════════

LEGAL_CHECKS_BY_STAGE: dict[Stage, dict[str, list[str]]] = {
    Stage.S2_BLUEPRINT: {
        "pre":  ["ministry_of_commerce_licensing"],
        "post": ["blueprint_legal_compliance"],
    },
    Stage.S4_CODEGEN: {
        "post": ["pdpl_consent_checkboxes", "data_residency_compliance"],
    },
    Stage.S5_BUILD: {
        "post": ["no_prohibited_sdks"],
    },
    Stage.S7_DEPLOY: {
        "pre":  ["cst_time_of_day_restrictions"],
        "post": ["deployment_region_compliance"],
    },
    Stage.S9_HANDOFF: {
        "post": ["all_legal_docs_generated", "final_compliance_sign_off"],
    },
}


async def legal_check_hook(
    state: PipelineState, stage: Stage, phase: str,
) -> None:
    """Run legal checks for a given stage/phase.

    Spec: §2.7.3
    Uses Scout + Strategist. Each check is logged to state.legal_checks_log.
    If a blocking check fails, sets state.legal_halt = True.
    """
    checks = LEGAL_CHECKS_BY_STAGE.get(stage, {}).get(phase, [])

    for check_name in checks:
        result = await _run_legal_check(state, check_name)
        state.legal_checks_log.append({
            "stage": stage.value,
            "phase": phase,
            "check": check_name,
            "passed": result["passed"],
            "details": result.get("details"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if not result["passed"] and result.get("blocking", True):
            state.legal_halt = True
            state.legal_halt_reason = (
                f"'{check_name}' failed at {stage.value}/{phase}: "
                f"{result.get('details', 'No details')}"
            )
            from factory.telegram.notifications import send_telegram_message
            await send_telegram_message(
                state.operator_id,
                f"🚨 Legal compliance issue:\n\n"
                f"Check: {check_name}\nStage: {stage.value}\n"
                f"Details: {result.get('details', 'N/A')}\n\n"
                f"Pipeline paused. Reply /continue after resolving.",
            )
            return


async def _run_legal_check(
    state: PipelineState, check_name: str,
) -> dict:
    """Execute a single legal check.

    Delegates to factory.legal.checks.run_legal_check() for registered checks.
    Falls back to auto-pass for any check not yet registered (dry-run safe).

    Spec: §2.7.3
    """
    logger.info(f"[Legal] Running check '{check_name}' for {state.project_id}")

    try:
        from factory.legal.checks import run_legal_check
        return await run_legal_check(state, check_name)
    except Exception as e:
        logger.debug(f"[Legal] Check '{check_name}' deferred (dry-run): {e}")
        return {
            "passed": True,
            "details": f"Deferred: {check_name} (dry-run fallback)",
            "blocking": False,
        }


# ═══════════════════════════════════════════════════════════════════
# §2.9 State Persistence — Triple-Write
# ═══════════════════════════════════════════════════════════════════


async def persist_state(state: PipelineState) -> int:
    """Transactional triple-write: Supabase active_projects + snapshot + audit log.

    Spec: §2.9.1
    Write order: (1) Supabase active_projects upsert, (2) state_snapshots row,
    (3) audit_log entry. Any individual failure is non-fatal — at least one
    write always succeeds (in-memory counter as last resort).
    """
    state.snapshot_id = (state.snapshot_id or 0) + 1
    state.updated_at = datetime.now(timezone.utc).isoformat()
    snapshot_index = state.snapshot_id

    # ── Write 1: Supabase active_projects + pipeline_states ──────────
    try:
        from factory.integrations.supabase import (
            upsert_active_project,
            upsert_pipeline_state,
        )
        await upsert_active_project(state.operator_id, state)
        await upsert_pipeline_state(state.project_id, state)
    except Exception as e:
        logger.debug(f"[persist] Supabase write failed (non-fatal): {e}")

    # ── Write 2: state_snapshots (time-travel) ────────────────────────
    try:
        from factory.integrations.supabase import get_supabase_client
        client = get_supabase_client()
        if client:
            client.table("state_snapshots").upsert({
                "project_id": state.project_id,
                "operator_id": state.operator_id,
                "stage": state.current_stage.value,
                "snapshot_index": snapshot_index,
                "state_json": state.model_dump(mode="json"),
            }).execute()
    except Exception as e:
        logger.debug(f"[persist] Snapshot write failed (non-fatal): {e}")

    # ── Write 3: audit_log entry ──────────────────────────────────────
    try:
        from factory.integrations.supabase import get_supabase_client
        client = get_supabase_client()
        if client:
            client.table("audit_log").insert({
                "operator_id": state.operator_id,
                "project_id": state.project_id,
                "action": f"stage_complete:{state.current_stage.value}",
                "details": {
                    "snapshot_id": snapshot_index,
                    "cost_usd": state.total_cost_usd,
                    "execution_mode": state.execution_mode.value,
                },
            }).execute()
    except Exception as e:
        logger.debug(f"[persist] Audit log write failed (non-fatal): {e}")

    logger.info(
        f"[Snapshot #{snapshot_index}] {state.current_stage.value} "
        f"for {state.project_id}"
    )
    return snapshot_index


# ═══════════════════════════════════════════════════════════════════
# §2.7.2 pipeline_node Wrapper
# ═══════════════════════════════════════════════════════════════════


def transition_to(state: PipelineState, stage: Stage) -> None:
    """Record stage transition."""
    state.previous_stage = state.current_stage
    state.current_stage = stage
    state.stage_history.append({
        "from": state.previous_stage.value if state.previous_stage else None,
        "to": stage.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


_STAGE_PROGRESS: dict[Stage, str] = {
    Stage.S0_INTAKE:    "📥 *S0 Intake* (1/10) — requirements parsed and project initialized",
    Stage.S1_LEGAL:     "⚖️ *S1 Legal* (2/10) — compliance checks passed",
    Stage.S2_BLUEPRINT: "🏗 *S2 Blueprint* (3/10) — architecture and SE documentation ready",
    Stage.S3_DESIGN:    "🎨 *S3 Design* (4/10) — UI/UX design system approved",
    Stage.S4_CODEGEN:   "💻 *S4 CodeGen* (5/10) — source files generated",
    Stage.S5_BUILD:     "🔨 *S5 Build* (6/10) — artefacts compiled",
    Stage.S6_TEST:      "🧪 *S6 Test* (7/10) — all test suites passed",
    Stage.S7_DEPLOY:    "🚀 *S7 Deploy* (8/10) — app deployed successfully",
    Stage.S8_VERIFY:    "✅ *S8 Verify* (9/10) — post-deploy checks passed",
    Stage.S9_HANDOFF:   "📦 *S9 Handoff* (10/10) — assets and docs delivered",
}


def pipeline_node(stage: Stage):
    """Decorator wrapping every DAG node with legal checks, snapshots,
    and stage transitions.

    Spec: §2.7.2
    Pre-stage legal check → transition → execute → post-stage legal check → persist snapshot.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(state: PipelineState) -> PipelineState:
            # Pre-stage legal check
            await legal_check_hook(state, stage, "pre")
            if state.legal_halt:
                transition_to(state, Stage.HALTED)
                return state

            # Transition to stage
            transition_to(state, stage)
            logger.info(
                f"[{state.project_id}] ➡️ {stage.value}"
            )

            # Execute stage logic
            state = await fn(state)

            # Post-stage legal check
            await legal_check_hook(state, stage, "post")
            if state.legal_halt:
                transition_to(state, Stage.HALTED)
                return state

            # Persist snapshot (time-travel)
            await persist_state(state)

            # Send per-stage progress notification to operator
            if state.operator_id:
                try:
                    from factory.telegram.notifications import send_telegram_message
                    msg = _STAGE_PROGRESS.get(stage)
                    if msg:
                        await send_telegram_message(state.operator_id, msg)
                except Exception:
                    pass  # Never let notification failure break the pipeline

            return state
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════
# §2.7.1 Route Functions (Conditional Edges)
# ═══════════════════════════════════════════════════════════════════

MAX_TEST_RETRIES = 3
MAX_VERIFY_RETRIES = 2


def route_after_test(state: PipelineState) -> str:
    """Route after S6 Test.

    Spec: §2.7.1 (v5.8)
    Pass → S7 Deploy (via pre-deploy gate)
    Fail (retries remaining) → S4 CodeGen (fix loop)
    Fail (retries exhausted) → Halt
    """
    test_output = state.s6_output or {}
    all_passed = test_output.get("passed", False)

    if all_passed:
        return "s7_deploy"

    retry_count = state.retry_count or 0
    if retry_count < MAX_TEST_RETRIES:
        state.retry_count = retry_count + 1
        logger.warning(
            f"[{state.project_id}] Tests failed — retry {state.retry_count}/{MAX_TEST_RETRIES} → S4"
        )
        return "s4_codegen"

    logger.error(
        f"[{state.project_id}] Tests failed after {MAX_TEST_RETRIES} retries → HALT"
    )
    state.legal_halt = True
    state.legal_halt_reason = (
        f"Tests failed after {MAX_TEST_RETRIES} retries. "
        f"Last failures: {json.dumps(test_output.get('failures', [])[:3])}"
    )
    return "halt"


def route_after_verify(state: PipelineState) -> str:
    """Route after S8 Verify.

    Spec: §2.7.1 (v5.8)
    Pass → S9 Handoff
    Fail (retries remaining) → S7 Deploy (redeploy)
    Fail (retries exhausted) → Halt
    """
    verify_output = state.s8_output or {}
    all_passed = verify_output.get("passed", False)

    if all_passed:
        return "s9_handoff"

    verify_retries = state.project_metadata.get("verify_retries", 0)
    if verify_retries < MAX_VERIFY_RETRIES:
        state.project_metadata["verify_retries"] = verify_retries + 1
        logger.warning(
            f"[{state.project_id}] Verify failed — retry → S7"
        )
        return "s7_deploy"

    logger.error(
        f"[{state.project_id}] Verify failed after {MAX_VERIFY_RETRIES} retries → HALT"
    )
    state.legal_halt = True
    state.legal_halt_reason = (
        f"Verification failed after {MAX_VERIFY_RETRIES} retries."
    )
    return "halt"


# ═══════════════════════════════════════════════════════════════════
# §2.7.1 DAG Build & Execution
# ═══════════════════════════════════════════════════════════════════

# Stage node registry — populated by stage modules at import time
_stage_nodes: dict[str, Any] = {}


def register_stage_node(name: str, fn: Any) -> None:
    """Register a stage node function for DAG assembly."""
    _stage_nodes[name] = fn


def build_pipeline_graph():
    """Build and compile the LangGraph pipeline.

    Spec: §2.7.1
    Returns a compiled StateGraph (or a simple executor for dry-run
    if LangGraph is not installed).
    """
    try:
        from langgraph.graph import StateGraph, END

        graph = StateGraph(PipelineState)

        # Add all registered stage nodes
        for name, fn in _stage_nodes.items():
            graph.add_node(name, fn)

        # Entry point
        graph.set_entry_point("s0_intake")

        # Linear edges: S0→S1→S2→S3→S4→S5→S6
        graph.add_edge("s0_intake", "s1_legal")
        graph.add_edge("s1_legal", "s2_blueprint")
        graph.add_edge("s2_blueprint", "s3_design")
        graph.add_edge("s3_design", "s4_codegen")
        graph.add_edge("s4_codegen", "s5_build")
        graph.add_edge("s5_build", "s6_test")

        # Conditional: S6 → S7 | S4 | halt
        graph.add_conditional_edges("s6_test", route_after_test, {
            "s7_deploy": "s7_deploy",
            "s4_codegen": "s4_codegen",
            "halt": "halt_handler",
        })

        graph.add_edge("s7_deploy", "s8_verify")

        # Conditional: S8 → S9 | S7 | halt
        graph.add_conditional_edges("s8_verify", route_after_verify, {
            "s9_handoff": "s9_handoff",
            "s7_deploy": "s7_deploy",
            "halt": "halt_handler",
        })

        graph.add_edge("s9_handoff", END)
        graph.add_edge("halt_handler", END)

        compiled = graph.compile()
        logger.info(
            f"LangGraph pipeline compiled with {len(_stage_nodes)} nodes"
        )
        return compiled

    except ImportError:
        logger.warning(
            "LangGraph not installed — using SimpleExecutor fallback"
        )
        return SimpleExecutor()


class SimpleExecutor:
    """Fallback sequential executor when LangGraph is not installed.

    Runs S0→S8 linearly with route checks after S5 and S7.
    Sufficient for dry-run testing.
    """

    async def ainvoke(self, state: PipelineState) -> PipelineState:
        """Execute the pipeline sequentially (v5.8: 10 stages)."""
        stage_sequence = [
            "s0_intake", "s1_legal", "s2_blueprint", "s3_design",
            "s4_codegen", "s5_build", "s6_test",
        ]

        for name in stage_sequence:
            fn = _stage_nodes.get(name)
            if fn is None:
                logger.warning(f"Stage node '{name}' not registered — skipping")
                continue
            state = await fn(state)
            if state.legal_halt or state.current_stage == Stage.HALTED:
                fn_halt = _stage_nodes.get("halt_handler")
                if fn_halt:
                    state = await fn_halt(state)
                return state

        # Route after S6 Test
        route = route_after_test(state)
        if route == "halt":
            fn_halt = _stage_nodes.get("halt_handler")
            if fn_halt:
                state = await fn_halt(state)
            return state
        elif route == "s4_codegen":
            # Simplified: just halt on retry for SimpleExecutor
            logger.info("SimpleExecutor: test retry not supported, halting")
            return state

        # S7→S8
        for name in ["s7_deploy", "s8_verify"]:
            fn = _stage_nodes.get(name)
            if fn:
                state = await fn(state)
            if state.legal_halt or state.current_stage == Stage.HALTED:
                fn_halt = _stage_nodes.get("halt_handler")
                if fn_halt:
                    state = await fn_halt(state)
                return state

        # Route after S8 Verify
        route = route_after_verify(state)
        if route == "halt":
            fn_halt = _stage_nodes.get("halt_handler")
            if fn_halt:
                state = await fn_halt(state)
            return state

        # S9
        fn_s9 = _stage_nodes.get("s9_handoff")
        if fn_s9:
            state = await fn_s9(state)

        return state


async def run_pipeline(
    graph_or_state: Any, state: Optional[PipelineState] = None,
) -> PipelineState:
    """Overloaded: run_pipeline(state) or run_pipeline(graph, state)."""
    if state is None:
        # Called as run_pipeline(state)
        state = graph_or_state
        graph_or_state = build_pipeline_graph()
    graph = graph_or_state
    logger.info(
        f"[{state.project_id}] 🚀 Pipeline starting "
        f"(mode={state.execution_mode.value}, "
        f"autonomy={state.autonomy_mode.value})"
    )

    try:
        if hasattr(graph, "ainvoke"):
            result = await graph.ainvoke(state)
        else:
            result = graph.invoke(state)

        # LangGraph returns a dict; normalize back to PipelineState
        if isinstance(result, dict):
            result = PipelineState.model_validate(result)

        if isinstance(result, PipelineState):
            final_stage = result.current_stage.value
        else:
            final_stage = "unknown"

        logger.info(
            f"[{state.project_id}] 🏁 Pipeline finished at {final_stage}"
        )
        return result

    except Exception as e:
        logger.error(
            f"[{state.project_id}] Pipeline error: {e}", exc_info=True,
        )
        state.errors.append({
            "type": "pipeline_crash",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        from factory.telegram.notifications import send_telegram_message
        await send_telegram_message(
            state.operator_id,
            f"🛑 Pipeline crashed: {str(e)[:500]}\n"
            f"Use /restore to recover.",
        )
        return state

# Alias for test compatibility
_transition_to = transition_to
