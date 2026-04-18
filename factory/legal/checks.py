"""
AI Factory Pipeline v5.8 — Continuous Legal Thread

Implements:
  - §2.7.3 LEGAL_CHECKS_BY_STAGE mapping
  - legal_check_hook() — injected by pipeline_node decorator
  - run_legal_check() — dispatches individual checks
  - 9 legal check implementations

Legal checks do not appear as pipeline stages — they are injected
by the pipeline_node wrapper at pre/post boundaries.

Spec Authority: v5.8 §2.7.3
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import AIRole, PipelineState, Stage
from factory.core.roles import call_ai
from factory.telegram.notifications import send_telegram_message
from factory.legal.regulatory import (
    get_regulators_for_category,
    is_ksa_compliant_region,
    is_within_deploy_window,
    check_prohibited_sdks,
    PDPL_REQUIREMENTS,
    PRIMARY_DATA_REGION,
)

logger = logging.getLogger("factory.legal.checks")


# ═══════════════════════════════════════════════════════════════════
# §2.7.3 Legal Checks by Stage
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


# ═══════════════════════════════════════════════════════════════════
# §2.7.3 Legal Check Hook
# ═══════════════════════════════════════════════════════════════════


async def legal_check_hook(
    state: PipelineState, stage: Stage, phase: str,
) -> None:
    """Run legal checks for a given stage/phase.

    Spec: §2.7.3

    Called by pipeline_node decorator before and after each stage.
    Uses Scout + Strategist for AI-driven checks.
    """
    checks = LEGAL_CHECKS_BY_STAGE.get(stage, {}).get(phase, [])

    for check_name in checks:
        result = await run_legal_check(state, check_name)

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
            await send_telegram_message(
                state.operator_id,
                f"🚨 Legal compliance issue:\n\n"
                f"Check: {check_name}\n"
                f"Stage: {stage.value}\n"
                f"Details: {result.get('details', 'N/A')}\n\n"
                f"Pipeline paused. Reply /continue after resolving.",
            )
            return


# ═══════════════════════════════════════════════════════════════════
# §2.7.3 Individual Check Implementations
# ═══════════════════════════════════════════════════════════════════

# Check registry
_CHECK_REGISTRY: dict[str, object] = {}


def register_check(name: str):
    """Decorator to register a legal check function."""
    def decorator(fn):
        _CHECK_REGISTRY[name] = fn
        return fn
    return decorator


async def run_legal_check(
    state: PipelineState, check_name: str,
) -> dict:
    """Dispatch to the appropriate check implementation.

    Returns: {"passed": bool, "details": str, "blocking": bool}
    """
    check_fn = _CHECK_REGISTRY.get(check_name)
    if not check_fn:
        logger.warning(f"Unknown legal check: {check_name}")
        return {"passed": True, "details": f"Check '{check_name}' not implemented", "blocking": False}

    try:
        return await check_fn(state)
    except Exception as e:
        logger.error(f"Legal check '{check_name}' error: {e}")
        return {"passed": False, "details": str(e), "blocking": False}


# ───────────────────────────────────────────────────────────
# S2 Pre: Ministry of Commerce Licensing
# ───────────────────────────────────────────────────────────


@register_check("ministry_of_commerce_licensing")
async def check_moc_licensing(state: PipelineState) -> dict:
    """Verify business license requirements for the app category.

    Spec: §2.7.3 — S2 pre
    """
    category = state.project_metadata.get("app_category", "other")
    regulators = get_regulators_for_category(category)

    if "MINISTRY_OF_COMMERCE" in regulators:
        # AI-driven check: ask Scout about licensing requirements
        result = await call_ai(
            role=AIRole.SCOUT,
            prompt=(
                f"What KSA Ministry of Commerce licenses are required "
                f"for a {category} app? "
                f"Return: license_type, required (yes/no), link_to_apply."
            ),
            state=state,
            action="general",
        )
        return {
            "passed": True,
            "details": f"MoC licensing checked for {category}: {result[:200]}",
            "blocking": False,  # Advisory — operator must obtain license
        }

    return {
        "passed": True,
        "details": f"No MoC licensing required for {category}",
        "blocking": False,
    }


# ───────────────────────────────────────────────────────────
# S2 Post: Blueprint Legal Compliance
# ───────────────────────────────────────────────────────────


@register_check("blueprint_legal_compliance")
async def check_blueprint_compliance(state: PipelineState) -> dict:
    """Validate blueprint against KSA legal requirements.

    Spec: §2.7.3 — S2 post
    """
    category = state.project_metadata.get("app_category", "other")
    has_payments = state.project_metadata.get("has_payments", False)
    has_user_accounts = state.project_metadata.get("has_user_accounts", False)

    issues = []

    if has_payments:
        regulators = get_regulators_for_category(category)
        if "SAMA" not in regulators:
            issues.append(
                "App has payments but category may not trigger SAMA oversight. "
                "Verify payment processor compliance."
            )

    if has_user_accounts and not state.project_metadata.get("pdpl_noted"):
        issues.append("App collects user data — PDPL compliance required.")
        state.project_metadata["pdpl_noted"] = True

    return {
        "passed": len(issues) == 0,
        "details": "; ".join(issues) if issues else "Blueprint compliant",
        "blocking": False,  # Advisory warnings
    }


# ───────────────────────────────────────────────────────────
# S3 Post: PDPL Consent Checkboxes
# ───────────────────────────────────────────────────────────


@register_check("pdpl_consent_checkboxes")
async def check_pdpl_consent(state: PipelineState) -> dict:
    """Ensure PDPL consent UI is present in generated code.

    Spec: §2.7.3 — S3 post
    """
    has_user_accounts = state.project_metadata.get("has_user_accounts", False)

    if not has_user_accounts:
        return {
            "passed": True,
            "details": "No user accounts — PDPL consent not required",
            "blocking": False,
        }

    # Check if generated code includes consent patterns
    code_output = state.project_metadata.get("s3_code_summary", "")
    consent_keywords = [
        "consent", "privacy", "pdpl", "agree",
        "data_collection", "opt_in",
    ]
    has_consent = any(kw in code_output.lower() for kw in consent_keywords)

    if not has_consent:
        return {
            "passed": False,
            "details": (
                "Generated code missing PDPL consent UI. "
                "User apps must include explicit consent checkbox before "
                "collecting personal data (PDPL Article 6)."
            ),
            "blocking": True,
        }

    return {
        "passed": True,
        "details": "PDPL consent patterns found in generated code",
        "blocking": False,
    }


# ───────────────────────────────────────────────────────────
# S3 Post: Data Residency Compliance
# ───────────────────────────────────────────────────────────


@register_check("data_residency_compliance")
async def check_data_residency(state: PipelineState) -> dict:
    """Validate data storage is KSA-resident.

    Spec: §2.7.3 — S3 post
    """
    region = (
        (state.s2_output or {}).get("deploy_region")
        or state.project_metadata.get("deploy_region", PRIMARY_DATA_REGION)
    )

    if not is_ksa_compliant_region(region):
        return {
            "passed": False,
            "severity": "critical",
            "details": (
                f"Deploy region '{region}' is not KSA-compliant. "
                f"Must use me-central1 (Dammam) or approved Gulf regions."
            ),
            "blocking": True,
        }

    return {
        "passed": True,
        "details": f"Data region '{region}' is KSA-compliant",
        "blocking": False,
    }


# ───────────────────────────────────────────────────────────
# S4 Post: No Prohibited SDKs
# ───────────────────────────────────────────────────────────


@register_check("no_prohibited_sdks")
async def check_sdks(state: PipelineState) -> dict:
    """Scan build dependencies for sanctioned/prohibited SDKs.

    Spec: §2.7.3 — S4 post
    """
    deps = state.project_metadata.get("dependencies", [])
    prohibited = check_prohibited_sdks(deps)

    if prohibited:
        return {
            "passed": False,
            "details": (
                f"Prohibited SDKs found: {prohibited}. "
                f"Remove before build."
            ),
            "blocking": True,
        }

    return {
        "passed": True,
        "details": f"No prohibited SDKs in {len(deps)} dependencies",
        "blocking": False,
    }


# ───────────────────────────────────────────────────────────
# S6 Pre: CST Time-of-Day Restrictions
# ───────────────────────────────────────────────────────────


@register_check("cst_time_of_day_restrictions")
async def check_deploy_time(state: PipelineState) -> dict:
    """Prevent deployment outside allowed hours.

    Spec: §2.7.3 — S6 pre
    Default: 06:00–23:00 AST (UTC+3)
    """
    import os as _os
    if _os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes"):
        return {"passed": True, "details": "Dry-run: time-of-day check skipped", "blocking": False}

    from datetime import timedelta
    now_utc = datetime.now(timezone.utc)
    now_ast = now_utc + timedelta(hours=3)
    hour_ast = now_ast.hour

    if not is_within_deploy_window(hour_ast):
        return {
            "passed": False,
            "details": (
                f"Deploy blocked: {hour_ast:02d}:00 AST is outside "
                f"allowed window. Resuming at 06:00 AST."
            ),
            "blocking": True,
        }

    return {
        "passed": True,
        "details": f"Deploy allowed at {hour_ast:02d}:00 AST",
        "blocking": False,
    }


# ───────────────────────────────────────────────────────────
# S6 Post: Deployment Region Compliance
# ───────────────────────────────────────────────────────────


@register_check("deployment_region_compliance")
async def check_deploy_region(state: PipelineState) -> dict:
    """Validate deployment target is in allowed regions.

    Spec: §2.7.3 — S6 post
    """
    region = state.project_metadata.get("deploy_region", PRIMARY_DATA_REGION)

    if not is_ksa_compliant_region(region):
        return {
            "passed": False,
            "details": f"Deployment region '{region}' is not KSA-compliant",
            "blocking": True,
        }

    return {
        "passed": True,
        "details": f"Deployment region '{region}' compliant",
        "blocking": False,
    }


# ───────────────────────────────────────────────────────────
# S8 Post: All Legal Docs Generated
# ───────────────────────────────────────────────────────────


@register_check("all_legal_docs_generated")
async def check_legal_docs(state: PipelineState) -> dict:
    """Confirm all required legal documents were produced.

    Spec: §2.7.3 — S8 post
    """
    docs = state.legal_documents or {}
    # Accept either the canonical key (terms_of_service) or legacy alias (terms_of_use)
    required = ["privacy_policy", "terms_of_service"]
    missing = [
        r for r in required
        if r not in docs and r.replace("_service", "_use") not in docs
    ]

    if missing:
        return {
            "passed": False,
            "details": f"Missing required legal docs: {missing}",
            "blocking": True,
        }

    return {
        "passed": True,
        "details": f"All {len(docs)} legal documents generated",
        "blocking": False,
    }


# ───────────────────────────────────────────────────────────
# S8 Post: Final Compliance Sign-Off
# ───────────────────────────────────────────────────────────


@register_check("final_compliance_sign_off")
async def check_final_compliance(state: PipelineState) -> dict:
    """Final compliance sweep before handoff.

    Spec: §2.7.3 — S8 post
    """
    checks_run = state.legal_checks_log
    failed_blocking = [
        c for c in checks_run
        if not c.get("passed") and c.get("check") != "final_compliance_sign_off"
    ]

    if failed_blocking:
        unresolved = [c["check"] for c in failed_blocking]
        return {
            "passed": False,
            "details": f"Unresolved legal issues: {unresolved}",
            "blocking": False,  # Advisory at final stage
        }

    return {
        "passed": True,
        "details": f"Final compliance: {len(checks_run)} checks reviewed",
        "blocking": False,
    }


# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════


def get_checks_for_stage(
    stage: Stage, phase: str,
) -> list[str]:
    """Get list of check names for a stage/phase."""
    return LEGAL_CHECKS_BY_STAGE.get(stage, {}).get(phase, [])


def get_all_check_names() -> list[str]:
    """Get all registered check names."""
    return list(_CHECK_REGISTRY.keys())