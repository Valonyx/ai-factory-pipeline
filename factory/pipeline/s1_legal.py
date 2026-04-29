"""
AI Factory Pipeline v5.8 — S1 Legal Gate Node

Implements:
  - §4.2 S1 Legal Gate (classification, regulatory mapping, risk)
  - Iterative refinement loop (up to 5 passes until convergence)
  - 9-document PDF suite (DocuGen)
  - Structured risk register + compliance matrix + sources bibliography
  - In-app legal text bundle (consent banners, notices, disclaimers)
  - P0 halt gate with COPILOT 4-option resolution menu
  - Mother Memory graph nodes for legal classification
  - §4.2.1 STRICT_STORE_COMPLIANCE enforcement (FIX-06)
  - §4.2.3 Preflight App Store compliance (advisory)

Spec Authority: v5.8 §4.2
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

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

_MAX_ITERATIONS = 5  # Max iterative refinement passes


# ═══════════════════════════════════════════════════════════════════
# §4.2 S1 Legal Gate Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S1_LEGAL)
async def s1_legal_node(state: PipelineState) -> PipelineState:
    """S1: Legal Gate — iterative classify, map regulations, assess risk.

    Spec: §4.2 v5.8
    Step 1: Iterative Scout research + Strategist classification (up to 5 passes)
    Step 2: Compile risk register + compliance matrix + sources bibliography
    Step 3: Handle blocked features (COPILOT 4-option gate)
    Step 4: P0 halt gate with COPILOT resolution menu
    Step 5: Generate 9-document legal dossier PDF
    Step 6: Generate in-app legal text bundle
    Step 7: Preflight App Store compliance (advisory)
    Step 8: STRICT_STORE_COMPLIANCE enforcement (FIX-06)
    Step 9: Mother Memory graph node write

    Cost target: <$1.50
    """
    from factory.core.stage_enrichment import enrich_prompt, store_stage_insight

    # FIX-MEM Issue #16: read prior decisions before starting stage work
    # so the AI has cross-session context (e.g. a previous S1 attempt).
    try:
        from factory.memory.mother_memory import recall_stage_context
        _prior_ctx = await recall_stage_context(
            project_id=state.project_id,
            operator_id=state.operator_id or "",
            for_stage="S1_LEGAL",
        )
        if _prior_ctx:
            state.project_metadata["s1_prior_context"] = _prior_ctx
            logger.debug(f"[{state.project_id}] S1: recalled prior memory context ({len(_prior_ctx)} chars)")
    except Exception as _mm_err:
        logger.debug(f"[{state.project_id}] S1: recall_stage_context skipped: {_mm_err}")

    requirements = state.s0_output or {}
    app_name = requirements.get("app_name") or state.idea_name or state.project_id
    app_category = requirements.get("app_category", "other")

    # ── Step 1: Iterative Scout research + Strategist classification ──
    legal_output, legal_research, iterations_run = await _iterative_classify(
        state, requirements, app_name, app_category,
    )

    # ── Step 2: Compile structured outputs ──
    legal_output["risk_register"] = _build_risk_register(legal_output)
    legal_output["compliance_matrix"] = _build_compliance_matrix(legal_output)
    legal_output["sources_bibliography"] = await _extract_sources(
        state, legal_research,
    )

    # ── Step 3: Handle blocked features (COPILOT) ──
    blocked_features = [
        f for f in legal_output.get("feature_risk_assessment", [])
        if f.get("risk") == "blocked"
    ]
    if blocked_features:
        legal_output = await _handle_blocked_features(
            state, legal_output, blocked_features,
        )

    # ── Step 4: P0 halt gate ──
    if not legal_output.get("proceed", True) and legal_output.get("blocking_issues"):
        await _p0_halt_gate(state, legal_output)
        # If still halted after gate, return early
        if state.legal_halt:
            state.s1_output = legal_output
            return state

    # ── Step 5: Generate legal dossier PDF (9-doc suite) ──
    legal_output = await _generate_dossier(
        state, legal_output, legal_research, app_name, requirements,
    )

    # ── Step 6: In-app legal text bundle ──
    legal_output["inapp_legal_texts"] = await _generate_inapp_texts(
        state, requirements, app_name,
    )

    # ── Step 7: Preflight App Store compliance ──
    preflight_warnings = await _preflight_store_compliance(state)
    if preflight_warnings:
        legal_output["compliance_warnings"] = preflight_warnings
        state.warnings.extend(preflight_warnings)
        from factory.telegram.notifications import notify_operator
        await notify_operator(
            state,
            NotificationType.INFO,
            f"⚠️ App Store preflight: {len(preflight_warnings)} potential issue(s):\n"
            + "\n".join(
                f"  • {w.get('rule', '?')}: {w.get('detail', '')}"
                for w in preflight_warnings[:5]
            ),
        )

    # ── Step 8: STRICT_STORE_COMPLIANCE enforcement (FIX-06) ──
    if STRICT_STORE_COMPLIANCE and preflight_warnings:
        high_sev = [w for w in preflight_warnings if w.get("severity") == "high"]
        if high_sev:
            confidence = _calculate_compliance_confidence(preflight_warnings)
            if confidence > COMPLIANCE_CONFIDENCE_THRESHOLD:
                state.legal_halt = True
                state.legal_halt_reason = (
                    f"[FIX-06] Compliance blocker(s) at confidence "
                    f"{confidence:.2f}: {len(high_sev)} issue(s)"
                )

    # ── Step 9: Mother Memory graph node ──
    await _write_to_mother_memory(state, legal_output)

    # ── Store insight for future projects ──
    await store_stage_insight(
        "s1_legal", state,
        fact=(
            f"App '{app_name}' ({app_category}): risk={legal_output.get('overall_risk')}, "
            f"bodies={legal_output.get('regulatory_bodies')}, "
            f"docs={legal_output.get('legal_docs_generated', [])}, "
            f"iterations={iterations_run}"
        ),
        category="legal",
        ttl_hours=720,
    )

    legal_output["iterations_run"] = iterations_run

    # ── Quality Gate (Issue 17) ──────────────────────────────────────
    # Skip gates in dry-run / test mode (DRY_RUN=true).
    from factory.core.dry_run import is_dry_run
    if not is_dry_run():
        from factory.core.quality_gates import (
            check_no_placeholders, check_min_length, check_min_list,
            raise_if_failed, QualityGateFailure, GateResult,
        )
        from factory.core.halt import HaltCode, HaltReason, set_halt

        # Quality thresholds (production-calibrated):
        # DocuGen generates 6–8 sections × 400–700 words each.
        # Fallback sections (_fallback_legal_section) produce ~2 500 chars.
        # BASIC:     3 000 chars / 3 docs (with fallback template guarantee)
        # Non-BASIC: 6 000 chars / 4 docs (full AI-generated, richer output)
        from factory.core.mode_router import MasterMode
        _is_basic = getattr(state, "master_mode", MasterMode.BASIC) == MasterMode.BASIC
        _min_chars = 3000 if _is_basic else 6000
        _min_docs  = 3    if _is_basic else 4

        _gate_results = []
        docs: dict = state.legal_documents or {}
        for doc_name, content in docs.items():
            if not isinstance(content, str):
                continue
            _gate_results.append(check_no_placeholders(content, doc_name))
            _gate_results.append(check_min_length(content, _min_chars, doc_name))

        doc_count = len([k for k, v in docs.items() if isinstance(v, str) and len(v) > 100])
        _gate_results.append(GateResult(
            name="min_doc_count",
            passed=doc_count >= _min_docs,
            observed=doc_count,
            required=_min_docs,
            message=f"Need >={_min_docs} legal documents, got {doc_count}" if doc_count < _min_docs else "",
        ))

        try:
            raise_if_failed("S1_LEGAL", _gate_results, recommended_action="retry S1_LEGAL")
        except QualityGateFailure as qgf:
            set_halt(state, HaltReason(
                code=HaltCode.QUALITY_GATE_FAILED,
                title="Legal documents failed quality gate",
                detail=qgf.format_for_telegram()[:600],
                stage="S1_LEGAL",
                failing_gate="legal_content",
                remediation_steps=["Retry S1 with /continue", "/cancel"],
            ))
            state.legal_halt = True
            state.s1_output = legal_output
            return state

    state.s1_output = legal_output

    # ── Mother Memory: full legal snapshot → fan-out to ALL backends ─
    try:
        from factory.memory.mother_memory import (
            store_legal_snapshot,
            store_pipeline_state_snapshot,
        )
        await store_legal_snapshot(state.project_id, {
            "operator_id": state.operator_id,
            **legal_output,
        })
        await store_pipeline_state_snapshot(state.project_id, "s1_legal", legal_output)
    except Exception as _mm_err:
        logger.debug(f"[{state.project_id}] S1 mother-memory snapshot failed (non-fatal): {_mm_err}")

    logger.info(
        f"[{state.project_id}] S1 complete: "
        f"risk={legal_output.get('overall_risk')}, "
        f"proceed={legal_output.get('proceed')}, "
        f"iterations={iterations_run}, "
        f"warnings={len(preflight_warnings)}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# Step 1: Iterative Classification Loop
# ═══════════════════════════════════════════════════════════════════


async def _iterative_classify(
    state: PipelineState,
    requirements: dict,
    app_name: str,
    app_category: str,
) -> tuple[dict, str, int]:
    """Run Scout research + Strategist classification with iterative refinement.

    Returns (legal_output, accumulated_research, iterations_run).
    Converges early if proceed=True and no blocking issues.
    Max _MAX_ITERATIONS passes.
    """
    from factory.core.stage_enrichment import enrich_prompt

    legal_research = ""
    legal_output: dict = {}
    prev_risk: Optional[str] = None

    for iteration in range(_MAX_ITERATIONS):
        # ── Scout research (initial + targeted follow-up) ──
        if iteration == 0:
            scout_query = _build_initial_scout_query(requirements, app_name, app_category)
        else:
            scout_query = _build_followup_scout_query(
                requirements, legal_output, iteration,
            )

        enriched_query = await enrich_prompt(
            "s1_legal", scout_query, state, scout=True, scout_query=scout_query,
        )
        research_part = await call_ai(
            role=AIRole.SCOUT,
            prompt=enriched_query,
            state=state,
            action="general",
        )
        legal_research += f"\n\n--- Iteration {iteration + 1} Research ---\n" + research_part

        # ── Strategist classifies ──
        legal_fields = [
            "app_description", "app_category", "features_must", "features_nice",
            "has_payments", "has_user_accounts", "has_location",
            "has_notifications", "has_realtime", "target_market",
            "target_platforms",
        ]
        legal_req = {k: requirements.get(k) for k in legal_fields if k in requirements}

        from factory.pipeline.stage_chain import inject_chain_context as _inject_cc
        _legal_base_prompt = (
            f"LEGAL CLASSIFICATION — Iteration {iteration + 1}/{_MAX_ITERATIONS}.\n\n"
            f"App: {app_name}\n"
            f"Requirements:\n{json.dumps(legal_req, indent=2)[:3000]}\n\n"
            f"KSA regulatory research (all iterations):\n{legal_research[:4000]}\n\n"
            f"Previous iteration risk: {prev_risk or 'N/A'}\n\n"
            f"Classify and decide. Return ONLY valid JSON:\n"
            f'{{\n'
            f'  "data_classification": "public|internal|confidential|restricted",\n'
            f'  "regulatory_bodies": ["PDPL", "CST", "SAMA", "NDMO", "NCA"],\n'
            f'  "compliance_matrix": {{\n'
            f'    "PDPL": "compliant|partial|non-compliant|n/a",\n'
            f'    "CST": "compliant|partial|non-compliant|n/a",\n'
            f'    "SAMA": "compliant|partial|non-compliant|n/a",\n'
            f'    "NDMO": "compliant|partial|non-compliant|n/a",\n'
            f'    "NCA": "compliant|partial|non-compliant|n/a"\n'
            f'  }},\n'
            f'  "payment_mode": "SANDBOX",\n'
            f'  "feature_risk_assessment": [\n'
            f'    {{"feature": "...", "risk": "clear|flagged|blocked", '
            f'"reason": "...", "action": "..."}}\n'
            f'  ],\n'
            f'  "required_legal_docs": ["privacy_policy", "terms_of_service", "eula", "data_deletion_policy"],\n'
            f'  "required_licenses": ["none"],\n'
            f'  "cross_border_data": false,\n'
            f'  "sama_sandbox_required": false,\n'
            f'  "overall_risk": "low|medium|high|critical",\n'
            f'  "proceed": true,\n'
            f'  "blocking_issues": [],\n'
            f'  "unresolved_questions": []\n'
            f'}}'
        )
        decision_text = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=_inject_cc(_legal_base_prompt, state, current_stage="s1_legal", compact=True),
            state=state,
            action="decide_legal",
        )

        # Detect exhausted-provider response before attempting JSON parse
        _EXHAUSTED_MARKERS = ("[all-providers-exhausted]", "[MOCK:")
        _is_exhausted = any(decision_text.startswith(m) for m in _EXHAUSTED_MARKERS)
        if _is_exhausted:
            logger.warning(
                f"[{state.project_id}] S1 iter {iteration + 1}: all AI providers exhausted "
                f"— using default legal output and continuing"
            )
            if not legal_output:
                legal_output = _default_legal_output()
            # Don't break immediately; still accumulate more research if iterations remain
            prev_risk = legal_output.get("overall_risk", "medium")
            continue

        try:
            legal_output = json.loads(decision_text)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"[{state.project_id}] S1 iter {iteration + 1}: Strategist JSON parse failed"
            )
            if not legal_output:
                legal_output = _default_legal_output()
            break

        current_risk = legal_output.get("overall_risk", "medium")
        has_blocking = bool(legal_output.get("blocking_issues"))
        has_unresolved = bool(legal_output.get("unresolved_questions"))

        # Converge if stable
        if legal_output.get("proceed", True) and not has_blocking and not has_unresolved:
            logger.info(
                f"[{state.project_id}] S1 converged at iteration {iteration + 1}"
            )
            return legal_output, legal_research, iteration + 1

        # Converge if risk unchanged and not first iteration
        if iteration > 0 and current_risk == prev_risk and not has_unresolved:
            logger.info(
                f"[{state.project_id}] S1 stable at iteration {iteration + 1} (risk={current_risk})"
            )
            return legal_output, legal_research, iteration + 1

        prev_risk = current_risk
        logger.info(
            f"[{state.project_id}] S1 iter {iteration + 1}: "
            f"risk={current_risk}, blocking={has_blocking}, "
            f"unresolved={len(legal_output.get('unresolved_questions', []))}"
        )

    return legal_output, legal_research, _MAX_ITERATIONS


def _build_initial_scout_query(
    requirements: dict,
    app_name: str,
    app_category: str,
) -> str:
    market = requirements.get("target_market", "ksa")
    market_label = {
        "ksa": "Saudi Arabia", "gcc": "GCC region",
        "global": "Global/KSA primary", "custom": "custom market",
    }.get(market, market)

    return (
        f"What regulations apply to this app in {market_label}?\n\n"
        f"App: {requirements.get('app_description', app_name)}\n"
        f"Category: {app_category}\n"
        f"Has payments: {requirements.get('has_payments', False)}\n"
        f"Has user accounts: {requirements.get('has_user_accounts', False)}\n"
        f"Has location: {requirements.get('has_location', False)}\n"
        f"Has realtime data: {requirements.get('has_realtime', False)}\n\n"
        f"Check: PDPL (data protection), CST (telecom/app registration), "
        f"SAMA (financial services), NDMO (data governance), NCA (cybersecurity), "
        f"SDAIA (AI governance), Ministry of Commerce (business licensing), "
        f"Apple App Store guidelines, Google Play policies.\n"
        f"Return specific requirements with article/section citations."
    )


def _build_followup_scout_query(
    requirements: dict,
    legal_output: dict,
    iteration: int,
) -> str:
    unresolved = legal_output.get("unresolved_questions", [])
    blocking = legal_output.get("blocking_issues", [])
    focus = (
        f"Unresolved questions: {unresolved}\n"
        f"Blocking issues: {blocking}"
        if unresolved or blocking
        else f"Verify and confirm findings for overall_risk={legal_output.get('overall_risk')}"
    )
    return (
        f"Follow-up legal research (iteration {iteration + 1}).\n\n"
        f"App category: {requirements.get('app_category', 'other')}\n"
        f"Previous classification risk: {legal_output.get('overall_risk')}\n\n"
        f"Focus areas:\n{focus}\n\n"
        f"Provide specific regulatory citations and definitive answers."
    )


# ═══════════════════════════════════════════════════════════════════
# Step 2: Structured Outputs
# ═══════════════════════════════════════════════════════════════════


def _build_risk_register(legal_output: dict) -> list[dict]:
    """Build structured risk register from feature risk assessment."""
    items = []
    for f in legal_output.get("feature_risk_assessment", []):
        items.append({
            "feature":    f.get("feature", "unknown"),
            "risk_level": f.get("risk", "clear"),
            "reason":     f.get("reason", ""),
            "mitigation": f.get("action", ""),
        })
    for issue in legal_output.get("blocking_issues", []):
        items.append({
            "feature":    "Blocking Issue",
            "risk_level": "critical",
            "reason":     str(issue),
            "mitigation": "Legal review required before proceeding",
        })
    return items


def _build_compliance_matrix(legal_output: dict) -> dict:
    """Return compliance matrix (body → status) from Strategist output."""
    # Prefer Strategist-provided matrix; fall back to heuristic derivation
    if "compliance_matrix" in legal_output:
        return legal_output["compliance_matrix"]

    risk = legal_output.get("overall_risk", "medium")
    status_map = {"low": "compliant", "medium": "partial", "high": "non-compliant"}
    default_status = status_map.get(risk, "partial")

    matrix: dict = {}
    for body in legal_output.get("regulatory_bodies", []):
        matrix[body] = default_status
    return matrix


async def _extract_sources(state: PipelineState, research_text: str) -> list[dict]:
    """Extract cited sources from research text using Quick Fix."""
    if not research_text.strip():
        return []
    try:
        raw = await call_ai(
            role=AIRole.QUICK_FIX,
            prompt=(
                f"Extract all regulatory sources cited in this legal research text. "
                f"Return ONLY a JSON array, no other text:\n"
                f'[{{"title": "PDPL Article 23", "type": "law|regulation|guideline|website", '
                f'"authority": "SDAIA|CST|SAMA|NCA|NDMO|MoC|Other"}}]\n\n'
                f"Research text (excerpt):\n{research_text[:3000]}"
            ),
            state=state,
            action="general",
        )
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed[:30]  # cap at 30 sources
    except Exception as e:
        logger.debug(f"[{state.project_id}] Sources extraction non-critical: {e}")
    return []


# ═══════════════════════════════════════════════════════════════════
# Step 3: Blocked Features Gate
# ═══════════════════════════════════════════════════════════════════


async def _handle_blocked_features(
    state: PipelineState,
    legal_output: dict,
    blocked_features: list[dict],
) -> dict:
    """COPILOT: present 4-option blocked-features decision."""
    blocked_names = [f.get("feature", "?") for f in blocked_features]

    if state.autonomy_mode == AutonomyMode.COPILOT:
        from factory.telegram.decisions import present_decision
        resolution = await present_decision(
            state=state,
            decision_type="s1_blocked_features",
            question=(
                f"⚖️ *Blocked features detected*\n\n"
                f"Features: {', '.join(blocked_names)}\n\n"
                f"How should we proceed?"
            ),
            options=[
                {"label": "✂️ Remove blocked features",       "value": "remove"},
                {"label": "📋 Apply for license (pause)",    "value": "license"},
                {"label": "🔒 SANDBOX mode (proceed anyway)","value": "sandbox"},
                {"label": "❌ Cancel project",                "value": "cancel"},
            ],
            recommended=0,
        )

        if resolution == "remove":
            legal_output["feature_risk_assessment"] = [
                f for f in legal_output.get("feature_risk_assessment", [])
                if f.get("risk") != "blocked"
            ]
            legal_output["blocked_features_removed"] = blocked_names
        elif resolution == "license":
            legal_output["awaiting_license"] = True
            legal_output["license_features"] = blocked_names
        elif resolution == "cancel":
            state.legal_halt = True
            state.legal_halt_reason = "Operator cancelled — blocked features cannot proceed"
        # sandbox: continue as-is
    else:
        # AUTOPILOT: log and continue in SANDBOX
        logger.warning(
            f"[{state.project_id}] AUTOPILOT: blocked features {blocked_names} → SANDBOX mode"
        )
        legal_output["blocked_features_autopilot_sandbox"] = blocked_names

    return legal_output


# ═══════════════════════════════════════════════════════════════════
# Step 4: P0 Halt Gate
# ═══════════════════════════════════════════════════════════════════


async def _p0_halt_gate(state: PipelineState, legal_output: dict) -> None:
    """Handle P0 legal halt with COPILOT resolution menu."""
    blocking = legal_output.get("blocking_issues", ["Unknown blocking issue"])
    halt_reason = (
        f"S1 Legal Gate: Blocking issues: {blocking}"
    )

    if state.autonomy_mode == AutonomyMode.COPILOT:
        from factory.telegram.decisions import present_decision
        from factory.telegram.notifications import send_telegram_message

        await send_telegram_message(
            state.operator_id,
            f"🚨 *P0 Legal Halt*\n\n"
            f"Blocking issues detected:\n"
            + "\n".join(f"• {issue}" for issue in blocking[:5])
            + "\n\nChoose how to resolve:",
        )

        resolution = await present_decision(
            state=state,
            decision_type="s1_p0_halt_resolution",
            question="How would you like to resolve the P0 legal halt?",
            options=[
                {"label": "✂️ Remove problematic feature",   "value": "remove"},
                {"label": "⚖️ Accept risk (legal review later)", "value": "accept"},
                {"label": "📋 Apply for exemption (pause)",  "value": "exemption"},
                {"label": "❌ Halt — do not proceed",         "value": "halt"},
            ],
            recommended=1,  # accept by default to unblock
        )

        if resolution in ("remove", "accept"):
            # Clear the halt — operator accepted responsibility
            legal_output["proceed"] = True
            legal_output["p0_resolved_by"] = resolution
            legal_output["blocking_issues_acknowledged"] = blocking
            logger.info(
                f"[{state.project_id}] P0 halt resolved by operator: {resolution}"
            )
        elif resolution == "exemption":
            state.legal_halt = True
            state.legal_halt_reason = (
                f"Awaiting regulatory exemption for: {blocking}"
            )
        else:  # halt
            state.legal_halt = True
            state.legal_halt_reason = halt_reason
    else:
        # AUTOPILOT: set halt
        state.legal_halt = True
        state.legal_halt_reason = halt_reason
        from factory.telegram.notifications import send_telegram_message
        await send_telegram_message(
            state.operator_id,
            f"🚨 *P0 Legal Halt* [{state.project_id}]\n\n"
            f"Blocking issues:\n"
            + "\n".join(f"• {issue}" for issue in blocking[:5])
            + "\n\nPipeline paused. Use /force_continue <reason> to override.",
        )


# ═══════════════════════════════════════════════════════════════════
# Step 5: Legal Dossier PDF (9-document suite)
# ═══════════════════════════════════════════════════════════════════


async def _generate_dossier(
    state: PipelineState,
    legal_output: dict,
    legal_research: str,
    app_name: str,
    requirements: dict,
) -> dict:
    """Generate DocuGen 9-document suite + PDF dossier."""
    try:
        from factory.legal.docugen import generate_legal_documents
        from factory.legal.pdf_generator import (
            generate_legal_dossier_pdf,
            upload_legal_pdf_to_supabase,
        )

        business_model = requirements.get("app_category", "general")
        legal_docs = await generate_legal_documents(
            state,
            blueprint_data={
                "app_name": app_name,
                "business_model": business_model,
                # Pass full requirements so DocuGen can tailor each section
                "requirements": requirements,
                # Pass S1 classification so DocuGen knows risk level, required docs,
                # compliance matrix, and feature risk assessments
                "legal_classification": legal_output,
                # Pass accumulated research (regulation citations, Scout findings)
                "legal_research": legal_research,
            },
        )

        pdf_path = await generate_legal_dossier_pdf(
            project_id=state.project_id,
            app_name=app_name,
            legal_output=legal_output,
            legal_research=legal_research,
            legal_documents=legal_docs,
            operator_id=state.operator_id,
        )

        legal_output["legal_dossier_pdf_path"] = pdf_path
        legal_output["legal_docs_generated"] = list(legal_docs.keys())

        pdf_url = await upload_legal_pdf_to_supabase(state.project_id, pdf_path)
        if pdf_url:
            legal_output["legal_dossier_url"] = pdf_url

        from factory.telegram.notifications import notify_operator
        await notify_operator(
            state,
            NotificationType.INFO,
            f"📋 Legal Dossier ({len(legal_docs)} docs):\n"
            f"{', '.join(legal_docs.keys())}\n"
            + (f"\nURL: {pdf_url}" if pdf_url else f"\nPath: {pdf_path}"),
        )
        logger.info(
            f"[{state.project_id}] Legal Dossier: {len(legal_docs)} docs, {pdf_path}"
        )

    except Exception as e:
        logger.warning(
            f"[{state.project_id}] Legal dossier generation failed (non-fatal): {e}"
        )

    return legal_output


# ═══════════════════════════════════════════════════════════════════
# Step 6: In-App Legal Text Bundle
# ═══════════════════════════════════════════════════════════════════


async def _generate_inapp_texts(
    state: PipelineState,
    requirements: dict,
    app_name: str,
) -> dict:
    """Generate short in-app legal UI texts (consent banners, notices, etc.).

    These are the short strings displayed inside the app UI itself,
    not the full legal documents. Used by S4 CodeGen for PDPL compliance.
    """
    try:
        features_summary = ", ".join(requirements.get("features_must", [])[:5])
        raw = await call_ai(
            role=AIRole.QUICK_FIX,
            prompt=(
                f"Generate short in-app legal UI texts for '{app_name}'. "
                f"App features: {features_summary}. "
                f"Has payments: {requirements.get('has_payments', False)}. "
                f"Has location: {requirements.get('has_location', False)}. "
                f"Has user accounts: {requirements.get('has_user_accounts', True)}.\n\n"
                f"Return ONLY valid JSON:\n"
                f'{{\n'
                f'  "consent_banner": "short consent text (1 sentence)",\n'
                f'  "privacy_notice": "1-sentence data use summary",\n'
                f'  "data_collection_notice": "what data and why (1-2 sentences)",\n'
                f'  "payment_disclaimer": "payment processing notice (1 sentence, if has_payments)",\n'
                f'  "location_notice": "location use explanation (1 sentence, if has_location)",\n'
                f'  "age_gate_text": "minimum age notice",\n'
                f'  "deletion_rights_text": "PDPL Art. 16 data deletion right (1 sentence)"\n'
                f'}}'
            ),
            state=state,
            action="general",
        )
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        logger.debug(f"[{state.project_id}] In-app texts generation non-critical: {e}")

    # Minimal fallback
    return {
        "consent_banner": (
            f"By using {app_name}, you agree to our Terms of Service and Privacy Policy."
        ),
        "privacy_notice": "We collect only the data needed to operate the service.",
        "data_collection_notice": (
            "Your data is processed in accordance with Saudi Arabia's PDPL."
        ),
        "deletion_rights_text": (
            "You may request deletion of your data at any time by contacting support."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# Step 9: Mother Memory Graph Node
# ═══════════════════════════════════════════════════════════════════


async def _write_to_mother_memory(
    state: PipelineState,
    legal_output: dict,
) -> None:
    """Write legal classification to Mother Memory for cross-project learning."""
    try:
        from factory.memory.mother_memory import store_pipeline_decision
        await store_pipeline_decision(
            operator_id=state.operator_id,
            project_id=state.project_id,
            stage="s1_legal",
            decision_type="legal_classification",
            decision={
                "data_classification": legal_output.get("data_classification"),
                "regulatory_bodies":   legal_output.get("regulatory_bodies"),
                "compliance_matrix":   legal_output.get("compliance_matrix"),
                "overall_risk":        legal_output.get("overall_risk"),
                "required_legal_docs": legal_output.get("required_legal_docs"),
                "payment_mode":        legal_output.get("payment_mode"),
                "cross_border_data":   legal_output.get("cross_border_data"),
                "sama_sandbox_required": legal_output.get("sama_sandbox_required"),
            },
            reasoning=(
                f"Legal classification for {state.idea_name or state.project_id}: "
                f"risk={legal_output.get('overall_risk')}, "
                f"proceed={legal_output.get('proceed')}"
            ),
        )
    except Exception as e:
        logger.debug(f"[{state.project_id}] Mother Memory write (non-critical): {e}")


# ═══════════════════════════════════════════════════════════════════
# §4.2.3 Preflight Compliance
# ═══════════════════════════════════════════════════════════════════


async def _preflight_store_compliance(state: PipelineState) -> list[dict]:
    """Query current Apple/Google guidelines for known rejection triggers.

    Spec: §4.2.3 — advisory only, does not block pipeline.
    """
    warnings: list[dict] = []
    requirements = state.s0_output or {}
    app_desc = requirements.get("app_description", "")

    if not app_desc or state.total_cost_usd >= 25.00:
        return warnings

    try:
        raw = await call_ai(
            role=AIRole.SCOUT,
            prompt=(
                f"Check Apple App Store Review Guidelines and Google Play policies "
                f"for rejection risks for this app: '{app_desc[:300]}'. "
                f"Focus on: 3.1.1 (IAP), 5.1.1 (Data), 4.2 (Minimum Functionality), "
                f"2.1 (Completeness). "
                f'Return ONLY JSON array: [{{"rule": "...", "risk_level": "low|medium|high", '
                f'"recommendation": "..."}}]'
            ),
            state=state,
            action="general",
        )
        parsed = json.loads(raw)
        for item in parsed:
            warnings.append({
                "source": "scout_guidelines",
                "rule": item.get("rule", ""),
                "detail": item.get("recommendation", ""),
                "severity": item.get("risk_level", "medium"),
            })
    except Exception as e:
        logger.debug(f"Preflight compliance non-critical: {e}")

    return warnings


def _calculate_compliance_confidence(warnings: list[dict]) -> float:
    """Estimate confidence of compliance blockers. Spec: §4.2.1"""
    if not warnings:
        return 0.0
    high_count = sum(
        1 for w in warnings
        if w.get("severity") == "high" and w.get("source") == "mother_memory"
    )
    return min(1.0, 0.5 + (high_count / len(warnings)) * 0.5)


def _default_legal_output() -> dict:
    """Safe default legal output for fallback scenarios."""
    return {
        "data_classification": "internal",
        "regulatory_bodies": ["PDPL", "CST"],
        "compliance_matrix": {"PDPL": "partial", "CST": "partial"},
        "payment_mode": "SANDBOX",
        "feature_risk_assessment": [],
        "required_legal_docs": [
            "privacy_policy", "terms_of_service", "eula", "data_deletion_policy",
        ],
        "required_licenses": ["none"],
        "cross_border_data": False,
        "sama_sandbox_required": False,
        "overall_risk": "medium",
        "proceed": True,
        "blocking_issues": [],
        "unresolved_questions": [],
        "parsed_by": "fallback",
    }


# Register with DAG
register_stage_node("s1_legal", s1_legal_node)
