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
import os
import traceback
from datetime import datetime, timezone
from functools import wraps
from typing import Optional, Callable, Awaitable

from factory.core.state import PipelineState, Stage, AutonomyMode
from factory.core.halt import HaltCode, HaltReason, set_halt
from factory.core.quality_gates import QualityGateFailure
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

# Per-stage artifact delivery map: stage_name → list of (state_output_key, caption_label)
_STAGE_ARTIFACTS_DELIVERY: dict[str, list[tuple[str, str]]] = {
    "S1_LEGAL":    [("legal_dossier_pdf_path", "Legal Dossier")],
    "S2_BLUEPRINT":[("blueprint_pdf_path", "Master Blueprint")],
    "S3_DESIGN":   [("design_package_path", "Design Package")],
    "S4_CODEGEN":  [("codegen_archive_path", "Code Archive"), ("github_repo", None)],
    "S5_BUILD":    [("build_log_path", "Build Log"), ("apk_path", "APK"), ("ipa_path", "IPA")],
    "S6_TEST":     [("test_report_path", "Test Report")],
    "S8_VERIFY":   [("verify_report_path", "Verification Report")],
    "S9_HANDOFF":  [("handoff_doc_path", "Handoff Document"), ("program_docs_path", "Program Docs")],
}


async def _notify_stage_complete(state: PipelineState, stage_name: str) -> None:
    """Send structured stage-completion progress to the operator.

    Spec: §5.4 — every stage transition notifies operator with
    stage name, % complete, cost, and key artifact links.
    """
    # 2g — delivery-layer terminal guard: never send notifications for a
    # cancelled pipeline (the task may still be unwinding when this is called).
    if state.pipeline_aborted:
        return
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

    # ── Per-stage file delivery (Issue 3 — comprehensive) ─────────────
    stage_upper = stage_name.upper()
    artifact_specs = _STAGE_ARTIFACTS_DELIVERY.get(stage_upper, [])
    if artifact_specs:
        try:
            from factory.telegram.notifications import send_telegram_file as _send_file
            for key, label in artifact_specs:
                path = None
                if output and isinstance(output, dict):
                    path = output.get(key)
                if not path:
                    path = state.project_metadata.get(key)
                # github_repo key: send as text link, not file
                if key == "github_repo" and path:
                    try:
                        await notify_operator(
                            state, NotificationType.STAGE_TRANSITION,
                            f"📦 Code repository: {path}"
                        )
                    except Exception:
                        pass
                    continue
                if path and __import__("os").path.isfile(str(path)):
                    caption = f"📎 {label or key.replace('_path','').replace('_',' ').title()}"
                    await _send_file(state.operator_id, str(path), caption=caption)
                    logger.info(f"[{state.project_id}] Delivered {key} after {stage_name}")
        except Exception as _e:
            logger.debug(f"Stage file delivery non-fatal: {_e}")


def _contract_bypass_allowed(stage: Stage, state: PipelineState) -> bool:
    """v5.8.15 Issue 50 — stage-success contract bypass.

    Returns True if the current run is one where the "real work" contract
    does NOT apply: mock/dry-run executions, the HALTED terminal stage,
    or MODIFY-mode skips where S2/S4 legitimately no-op.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return True
    if os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes"):
        return True
    if os.getenv("AI_FACTORY_CONTRACT_BYPASS", "").lower() in ("true", "1", "yes"):
        return True
    if state.current_stage == Stage.HALTED:
        return True
    try:
        from factory.core.state import PipelineMode
        if getattr(state, "pipeline_mode", None) == PipelineMode.MODIFY and stage in (
            Stage.S2_BLUEPRINT, Stage.S4_CODEGEN,
        ):
            return True
    except Exception:
        pass
    # Handoff is a pure orchestration step — no provider calls required
    if stage == Stage.S9_HANDOFF:
        return True
    return False


def _merge_stage_counters(state: PipelineState, counters: dict) -> None:
    """Fold contextvar-collected counters into the durable StageMetrics field."""
    try:
        m = state.metrics
        pc = int(counters.get("provider_calls", 0) or 0)
        ap = int(counters.get("artifacts_produced", 0) or 0)
        mw = int(counters.get("mm_writes", 0) or 0)
        if pc:
            m.record_provider_call(pc)
        if ap:
            m.record_artifact(ap)
        if mw:
            m.record_mm_write(mw)
        # Preserve timestamps from context if the model didn't already stamp them
        for src, dst in (
            ("last_provider_call_at", "last_provider_call_at"),
            ("last_artifact_at", "last_artifact_at"),
            ("last_mm_write_at", "last_mm_write_at"),
        ):
            val = counters.get(src)
            if val and not getattr(m, dst, None):
                setattr(m, dst, val)
    except Exception as e:
        logger.debug(f"[metrics] merge failed (non-fatal): {e}")


def pipeline_node(stage: Stage):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(state: PipelineState) -> PipelineState:
            # 2d-iii — fast exit if the pipeline was already aborted or halted
            if state.pipeline_aborted or state.current_stage == Stage.HALTED:
                return state

            # 2d-v — stage-visit cap (infinite-loop guard)
            stage_key = stage.value
            visits = state.stage_visit_counts.get(stage_key, 0) + 1
            state.stage_visit_counts[stage_key] = visits
            if visits > 3:
                set_halt(state, HaltReason(
                    code=HaltCode.UNCAUGHT_EXCEPTION,
                    title="Stage loop detected",
                    detail=(
                        f"Stage {stage_key} has been entered {visits} times "
                        "without operator intervention."
                    ),
                    stage=stage_key,
                    remediation_steps=[
                        "Operator must /cancel or /force_continue",
                        "/restore to a previous snapshot",
                    ],
                ))
                _transition_to(state, Stage.HALTED)
                return state

            await legal_check_hook(state, stage, "pre")
            if state.legal_halt:
                _transition_to(state, Stage.HALTED)
                return state
            _transition_to(state, stage)
            logger.info(f"[{state.project_id}] Stage {stage.value} START")
            # v5.8.15 Issue 50 — install per-stage activity counters
            try:
                state.metrics.reset_stage()
            except Exception:
                pass
            try:
                from factory.core.metrics_context import (
                    start_stage_metrics, clear_stage_metrics,
                )
                _stage_counters = start_stage_metrics()
            except Exception:
                _stage_counters = None
                clear_stage_metrics = lambda: None  # type: ignore
            try:
                state = await fn(state)
            except BudgetExhaustedError as e:
                logger.critical(f"[{state.project_id}] BLACK tier halt: {e}")
                _transition_to(state, Stage.HALTED)
                set_halt(state, HaltReason(
                    code=HaltCode.BUDGET_EXHAUSTED,
                    title="Budget exhausted",
                    detail=f"BLACK tier budget guard triggered: {e}",
                    stage=stage.value,
                    remediation_steps=[
                        "Raise monthly budget with /budget <USD>",
                        "Wait for next billing cycle",
                    ],
                ))
                return state
            except BudgetIntakeBlockedError as e:
                logger.warning(f"[{state.project_id}] RED tier intake blocked: {e}")
                _transition_to(state, Stage.HALTED)
                set_halt(state, HaltReason(
                    code=HaltCode.INTAKE_BLOCKED,
                    title="Intake blocked — budget near cap",
                    detail=f"RED tier intake guard triggered: {e}",
                    stage=stage.value,
                    remediation_steps=[
                        "Raise monthly budget with /budget <USD>",
                        "Cancel stale projects with /cancel",
                    ],
                ))
                return state
            except QualityGateFailure as qgf:
                logger.warning(f"[{state.project_id}] Quality gate failed at {stage.value}: {qgf}")
                set_halt(state, HaltReason(
                    code=HaltCode.QUALITY_GATE_FAILED,
                    title=f"Quality gate failed — {stage.value}",
                    detail=qgf.format_for_telegram()[:600],
                    stage=stage.value,
                    failing_gate=qgf.failed_gates[0].name if qgf.failed_gates else None,
                    remediation_steps=["Retry with /continue", "/cancel"],
                ))
                _transition_to(state, Stage.HALTED)
                return state
            except Exception as e:
                tb_tail = "\n".join(traceback.format_exc().splitlines()[-3:])
                logger.error(f"[{state.project_id}] Stage {stage.value} ERROR: {e}", exc_info=True)
                state.project_metadata["last_error"] = str(e)[:500]
                set_halt(state, HaltReason(
                    code=HaltCode.UNCAUGHT_EXCEPTION,
                    title="Unexpected error",
                    detail=f"{type(e).__name__}: {e}\n{tb_tail}",
                    stage=stage.value,
                    remediation_steps=[
                        "Report this bug to the operator team",
                        f"/restore State_#{state.snapshot_id or 0}",
                        "/cancel",
                    ],
                ))
                _transition_to(state, Stage.HALTED)
                return state
            # v5.8.15 Issue 50 — merge stage counters, detect passive artifacts,
            # and enforce the stage-success contract.
            try:
                if _stage_counters is not None:
                    _merge_stage_counters(state, dict(_stage_counters))
                # Passive artifact detection: if the stage populated any of its
                # declared output fields, count that as an artifact produced.
                decl = _STAGE_ARTIFACTS.get(stage.value, [])
                passive_hits = 0
                for key in decl:
                    val = getattr(state, key, None)
                    if val:
                        passive_hits += 1
                if passive_hits and state.metrics.artifacts_produced_in_stage == 0:
                    state.metrics.record_artifact(passive_hits)
            except Exception as _merr:
                logger.debug(f"[metrics] post-stage merge non-fatal: {_merr}")
            finally:
                try:
                    clear_stage_metrics()
                except Exception:
                    pass

            # Contract check — the stage must show evidence of real work unless
            # an explicit bypass applies (mock/dry-run/HALTED/MODIFY-skip/S9).
            if not _contract_bypass_allowed(stage, state):
                m = state.metrics
                if (
                    m.provider_calls_in_stage == 0
                    and m.artifacts_produced_in_stage == 0
                    and m.mm_writes_in_stage == 0
                ):
                    set_halt(state, HaltReason(
                        code=HaltCode.STAGE_TRIVIAL_COMPLETION,
                        title=f"Stage {stage.value} completed with no real work",
                        detail=(
                            "The stage handler returned success but produced "
                            "zero provider calls, zero artifacts, and zero "
                            "Mother Memory writes. This violates the stage-success "
                            "contract (v5.8.15 Issue 50)."
                        ),
                        stage=stage.value,
                        failing_gate="stage_success_contract",
                        remediation_steps=[
                            "Inspect the stage handler for a silent early-return",
                            "Set AI_PROVIDER=mock or DRY_RUN=true to bypass locally",
                            "/restore to a prior snapshot and /continue",
                        ],
                    ))
                    _transition_to(state, Stage.HALTED)
                    return state

            await legal_check_hook(state, stage, "post")
            if state.legal_halt:
                _transition_to(state, Stage.HALTED)
                return state
            await _persist_snapshot(state)
            logger.info(
                f"[{state.project_id}] Stage {stage.value} COMPLETE "
                f"(provider_calls={state.metrics.provider_calls_in_stage}, "
                f"artifacts={state.metrics.artifacts_produced_in_stage}, "
                f"mm_writes={state.metrics.mm_writes_in_stage})"
            )
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


def _check_deadline(state: PipelineState) -> bool:
    """Return True if the project wall-clock deadline has been exceeded."""
    if not state.pipeline_deadline:
        return False
    return datetime.now(timezone.utc).isoformat() > state.pipeline_deadline


def _abort_check(state: PipelineState) -> bool:
    """Check abort flag and deadline; set halt if deadline exceeded.

    Returns True if the pipeline should stop (either flag set or deadline hit).
    Call at every stage boundary after awaiting a stage function.
    """
    if state.pipeline_aborted:
        return True
    if _check_deadline(state):
        set_halt(state, HaltReason(
            code=HaltCode.PIPELINE_CANCELLED,
            title="Project deadline exceeded",
            detail=(
                f"Project exceeded the 4-hour wall-clock limit "
                f"(deadline: {state.pipeline_deadline})."
            ),
            stage=state.current_stage.value,
            remediation_steps=[
                "/continue to restart from current stage",
                "/cancel",
            ],
        ))
        state.pipeline_aborted = True
        return True
    return False


async def _persist_snapshot(state: PipelineState) -> None:
    state.snapshot_id = (state.snapshot_id or 0) + 1
    state.snapshot_count = (getattr(state, "snapshot_count", 0) or 0) + 1
    logger.debug(f"[{state.project_id}] Snapshot #{state.snapshot_id} at {state.current_stage.value}")
    # Persist to Supabase (non-fatal — snapshot loss is acceptable; pipeline must not halt)
    try:
        from factory.integrations.supabase import upsert_pipeline_state
        await upsert_pipeline_state(state.project_id, state)
    except Exception as _snap_err:
        logger.warning(f"[{state.project_id}] Snapshot #{state.snapshot_id} persist failed (non-fatal): {_snap_err}")


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

    # Prefer structured HaltReason if one was attached via set_halt().
    struct = state.project_metadata.get("halt_reason_struct")
    if struct:
        # Rehydrate into HaltReason and render full Telegram block.
        try:
            reason_obj = HaltReason(
                code=HaltCode(struct["code"]),
                title=struct["title"],
                detail=struct["detail"],
                stage=struct.get("stage", state.current_stage.value),
                failing_gate=struct.get("failing_gate"),
                remediation_steps=list(struct.get("remediation_steps") or []),
                restore_options=list(struct.get("restore_options") or ["/continue", "/cancel"]),
            )
            logger.warning(
                f"[{state.project_id}] Pipeline HALTED: "
                f"[{reason_obj.code.value}] {reason_obj.title}"
            )
            await send_telegram_message(state.operator_id, reason_obj.format_for_telegram())
            return state
        except (KeyError, ValueError) as e:
            logger.error(f"[{state.project_id}] halt_reason_struct malformed: {e}")

    # Fallback — no structured payload. Build one from whatever free-text
    # signals exist. Never render the literal string "unknown".
    legal = (state.legal_halt_reason or "").strip()
    stored = (state.project_metadata.get("halt_reason") or "").strip()
    last_error = (state.project_metadata.get("last_error") or "").strip()
    detail_parts = [p for p in (legal, stored, last_error) if p and p.lower() != "unknown"]
    detail = " | ".join(detail_parts) or "No diagnostic detail was captured at the halt site."

    reason_obj = HaltReason(
        code=HaltCode.UNCAUGHT_EXCEPTION,
        title="Pipeline halted",
        detail=detail,
        stage=state.current_stage.value,
        remediation_steps=[
            f"/restore State_#{state.snapshot_id or 0}",
            "/continue",
            "/cancel",
        ],
    )
    logger.warning(f"[{state.project_id}] Pipeline HALTED: {reason_obj}")
    await send_telegram_message(state.operator_id, reason_obj.format_for_telegram())
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

    # Fast-exit: if the pipeline was flagged as aborted before we even started
    # (e.g. a /cancel arrived while the task was queued), skip all stages immediately.
    if state.pipeline_aborted:
        logger.info(f"[{state.project_id}] Pipeline pre-aborted — returning without running stages")
        return state

    # ── Credential pre-flight ────────────────────────────────────────
    # Set SKIP_CREDENTIAL_PREFLIGHT=true to bypass in test/dry-run environments.
    _skip_preflight = os.environ.get("SKIP_CREDENTIAL_PREFLIGHT", "").lower() in ("true", "1", "yes")
    if not _skip_preflight:
        from factory.core.credentials import check_credentials, get_missing_critical, format_credential_error
        _cred_results = check_credentials()
        _missing_critical = get_missing_critical(_cred_results)
        # If BOTH anthropic and google_ai are missing → true CRITICAL gap
        _ai_creds_absent = (
            not any(r.present for r in _cred_results if r.service_id in ("anthropic", "google_ai"))
        )
        _real_missing = [r for r in _missing_critical if r.service_id != "google_ai" or _ai_creds_absent]
        if _real_missing:
            error_msg = format_credential_error(_real_missing)
            set_halt(state, HaltReason(
                code=HaltCode.CREDENTIAL_MISSING,
                title="Missing required credentials",
                detail=error_msg[:800],
                stage="S0_INTAKE",
                remediation_steps=[r.fix_steps[0] for r in _real_missing if r.fix_steps],
                restore_options=["/cancel"],
            ))
            _transition_to(state, Stage.HALTED)
            try:
                await send_telegram_message(state.operator_id, error_msg)
            except Exception:
                pass
            return await halt_handler_node(state)

    # 2d-iv — set wall-clock deadline (4 hours from first run)
    if not state.pipeline_deadline:
        from datetime import timedelta
        deadline_dt = datetime.now(timezone.utc) + timedelta(hours=4)
        state.pipeline_deadline = deadline_dt.isoformat()

    try:
        for stage_name, stage_fn in STAGE_SEQUENCE[:7]:  # S0→S6 linear; S7+ handled by routing
            state = await stage_fn(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            if _abort_check(state):
                return state
            # stage_name format: "s0_intake" → "S0_INTAKE"
            await _notify_stage_complete(state, stage_name.upper())
            if _abort_check(state):
                return state

        while True:
            route = route_after_test(state)
            if route == "halt":
                return await halt_handler_node(state)
            if route == "s4_codegen":
                state = await s4_codegen_node(state)
                if state.current_stage == Stage.HALTED:
                    return await halt_handler_node(state)
                if _abort_check(state):
                    return state
                await _notify_stage_complete(state, "S4_CODEGEN")
                if _abort_check(state):
                    return state
                state = await s5_build_node(state)
                if state.current_stage == Stage.HALTED:
                    return await halt_handler_node(state)
                if _abort_check(state):
                    return state
                await _notify_stage_complete(state, "S5_BUILD")
                if _abort_check(state):
                    return state
                state = await s6_test_node(state)
                if state.current_stage == Stage.HALTED:
                    return await halt_handler_node(state)
                if _abort_check(state):
                    return state
                await _notify_stage_complete(state, "S6_TEST")
                if _abort_check(state):
                    return state
                continue
            if route == "s7_deploy":
                break

        state = await s7_deploy_node(state)
        if state.current_stage == Stage.HALTED:
            return await halt_handler_node(state)
        if _abort_check(state):
            return state
        await _notify_stage_complete(state, "S7_DEPLOY")
        if _abort_check(state):
            return state

        state = await s8_verify_node(state)
        if state.current_stage == Stage.HALTED:
            return await halt_handler_node(state)
        if _abort_check(state):
            return state
        await _notify_stage_complete(state, "S8_VERIFY")
        if _abort_check(state):
            return state

        while True:
            route = route_after_verify(state)
            if route == "halt":
                return await halt_handler_node(state)
            if route == "s7_deploy":
                state = await s7_deploy_node(state)
                if state.current_stage == Stage.HALTED:
                    return await halt_handler_node(state)
                if _abort_check(state):
                    return state
                await _notify_stage_complete(state, "S7_DEPLOY")
                if _abort_check(state):
                    return state
                state = await s8_verify_node(state)
                if state.current_stage == Stage.HALTED:
                    return await halt_handler_node(state)
                if _abort_check(state):
                    return state
                await _notify_stage_complete(state, "S8_VERIFY")
                if _abort_check(state):
                    return state
                continue
            if route == "s9_handoff":
                break

        state = await s9_handoff_node(state)
        if state.current_stage == Stage.HALTED:
            return await halt_handler_node(state)
        if _abort_check(state):
            return state
        await _notify_stage_complete(state, "S9_HANDOFF")

        _transition_to(state, Stage.COMPLETED)
        logger.info(f"[{state.project_id}] Pipeline COMPLETE — cost=${state.total_cost_usd:.2f}")
        return state

    except asyncio.CancelledError:
        logger.info(f"[{state.project_id}] Pipeline cancelled by operator")
        state.pipeline_aborted = True
        _transition_to(state, Stage.HALTED)
        set_halt(state, HaltReason(
            code=HaltCode.PIPELINE_CANCELLED,
            title="Pipeline cancelled by operator",
            detail="The operator used /cancel while the pipeline was running.",
            stage=state.current_stage.value,
            remediation_steps=["/new to start a fresh project"],
        ))
        # best-effort notification — don't re-raise, let the task exit cleanly
        try:
            await send_telegram_message(
                state.operator_id,
                HaltReason(
                    code=HaltCode.PIPELINE_CANCELLED,
                    title="Pipeline cancelled",
                    detail="Stopped by /cancel.",
                    stage=state.current_stage.value,
                    remediation_steps=["/new to start a fresh project"],
                ).format_for_telegram(),
            )
        except Exception:
            pass
        return state


async def resume_pipeline(state: PipelineState) -> PipelineState:
    """Resume pipeline from state.current_stage.

    Spec: §2.7.1 — used by /continue and callback restore flow.
    Finds the current stage in STAGE_SEQUENCE and runs from that point;
    handles S7+ routing loops identically to run_pipeline().

    If current_stage is HALTED the caller must have already set
    state.current_stage back to the target stage before calling this.
    """
    logger.info(
        f"[{state.project_id}] Pipeline RESUME from {state.current_stage.value}"
    )
    budget_governor.set_spend_source(cost_tracker.monthly_total_cents)

    # Clear abort flag on resume (operator explicitly requested continuation)
    state.pipeline_aborted = False

    current = state.current_stage.value  # e.g. "s4_codegen"
    _linear = STAGE_SEQUENCE[:7]         # (name, fn) pairs for S0→S6
    _linear_names = [n for n, _ in _linear]

    try:
        # ── Linear portion S0–S6 ────────────────────────────────────────
        if current in _linear_names:
            start_idx = _linear_names.index(current)
            for stage_name, stage_fn in _linear[start_idx:]:
                state = await stage_fn(state)
                if state.current_stage == Stage.HALTED:
                    return await halt_handler_node(state)
                if _abort_check(state):
                    return state
                await _notify_stage_complete(state, stage_name.upper())
                if _abort_check(state):
                    return state

            # After S6 — test routing loop (same as run_pipeline)
            while True:
                route = route_after_test(state)
                if route == "halt":
                    return await halt_handler_node(state)
                if route == "s4_codegen":
                    state = await s4_codegen_node(state)
                    if state.current_stage == Stage.HALTED:
                        return await halt_handler_node(state)
                    if _abort_check(state):
                        return state
                    await _notify_stage_complete(state, "S4_CODEGEN")
                    if _abort_check(state):
                        return state
                    state = await s5_build_node(state)
                    if state.current_stage == Stage.HALTED:
                        return await halt_handler_node(state)
                    if _abort_check(state):
                        return state
                    await _notify_stage_complete(state, "S5_BUILD")
                    if _abort_check(state):
                        return state
                    state = await s6_test_node(state)
                    if state.current_stage == Stage.HALTED:
                        return await halt_handler_node(state)
                    if _abort_check(state):
                        return state
                    await _notify_stage_complete(state, "S6_TEST")
                    if _abort_check(state):
                        return state
                    continue
                break  # route == "s7_deploy"
            current = "s7_deploy"

        # ── S7 Deploy ───────────────────────────────────────────────────
        if current == "s7_deploy":
            state = await s7_deploy_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            if _abort_check(state):
                return state
            await _notify_stage_complete(state, "S7_DEPLOY")
            if _abort_check(state):
                return state
            current = "s8_verify"

        # ── S8 Verify ───────────────────────────────────────────────────
        if current == "s8_verify":
            state = await s8_verify_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            if _abort_check(state):
                return state
            await _notify_stage_complete(state, "S8_VERIFY")
            if _abort_check(state):
                return state

            while True:
                route = route_after_verify(state)
                if route == "halt":
                    return await halt_handler_node(state)
                if route == "s7_deploy":
                    state = await s7_deploy_node(state)
                    if state.current_stage == Stage.HALTED:
                        return await halt_handler_node(state)
                    if _abort_check(state):
                        return state
                    await _notify_stage_complete(state, "S7_DEPLOY")
                    if _abort_check(state):
                        return state
                    state = await s8_verify_node(state)
                    if state.current_stage == Stage.HALTED:
                        return await halt_handler_node(state)
                    if _abort_check(state):
                        return state
                    await _notify_stage_complete(state, "S8_VERIFY")
                    if _abort_check(state):
                        return state
                    continue
                break  # route == "s9_handoff"
            current = "s9_handoff"

        # ── S9 Handoff ──────────────────────────────────────────────────
        if current == "s9_handoff":
            state = await s9_handoff_node(state)
            if state.current_stage == Stage.HALTED:
                return await halt_handler_node(state)
            if _abort_check(state):
                return state
            await _notify_stage_complete(state, "S9_HANDOFF")

        _transition_to(state, Stage.COMPLETED)
        logger.info(f"[{state.project_id}] Pipeline COMPLETE — cost=${state.total_cost_usd:.2f}")
        return state

    except asyncio.CancelledError:
        logger.info(f"[{state.project_id}] Pipeline cancelled by operator")
        state.pipeline_aborted = True
        _transition_to(state, Stage.HALTED)
        set_halt(state, HaltReason(
            code=HaltCode.PIPELINE_CANCELLED,
            title="Pipeline cancelled by operator",
            detail="The operator used /cancel while the pipeline was running.",
            stage=state.current_stage.value,
            remediation_steps=["/new to start a fresh project"],
        ))
        try:
            await send_telegram_message(
                state.operator_id,
                HaltReason(
                    code=HaltCode.PIPELINE_CANCELLED,
                    title="Pipeline cancelled",
                    detail="Stopped by /cancel.",
                    stage=state.current_stage.value,
                    remediation_steps=["/new to start a fresh project"],
                ).format_for_telegram(),
            )
        except Exception:
            pass
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
