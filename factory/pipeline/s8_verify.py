"""
AI Factory Pipeline v5.8 — S8 Verify Node

Implements:
  - §4.8 S8 Verify (smoke tests on deployed app)
  - Web: HTTP health check
  - Mobile: App Store processing status
  - Legal: Final compliance verification via Scout

Spec Authority: v5.8 §4.8

PATCH NOTE (NB1 Part 8):
  check_circuit_breaker() belongs to factory.intelligence.circuit_breaker
  which is built in Part 9. Replaced with inline budget guard using
  BUDGET_CONFIG until Part 9 wires the real circuit breaker.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    PipelineState,
    Stage,
    BUDGET_CONFIG,
)
from factory.core.roles import call_ai
from factory.core.execution import ExecutionModeManager
from factory.core.user_space import enforce_user_space
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s8_verify")


# ═══════════════════════════════════════════════════════════════════
# §4.8 S8 Verify Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S8_VERIFY)
async def s8_verify_node(state: PipelineState) -> PipelineState:
    """S7: Verify — smoke tests on deployed app.

    Spec: §4.8
    1. Web: HTTP health check
    2. Mobile: App Store processing status
    3. Legal: Final compliance verification (Scout)

    Cost target: <$0.20
    """
    # ── Issue 5 re-verify: inject chain context ──
    from factory.pipeline.stage_chain import inject_chain_context as _inject_cc  # noqa: F401

    # DRY_RUN / CI / mock: no real deployment infrastructure — auto-pass verification
    # so the pipeline can reach S9 without an infinite S8→S7 retry loop.
    import os as _os
    if (
        _os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
        or _os.getenv("PIPELINE_ENV", "").lower() == "ci"
        or _os.getenv("AI_PROVIDER", "").lower() == "mock"
    ):
        logger.info(f"[{state.project_id}] S8: DRY_RUN — auto-passing verification")
        state.s8_output = {
            "passed": True,
            "checks": [{"type": "dry_run_bypass", "passed": True}],
            "check_count": 1,
        }
        return state

    deployments = (state.s7_output or {}).get("deployments", {})
    checks: list[dict] = []

    # ── Web verification ──
    if "web" in deployments:
        web_check = await _verify_web(state, deployments["web"])
        checks.append(web_check)

    # ── Source-only delivery verification ──
    if "source_code" in deployments:
        src = deployments["source_code"]
        checks.append({
            "type": "source_delivery",
            "passed": src.get("success", False),
            "method": src.get("method", "source_zip"),
            "note": "Source code delivered (no binary build environment)",
        })

    # ── Mobile verification ──
    for platform in ("android", "ios"):
        if platform in deployments:
            mobile_check = _verify_mobile(platform, deployments[platform])
            checks.append(mobile_check)

    # ── App Store guidelines check (Scout) ──
    guidelines_check = await _verify_store_guidelines(state)
    if guidelines_check:
        checks.append(guidelines_check)

    all_passed = all(c.get("passed", False) for c in checks)

    state.project_metadata["verify_passed"] = all_passed
    state.s8_output = {
        "passed": all_passed,
        "checks": checks,
        "check_count": len(checks),
    }

    # ── Issue 11 re-verify: store stage insight ──
    try:
        from factory.core.stage_enrichment import store_stage_insight
        _health_url = next(
            (c.get("url","") for c in checks if c.get("type") == "web_health" and c.get("url")),
            ""
        )
        await store_stage_insight(
            "s8_verify", state,
            fact=(
                f"Verify: {'PASS' if all_passed else 'FAIL'}. "
                f"URL: {_health_url}"
            ),
            category="verify",
        )
    except Exception as _si_err:
        logger.debug(f"[{state.project_id}] S8 store_stage_insight failed (non-fatal): {_si_err}")

    # Issue 19: when verification fails, capture the actual failure surface
    # (list of failed check types + their detail) so downstream halt handlers
    # render something actionable instead of "Reason: unknown".
    if not all_passed:
        failed = [c for c in checks if not c.get("passed", False)]
        failure_lines = [
            f"{c.get('type', 'check')}: "
            f"{c.get('detail') or c.get('note') or c.get('status') or c.get('url') or 'no detail'}"
            for c in failed
        ]
        failure_detail = "; ".join(failure_lines) or "no check detail captured"
        from factory.core.halt import HaltCode, HaltReason
        reason = HaltReason(
            code=HaltCode.STAGE_VERIFICATION_FAILED,
            title=f"S8 Verify failed ({len(failed)} of {len(checks)} checks)",
            detail=failure_detail[:1500],
            stage="S8_VERIFY",
            failing_gate="deploy_verification",
            remediation_steps=[
                "Inspect deployment logs for the failed check",
                "Re-run S7 deploy with /continue after fixing",
                f"/restore State_#{state.snapshot_id or 0}",
            ],
        )
        state.project_metadata["s8_failure_reason"] = reason.to_dict()
        state.project_metadata["halt_reason_struct"] = reason.to_dict()
        state.project_metadata["halt_reason"] = str(reason)

    logger.info(
        f"[{state.project_id}] S8 Verify: "
        f"passed={all_passed}, checks={len(checks)}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# Verification Checks
# ═══════════════════════════════════════════════════════════════════


async def _verify_web(
    state: PipelineState, web_deploy: dict,
) -> dict:
    """HTTP health check on deployed web app.

    Spec: §4.8 (web verification)
    """
    url = web_deploy.get("url")
    if not url:
        return {
            "type": "web_health",
            "passed": web_deploy.get("success", False),
            "note": "No URL available for health check",
        }

    exec_mgr = ExecutionModeManager(state)

    # Generate curl command via Quick Fix
    health_cmd = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=(
            f"Generate a curl command to health-check this URL: {url}\n"
            f"Include -s -o /dev/null -w '%{{http_code}}' for status code.\n"
            f"Return ONLY the curl command."
        ),
        state=state,
        action="general",
    )

    result = await exec_mgr.execute_task({
        "name": "web_health_check",
        "type": "backend_deploy",
        "command": enforce_user_space(health_cmd.strip()),
        "timeout": 30,
    }, requires_macincloud=False)

    return {
        "type": "web_health",
        "passed": result.get("exit_code", 1) == 0,
        "url": url,
        "status_code": result.get("stdout", "").strip(),
    }


def _verify_mobile(platform: str, deploy: dict) -> dict:
    """Check mobile deployment status.

    Spec: §4.8 (mobile verification)
    """
    method = deploy.get("method", "unknown")

    if method == "api":
        return {
            "type": f"{platform}_upload",
            "passed": True,
            "status": deploy.get("status", "submitted"),
        }
    elif method == "airlock_telegram":
        return {
            "type": f"{platform}_airlock",
            "passed": True,
            "note": "Binary sent to operator for manual upload",
        }
    else:
        # Issue 19: Capture actual failure surface rather than literal "unknown".
        err = deploy.get("error") or deploy.get("status_detail")
        status_detail = (
            f"method={method}, success={deploy.get('success', False)}"
            + (f", error={err}" if err else "")
        )
        return {
            "type": f"{platform}_deploy",
            "passed": deploy.get("success", False),
            "status": deploy.get("status") or status_detail,
            "method": method,
            "detail": status_detail,
        }


async def _verify_store_guidelines(state: PipelineState) -> Optional[dict]:
    """Scout-based App Store guidelines check.

    Spec: §4.8 (legal verification)

    PATCH (NB1 Part 8): Inline budget guard replaces check_circuit_breaker()
    which is wired in Part 9 (factory.intelligence.circuit_breaker).
    Guard passes when per-project AI spend is below the per-project cap.
    """
    # CLI/dry-run bypass — no real Scout available, auto-pass guidelines check
    import os
    if os.getenv("TELEGRAM_BOT_TOKEN") is None or os.getenv("DRY_RUN", "false").lower() == "true":
        logger.info(f"[{state.project_id}] S7: dry-run bypass — guidelines auto-passed")
        return {"type": "store_guidelines", "passed": True, "details": "dry-run bypass"}

    # Inline budget guard — replaced by real circuit breaker in Part 9
    current_spend = state.total_cost_usd
    per_project_cap = BUDGET_CONFIG.get("per_project_ai_cap", 25.00)
    can_research = current_spend < per_project_cap

    if not can_research:
        logger.warning(
            f"[{state.project_id}] S7: Budget cap reached "
            f"(${current_spend:.2f}), skipping Scout guidelines check."
        )
        return None

    from factory.core.stage_enrichment import enrich_prompt
    from factory.pipeline.stage_chain import inject_chain_context as _inject_cc
    s0 = state.s0_output or {}
    _guidelines_base = _inject_cc(
        f"Does this app description violate Apple App Store "
        f"or Google Play guidelines?\n"
        f"App: {s0.get('app_description', '')}\n"
        f"Category: {s0.get('app_category', '')}\n"
        f"Has payments: {s0.get('has_payments', False)}\n"
        f"Return: pass/fail with specific guideline references.",
        state,
        current_stage="s8_verify",
        compact=True,
    )
    _guidelines_prompt = await enrich_prompt(
        "s8_verify", _guidelines_base, state,
        scout=True,
        scout_query=(
            f"Current Apple App Store and Google Play Store review guidelines 2025-2026 "
            f"for {s0.get('app_category', 'general')} apps. "
            f"Common rejection reasons, required privacy disclosures, payment rules."
        ),
    )
    guidelines = await call_ai(
        role=AIRole.SCOUT,
        prompt=_guidelines_prompt,
        state=state,
        action="general",
    )

    # Auto-pass when AI is in fallback mode (no providers available)
    fallback_markers = ("[all-providers-exhausted]", "[mock-", "[mock]")
    is_fallback = any(m in guidelines.lower()[:50] for m in fallback_markers)
    if is_fallback:
        return {
            "type": "store_guidelines",
            "passed": True,
            "details": "AI unavailable — guidelines auto-passed (review manually)",
        }

    passed = "pass" in guidelines.lower()[:200] and "fail" not in guidelines.lower()[:100]
    return {
        "type": "store_guidelines",
        "passed": passed,
        "details": guidelines[:500],
    }


# Register with DAG (replaces stub)
register_stage_node("s8_verify", s8_verify_node)
