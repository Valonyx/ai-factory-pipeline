"""
AI Factory Pipeline v5.6 — S1 Legal Gate Node

Implements:
  - §4.2 S1 Legal Gate (classification, regulatory mapping, risk)
  - Scout researches applicable KSA regulations
  - Strategist classifies and decides
  - §4.2.1 STRICT_STORE_COMPLIANCE enforcement (FIX-06)
  - §4.2.3 Preflight App Store compliance (advisory)

Spec Authority: v5.6 §4.2, §4.2.1–§4.2.3
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from factory.core.state import (
    AIRole,
    AutonomyMode,
    NotificationType,
    PipelineState,
    Stage,
)
from factory.core.roles import call_ai
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s1_legal")

# §4.2.1 Strict Compliance Config (FIX-06)
STRICT_STORE_COMPLIANCE = os.getenv(
    "STRICT_STORE_COMPLIANCE", "false",
).lower() == "true"

COMPLIANCE_CONFIDENCE_THRESHOLD = float(
    os.getenv("COMPLIANCE_CONFIDENCE_THRESHOLD", "0.7"),
)


# ═══════════════════════════════════════════════════════════════════
# §4.2 S1 Legal Gate Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S1_LEGAL)
async def s1_legal_node(state: PipelineState) -> PipelineState:
    """S1: Legal Gate — classify, map regulations, assess risk.

    Spec: §4.2
    Step 1: Scout researches applicable KSA regulations
    Step 2: Strategist classifies and decides (data sensitivity, risk)
    Step 3: Handle blocked features (Copilot mode)
    Step 4: Handle overall proceed/halt
    Step 5: Preflight App Store compliance (advisory)
    Step 6: STRICT_STORE_COMPLIANCE enforcement (FIX-06)

    Cost target: <$0.80
    """
    requirements = state.s0_output or {}

    # ── Step 1: Scout researches KSA regulations ──
    legal_research = await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"What KSA regulations apply to this app?\n\n"
            f"App: {requirements.get('app_description', 'Unknown')}\n"
            f"Category: {requirements.get('app_category', 'other')}\n"
            f"Has payments: {requirements.get('has_payments', False)}\n"
            f"Has user accounts: {requirements.get('has_user_accounts', False)}\n"
            f"Has location: {requirements.get('has_location', False)}\n\n"
            f"Check: PDPL (data protection), CST (telecom/app registration), "
            f"SAMA (financial), NDMO (data governance), NCA (cybersecurity), "
            f"SDAIA (AI governance), Ministry of Commerce (business licensing).\n"
            f"Return specific requirements per regulatory body."
        ),
        state=state,
        action="general",
    )

    # ── Step 2: Strategist classifies and decides ──
    legal_decision = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"LEGAL CLASSIFICATION.\n\n"
            f"App requirements:\n{json.dumps(requirements, indent=2)[:4000]}\n\n"
            f"KSA regulatory research:\n{legal_research[:3000]}\n\n"
            f"Classify and decide. Return ONLY valid JSON:\n"
            f'{{\n'
            f'  "data_classification": "public|internal|confidential|restricted",\n'
            f'  "regulatory_bodies": ["CST", "SAMA"],\n'
            f'  "payment_mode": "SANDBOX",\n'
            f'  "feature_risk_assessment": [\n'
            f'    {{"feature": "...", "risk": "clear|flagged|blocked", '
            f'"reason": "...", "action": "..."}}\n'
            f'  ],\n'
            f'  "required_legal_docs": ["privacy_policy", "terms_of_use"],\n'
            f'  "required_licenses": ["none"],\n'
            f'  "cross_border_data": false,\n'
            f'  "sama_sandbox_required": false,\n'
            f'  "overall_risk": "low|medium|high",\n'
            f'  "proceed": true,\n'
            f'  "blocking_issues": []\n'
            f'}}'
        ),
        state=state,
        action="decide_legal",
    )

    try:
        legal_output = json.loads(legal_decision)
    except json.JSONDecodeError:
        logger.warning(
            f"[{state.project_id}] S1: Failed to parse Strategist JSON, "
            f"using safe defaults"
        )
        legal_output = {
            "data_classification": "internal",
            "regulatory_bodies": ["CST"],
            "payment_mode": "SANDBOX",
            "feature_risk_assessment": [],
            "required_legal_docs": ["privacy_policy", "terms_of_use"],
            "required_licenses": ["none"],
            "cross_border_data": False,
            "sama_sandbox_required": False,
            "overall_risk": "medium",
            "proceed": True,
            "blocking_issues": [],
        }

    # ── Step 3: Handle blocked features (Copilot) ──
    blocked_features = [
        f for f in legal_output.get("feature_risk_assessment", [])
        if f.get("risk") == "blocked"
    ]

    if blocked_features and state.autonomy_mode == AutonomyMode.COPILOT:
        from factory.telegram.decisions import present_decision

        blocked_names = [f.get("feature", "?") for f in blocked_features]
        await present_decision(
            state=state,
            decision_type="s1_blocked_features",
            question=f"Legal blocked features: {blocked_names}",
            options=[
                {"label": "Remove blocked features", "value": "remove"},
                {"label": "Apply for licenses first", "value": "license"},
                {"label": "Proceed anyway (SANDBOX)", "value": "sandbox"},
            ],
            recommended=0,
        )

    # ── Step 4: Handle overall proceed/halt ──
    if not legal_output.get("proceed", True):
        state.legal_halt = True
        state.legal_halt_reason = (
            f"S1 Legal Gate: Blocking issues: "
            f"{legal_output.get('blocking_issues', ['Unknown'])}"
        )

    state.s1_output = legal_output

    # ── Step 5: Preflight App Store compliance (advisory) ──
    preflight_warnings = await _preflight_store_compliance(state)
    if preflight_warnings:
        state.s1_output["compliance_warnings"] = preflight_warnings
        state.warnings.extend(preflight_warnings)

        from factory.telegram.notifications import notify_operator
        await notify_operator(
            state,
            NotificationType.INFO,
            f"⚠️ App Store Preflight found {len(preflight_warnings)} "
            f"potential issues:\n"
            + "\n".join(
                f"  • {w.get('rule', '?')}: {w.get('detail', '')}"
                for w in preflight_warnings[:5]
            ),
        )

    # ── Step 6: STRICT_STORE_COMPLIANCE enforcement (FIX-06) ──
    if STRICT_STORE_COMPLIANCE and preflight_warnings:
        high_severity = [
            w for w in preflight_warnings
            if w.get("severity") == "high"
        ]
        if high_severity:
            confidence = _calculate_compliance_confidence(preflight_warnings)
            if confidence > COMPLIANCE_CONFIDENCE_THRESHOLD:
                state.legal_halt = True
                state.legal_halt_reason = (
                    f"[FIX-06] Compliance blocker(s) at confidence "
                    f"{confidence:.2f}: {len(high_severity)} issues"
                )

    logger.info(
        f"[{state.project_id}] S1 complete: "
        f"risk={legal_output.get('overall_risk', '?')}, "
        f"proceed={legal_output.get('proceed', '?')}, "
        f"warnings={len(preflight_warnings)}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# §4.2.3 Preflight Compliance
# ═══════════════════════════════════════════════════════════════════


async def _preflight_store_compliance(
    state: PipelineState,
) -> list[dict]:
    """Query current Apple/Google guidelines for known rejection triggers.

    Spec: §4.2.3
    Advisory only — does not block pipeline.
    """
    warnings: list[dict] = []
    requirements = state.s0_output or {}
    app_desc = requirements.get("app_description", "")

    if not app_desc:
        return warnings

    try:
        # Inline budget guard (check_circuit_breaker wired in Part 9)
        current_spend = state.total_cost_usd
        can_research = current_spend < 25.00
        if not can_research:
            return warnings

        guideline_intel = await call_ai(
            role=AIRole.SCOUT,
            prompt=(
                f"Check Apple App Store Review Guidelines and Google Play "
                f"policies for potential rejection risks for this app: "
                f"'{app_desc}'. Focus on: Section 3.1.1 (In-App Purchase), "
                f"Section 5.1.1 (Data Collection), Section 4.2 (Minimum "
                f"Functionality), Section 2.1 (App Completeness). "
                f"Return ONLY a JSON array of "
                f'{{"rule": "...", "risk_level": "low|medium|high", '
                f'"recommendation": "..."}}'
            ),
            state=state,
            action="general",
        )

        parsed = json.loads(guideline_intel)
        for item in parsed:
            warnings.append({
                "source": "scout_guidelines",
                "rule": item.get("rule", ""),
                "detail": item.get("recommendation", ""),
                "severity": item.get("risk_level", "medium"),
            })
    except (json.JSONDecodeError, TypeError, Exception) as e:
        logger.debug(f"Preflight compliance non-critical error: {e}")

    return warnings


def _calculate_compliance_confidence(warnings: list[dict]) -> float:
    """Estimate confidence of compliance blockers.

    Spec: §4.2.1
    """
    if not warnings:
        return 0.0
    high_confidence_count = sum(
        1 for w in warnings
        if w.get("severity") == "high"
        and w.get("source") == "mother_memory"
    )
    total = len(warnings)
    return min(1.0, 0.5 + (high_confidence_count / total) * 0.5)


# Register with DAG
register_stage_node("s1_legal", s1_legal_node)