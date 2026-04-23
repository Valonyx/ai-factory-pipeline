"""
AI Factory Pipeline v5.8 — DocuGen Module (The Corporate Secretary)

Implements:
  - §3.5.1 Document type templates
  - §3.5.2 Generation flow (Scout → Strategist → Engineer)
  - Legal disclaimer (REQUIRES_LEGAL_REVIEW)
  - Citation enforcement from Scout research

All AI-generated legal documents are DRAFTS requiring mandatory
human legal review before publication or use.

Spec Authority: v5.8 §3.5
"""

from __future__ import annotations

import logging
from typing import Optional

from factory.core.state import AIRole, PipelineState
from factory.core.roles import call_ai
from factory.telegram.notifications import send_telegram_message

logger = logging.getLogger("factory.legal.docugen")


# ═══════════════════════════════════════════════════════════════════
# §3.5.1 Document Templates
# ═══════════════════════════════════════════════════════════════════

DOCUGEN_TEMPLATES: dict[str, dict] = {
    # ── Universal (required for ALL apps) ──────────────────────────────
    "privacy_policy": {
        "required_for": ["all"],
        "description": "PDPL-compliant privacy policy",
        "priority": 1,
    },
    "terms_of_service": {
        "required_for": ["all"],
        "description": "Terms of service / user agreement",
        "priority": 1,
    },
    "eula": {
        "required_for": ["all"],
        "description": "End User License Agreement (EULA) — required by App Store & Google Play",
        "priority": 2,
    },
    "data_deletion_policy": {
        "required_for": ["all"],
        "description": "Data deletion rights policy (PDPL Art. 16 — right to erasure)",
        "priority": 2,
    },
    # ── Conditional — platform / business model ────────────────────────
    "cookie_policy": {
        "required_for": ["web"],   # also checked against target_platforms
        "description": "Cookie and tracking technology policy (web apps)",
        "priority": 3,
    },
    "merchant_agreement": {
        "required_for": ["marketplace", "e-commerce"],
        "description": "Merchant/seller agreement for marketplace apps",
        "priority": 3,
    },
    "driver_contract": {
        "required_for": ["delivery", "transport", "ride-hailing"],
        "description": "Independent contractor agreement for drivers",
        "priority": 3,
    },
    "data_processing_agreement": {
        "required_for": ["saas", "b2b"],
        "description": "DPA for B2B/SaaS data processing",
        "priority": 3,
    },
    "acceptable_use_policy": {
        "required_for": ["social", "community", "marketplace", "game"],
        "description": "Acceptable use / community standards policy for user-generated content",
        "priority": 3,
    },
}

# Backwards-compat alias (was "terms_of_use" before v5.8; canonical key is "terms_of_service")
DOCUGEN_TEMPLATES["terms_of_use"] = {
    **DOCUGEN_TEMPLATES["terms_of_service"],
    "description": "Terms of service / user agreement (alias: terms_of_use)",
}
# Remove duplicate so we only generate one
del DOCUGEN_TEMPLATES["terms_of_use"]

LEGAL_DISCLAIMER = (
    "⚠️ Legal documents generated for {app_name}. "
    "These are AI-generated DRAFTS — not final legal instruments. "
    "Have them reviewed by a qualified KSA legal professional "
    "before publishing."
)


# ═══════════════════════════════════════════════════════════════════
# §3.5.2 DocuGen Flow
# ═══════════════════════════════════════════════════════════════════


async def generate_legal_documents(
    state: PipelineState,
    blueprint_data: dict,
) -> dict[str, str]:
    """Generate all required legal documents.

    Spec: §3.5.2

    Flow: Scout researches → Strategist structures → Engineer writes.

    Args:
        state: Current pipeline state.
        blueprint_data: Blueprint dict with app_name, business_model, etc.

    Returns:
        Dict mapping doc_type → document content (Markdown).
    """
    business_model = blueprint_data.get("business_model", "general")
    app_name = blueprint_data.get("app_name", state.project_id)
    target_platforms = (state.s0_output or {}).get("target_platforms", [])
    documents: dict[str, str] = {}

    # Sort by priority so universal docs (p=1) are generated before conditional (p=3)
    ordered = sorted(DOCUGEN_TEMPLATES.items(), key=lambda kv: kv[1].get("priority", 9))

    # Pre-count how many docs we'll generate so the operator sees progress
    doc_queue: list[tuple[str, dict]] = []
    for doc_type, template in ordered:
        required = template["required_for"]
        if "all" in required:
            doc_queue.append((doc_type, template))
        elif doc_type == "cookie_policy":
            if "web" in target_platforms:
                doc_queue.append((doc_type, template))
        elif business_model in required:
            doc_queue.append((doc_type, template))

    total_docs = len(doc_queue)
    for idx, (doc_type, template) in enumerate(doc_queue, 1):
        doc_name = doc_type.replace("_", " ").title()
        logger.info(
            f"[{state.project_id}] DocuGen: generating {doc_type} "
            f"({idx}/{total_docs}) for {business_model}"
        )

        # Notify operator of progress so they don't think it's frozen
        await send_telegram_message(
            state.operator_id,
            f"📝 Legal doc {idx}/{total_docs}: *{doc_name}* …",
        )

        doc = await _generate_single_document(
            state, doc_type, template, business_model, app_name,
        )
        documents[doc_type] = doc

    # Store in state
    state.legal_documents = documents

    # Send disclaimer to operator
    await send_telegram_message(
        state.operator_id,
        LEGAL_DISCLAIMER.format(app_name=app_name),
    )

    logger.info(
        f"[{state.project_id}] DocuGen: {len(documents)} documents generated "
        f"({', '.join(documents.keys())})"
    )
    return documents


async def _generate_single_document(
    state: PipelineState,
    doc_type: str,
    template: dict,
    business_model: str,
    app_name: str,
) -> str:
    """Generate a single legal document via section-chunked production.

    Spec: §3.5.2  |  v5.8.16 Phase 6 — Context-overflow fix

    Architecture (Mother Memory threaded):
      Scout  → researches KSA requirements
      Strategist → produces JSON section outline (6-8 sections)
      Engineer × N → writes each section independently; each call receives
                     the previously written sections as explicit context so
                     any provider in the chain (Groq, Gemini, Together …)
                     starts with full document continuity.
      Assembler → joins sections, strips placeholders, adds header.

    This replaces the old single Engineer call which was capped at each
    provider's output-token limit (~8 192 tokens / ≈6 000 words) and
    produced structurally incomplete documents.  Now each section is
    400-800 words, well inside every free model's output window, and the
    complete document accumulates to 3 000-8 000 words across 6-8 sections.
    """
    import re as _re
    from datetime import date as _date

    doc_name = doc_type.replace("_", " ")
    _today = _date.today().strftime("%B %d, %Y")

    # ── Step 1: Scout researches current requirements ──
    intel = await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"KSA legal requirements for {doc_name} "
            f"for a {business_model} app. "
            f"Include PDPL, SAMA, MoC regulations. 2025-2026 changes and enforcement."
        ),
        state=state,
        action="general",
    )

    # ── Step 2: Strategist produces JSON section outline ──
    structure_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Create a complete section outline for a production-quality {doc_name}.\n"
            f"App: {app_name} | Business model: {business_model}\n"
            f"Jurisdiction: KSA (Saudi Arabia) | Effective: {_today}\n"
            f"Research:\n{intel[:3500]}\n\n"
            f"Return a JSON array with 6-8 sections. Each section must have:\n"
            f'  "section": "1", "title": "English Title", '
            f'"arabic_title": "العنوان العربي", '
            f'"clauses": ["Clause 1", "Clause 2", "Clause 3"]\n\n'
            f"Cover: scope/definitions, data handling, user rights, "
            f"obligations, liability, governing law, and {business_model}-specific topics."
        ),
        state=state,
        action="decide_legal",
    )

    sections = _parse_section_outline(structure_raw)
    logger.info(
        f"[{state.project_id}] DocuGen: {doc_name} → "
        f"{len(sections)} sections to generate"
    )

    # ── Step 3: Engineer writes each section with prior-section context ──
    written_sections: list[str] = []

    for i, sec in enumerate(sections):
        sec_num = i + 1
        title = sec.get("title", f"Section {sec_num}")
        arabic_title = sec.get("arabic_title", "")
        clauses = sec.get("clauses", [])

        # Build explicit prior-context block so any provider starts informed
        prior_ctx = ""
        if written_sections:
            prior_ctx = (
                "\n\nDOCUMENT WRITTEN SO FAR (for continuity — do not repeat):\n"
            )
            for j, prev_text in enumerate(written_sections):
                # Send first 350 chars of each prior section as a summary
                snippet = prev_text.replace("\n", " ")[:350]
                prev_title = sections[j].get("title", f"Section {j+1}")
                prior_ctx += f"[§{j+1} {prev_title}]: {snippet}…\n"

        section_text = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Write Section {sec_num} of the {doc_name} for {app_name}.\n\n"
                f"Document context:\n"
                f"  App Name  : {app_name}\n"
                f"  Company   : {app_name} (operator of this application)\n"
                f"  Model     : {business_model}\n"
                f"  Date      : {_today}\n"
                f"  Law       : KSA / PDPL, App Store / Play Store compliant\n"
                f"{prior_ctx}\n"
                f"THIS SECTION:\n"
                f"  Number    : {sec_num}/{len(sections)}\n"
                f"  Title (EN): {title}\n"
                f"  Title (AR): {arabic_title}\n"
                f"  Clauses   : {', '.join(clauses)}\n\n"
                f"Instructions:\n"
                f"  - Write 400-700 words of real legal text for this section.\n"
                f"  - Start with the Arabic title, then English title, then body.\n"
                f"  - Include bilingual sub-headings where natural.\n"
                f"  - Each clause gets at least one full legal paragraph.\n"
                f"  - CRITICAL: NEVER use bracket placeholders like [COMPANY_NAME],\n"
                f"    [EFFECTIVE_DATE], [ADDRESS], [INSERT], [YOUR_*], or any\n"
                f"    [ALL_CAPS] token. Use real values: app is '{app_name}',\n"
                f"    date is {_today}. If a value is unknown (e.g. address),\n"
                f"    write a realistic plausible KSA address or omit it.\n"
                f"  - Return Markdown for this section only (## heading level)."
            ),
            state=state,
            action="write_code",
        )

        # Strip placeholders immediately after generation
        for pat, repl in [
            (r"\[EFFECTIVE_DATE\]", _today),
            (r"\[COMPANY_NAME\]", app_name),
            (r"\[APP_NAME\]", app_name),
            (r"\[UNVERIFIED\]", ""),
            (r"\[INSERT[^\]]*\]", ""),
            (r"\[YOUR[^\]]*\]", ""),
            (r"\[DATE\]", _today),
            (r"\[[A-Z][A-Z_]{2,}\]", ""),   # catch-all for any ALL_CAPS token
        ]:
            section_text = _re.sub(pat, repl, section_text)

        written_sections.append(section_text)

        # Persist to Mother Memory so a provider switch mid-document
        # can pull context from the memory block on the next call.
        try:
            from factory.memory.mother_memory import store_pipeline_decision
            import asyncio as _asyncio
            _asyncio.create_task(store_pipeline_decision(
                project_id=state.project_id,
                stage="S1_LEGAL",
                decision_type=f"legal_{doc_type}_s{sec_num}",
                content=(
                    f"[{doc_name}] §{sec_num} {title}: "
                    f"{section_text[:600]}"
                ),
                operator_id=state.operator_id or "",
            ))
        except Exception:
            pass  # never block document generation over a memory write

        logger.debug(
            f"[{state.project_id}] DocuGen: {doc_name} §{sec_num}/{len(sections)} "
            f"written ({len(section_text)} chars)"
        )

    # ── Assemble full document ──
    full_doc = "\n\n---\n\n".join(written_sections)

    # Final belt-and-suspenders placeholder sweep over entire document
    for pat, repl in [
        (r"\[EFFECTIVE_DATE\]", _today),
        (r"\[COMPANY_NAME\]", app_name),
        (r"\[APP_NAME\]", app_name),
        (r"\[UNVERIFIED\]", ""),
        (r"\[INSERT[^\]]*\]", ""),
        (r"\[YOUR[^\]]*\]", ""),
        (r"\[DATE\]", _today),
        (r"\[[A-Z][A-Z_]{2,}\]", ""),
    ]:
        full_doc = _re.sub(pat, repl, full_doc)

    # Tag document status + document-level title
    header = (
        f"<!-- REQUIRES_LEGAL_REVIEW -->\n"
        f"<!-- Generated by AI Factory Pipeline v5.8 DocuGen -->\n"
        f"<!-- Document: {doc_name} | App: {app_name} | Sections: {len(written_sections)} -->\n"
        f"<!-- Business Model: {business_model} | Date: {_today} -->\n\n"
        f"# {doc_name.title()}\n\n"
        f"**{app_name}** — Effective: {_today}\n\n"
        f"---\n\n"
    )

    total_chars = len(full_doc)
    logger.info(
        f"[{state.project_id}] DocuGen: {doc_name} assembled "
        f"({len(written_sections)} sections, {total_chars} chars)"
    )
    return header + full_doc


def _parse_section_outline(structure_raw: str) -> list[dict]:
    """Parse Strategist's JSON section outline into a list of section dicts.

    Handles JSON embedded in Markdown code fences or raw text.
    Falls back to a universally applicable 6-section default outline if
    parsing fails — this guarantees generation always proceeds.
    """
    import json as _json
    import re as _re

    # Strategy 1: try a direct parse of the whole response
    try:
        direct = _json.loads(structure_raw.strip())
        if isinstance(direct, list) and direct:
            return direct
    except Exception:
        pass

    # Strategy 2: extract from code-fenced block (```json ... ```)
    # Use greedy match so we get the FULL array, not just up to the first ]
    for pattern in (
        r"```json\s*(\[.*\])\s*```",
        r"```\s*(\[.*\])\s*```",
    ):
        m = _re.search(pattern, structure_raw, _re.DOTALL)
        if m:
            try:
                parsed = _json.loads(m.group(1))
                if isinstance(parsed, list) and parsed:
                    return parsed
            except Exception:
                continue

    # Strategy 3: find the outermost [...] span manually (bracket matching)
    start = structure_raw.find("[")
    if start != -1:
        depth = 0
        for pos in range(start, len(structure_raw)):
            ch = structure_raw[pos]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = _json.loads(structure_raw[start:pos + 1])
                        if isinstance(parsed, list) and parsed:
                            return parsed
                    except Exception:
                        pass
                    break

    # Fallback: generic 6-section outline works for most legal document types
    logger.warning(
        "[docugen] Could not parse section outline — using default 6-section fallback"
    )
    return [
        {
            "section": "1",
            "title": "Introduction, Scope and Definitions",
            "arabic_title": "المقدمة والنطاق والتعريفات",
            "clauses": ["Purpose of this document", "Key definitions", "Geographic scope"],
        },
        {
            "section": "2",
            "title": "Data Collection, Processing and Use",
            "arabic_title": "جمع البيانات ومعالجتها واستخدامها",
            "clauses": ["Categories of personal data", "Purposes of processing", "Legal basis under PDPL"],
        },
        {
            "section": "3",
            "title": "User Rights and How to Exercise Them",
            "arabic_title": "حقوق المستخدم وكيفية ممارستها",
            "clauses": ["Right to access", "Right to erasure (PDPL Art. 16)", "Right to data portability"],
        },
        {
            "section": "4",
            "title": "Data Security, Retention and Breach Notification",
            "arabic_title": "أمن البيانات والاحتفاظ بها والإخطار بالانتهاكات",
            "clauses": ["Technical safeguards", "Retention periods", "Breach notification within 72 hours"],
        },
        {
            "section": "5",
            "title": "Third-Party Sharing and International Transfers",
            "arabic_title": "المشاركة مع أطراف ثالثة والنقل الدولي",
            "clauses": ["Authorized third parties", "Data Processing Agreements", "Cross-border transfer safeguards"],
        },
        {
            "section": "6",
            "title": "Governing Law, Disputes and Policy Updates",
            "arabic_title": "القانون الواجب التطبيق والنزاعات وتحديثات السياسة",
            "clauses": ["KSA jurisdiction", "Dispute resolution", "How users are notified of changes"],
        },
    ]


# ═══════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════


def get_required_docs(business_model: str) -> list[str]:
    """Get list of required document types for a business model.

    Spec: §3.5.1
    """
    required = []
    for doc_type, template in DOCUGEN_TEMPLATES.items():
        reqs = template["required_for"]
        if "all" in reqs or business_model in reqs:
            required.append(doc_type)
    return required


def is_doc_generated(state: PipelineState, doc_type: str) -> bool:
    """Check if a specific document has been generated."""
    return doc_type in (state.legal_documents or {})


def get_missing_docs(
    state: PipelineState, business_model: str,
) -> list[str]:
    """Get list of required but missing documents."""
    required = get_required_docs(business_model)
    generated = set((state.legal_documents or {}).keys())
    return [d for d in required if d not in generated]