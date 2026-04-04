"""
AI Factory Pipeline v5.6 — DocuGen Module (The Corporate Secretary)

Implements:
  - §3.5.1 Document type templates
  - §3.5.2 Generation flow (Scout → Strategist → Engineer)
  - Legal disclaimer (REQUIRES_LEGAL_REVIEW)
  - Citation enforcement from Scout research

All AI-generated legal documents are DRAFTS requiring mandatory
human legal review before publication or use.

Spec Authority: v5.6 §3.5
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
    "privacy_policy": {
        "required_for": ["all"],
        "description": "PDPL-compliant privacy policy",
    },
    "terms_of_use": {
        "required_for": ["all"],
        "description": "Terms of service / user agreement",
    },
    "merchant_agreement": {
        "required_for": ["marketplace", "e-commerce"],
        "description": "Merchant/seller agreement for marketplace apps",
    },
    "driver_contract": {
        "required_for": ["delivery", "transport", "ride-hailing"],
        "description": "Independent contractor agreement for drivers",
    },
    "data_processing_agreement": {
        "required_for": ["saas", "b2b"],
        "description": "DPA for B2B/SaaS data processing",
    },
}

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
    documents: dict[str, str] = {}

    for doc_type, template in DOCUGEN_TEMPLATES.items():
        required = template["required_for"]
        if "all" not in required and business_model not in required:
            continue

        logger.info(
            f"[{state.project_id}] DocuGen: generating {doc_type} "
            f"for {business_model}"
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
        f"[{state.project_id}] DocuGen: {len(documents)} documents generated"
    )
    return documents


async def _generate_single_document(
    state: PipelineState,
    doc_type: str,
    template: dict,
    business_model: str,
    app_name: str,
) -> str:
    """Generate a single legal document.

    Spec: §3.5.2

    Scout: current KSA requirements.
    Strategist: legal structure.
    Engineer: full document text.
    """
    doc_name = doc_type.replace("_", " ")

    # ── Step 1: Scout researches current requirements ──
    intel = await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"KSA legal requirements for {doc_name} "
            f"for {business_model} app. "
            f"Include PDPL, SAMA, MoC. 2025-2026 changes."
        ),
        state=state,
        action="general",
    )

    # ── Step 2: Strategist structures the document ──
    structure = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Draft structure: {doc_name}\n"
            f"Business: {business_model}\n"
            f"App: {app_name}\n"
            f"Research:\n{intel[:4000]}\n\n"
            f"Return JSON with sections and key clauses."
        ),
        state=state,
        action="decide_legal",
    )

    # ── Step 3: Engineer writes full document ──
    doc = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Write complete {doc_name}.\n"
            f"Structure:\n{structure[:4000]}\n"
            f"App: {app_name}\n"
            f"Business: {business_model}\n"
            f"Requirements: Professional legal language, "
            f"Arabic+English bilingual, PDPL compliant, "
            f"KSA jurisdiction. Include [EFFECTIVE_DATE] and "
            f"[COMPANY_NAME] placeholders. Return Markdown.\n\n"
            f"Mark any claim without a citation source as [UNVERIFIED]."
        ),
        state=state,
        action="write_code",
    )

    # Tag document status
    header = (
        f"<!-- REQUIRES_LEGAL_REVIEW -->\n"
        f"<!-- Generated by AI Factory Pipeline v5.6 DocuGen -->\n"
        f"<!-- Document: {doc_name} | App: {app_name} -->\n"
        f"<!-- Business Model: {business_model} -->\n\n"
    )

    return header + doc


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