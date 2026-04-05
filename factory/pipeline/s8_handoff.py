"""
AI Factory Pipeline v5.6 — S8 Handoff Node

Implements:
  - §4.9 S8 Handoff (legal docs, summary, delivery)
  - FIX-27 Handoff Intelligence Pack (4 per-project docs)
  - FIX-27 Per-program docs (3 docs, when all siblings complete)
  - DocuGen Module (§3.5) — legal doc generation
  - Mother Memory persistence for handoff docs

Spec Authority: v5.6 §4.9, §3.5, FIX-27
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    NotificationType,
    PipelineState,
    Stage,
    TechStack,
)
from factory.core.roles import call_ai
from factory.telegram.notifications import send_telegram_message, notify_operator
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s8_handoff")


# ═══════════════════════════════════════════════════════════════════
# §3.5 DocuGen — Legal Document Generation
# ═══════════════════════════════════════════════════════════════════

DOCUGEN_TEMPLATES: dict[str, dict] = {
    "privacy_policy":            {"required_for": ["all"]},
    "terms_of_use":              {"required_for": ["all"]},
    "merchant_agreement":        {"required_for": ["marketplace", "e-commerce"]},
    "driver_contract":           {"required_for": ["delivery", "transport", "ride-hailing"]},
    "data_processing_agreement": {"required_for": ["saas", "b2b"]},
}


async def generate_legal_documents(
    state: PipelineState, blueprint_data: dict,
) -> dict[str, str]:
    """Generate all required legal documents.

    Spec: §3.5
    Scout researches → Strategist structures → Engineer writes.
    All docs flagged REQUIRES_LEGAL_REVIEW.
    """
    business_model = blueprint_data.get("business_model", "general")
    app_name = blueprint_data.get("app_name", state.project_id)
    documents: dict[str, str] = {}

    for doc_type, template in DOCUGEN_TEMPLATES.items():
        required = template["required_for"]
        if "all" not in required and business_model not in required:
            continue

        # Scout: research current KSA requirements
        intel = await call_ai(
            role=AIRole.SCOUT,
            prompt=(
                f"KSA legal requirements for {doc_type.replace('_', ' ')} "
                f"for {business_model} app. Include PDPL, SAMA, MoC. "
                f"2025-2026 changes."
            ),
            state=state,
            action="general",
        )

        # Strategist: structure
        structure = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=(
                f"Draft structure: {doc_type.replace('_', ' ')}\n"
                f"Business: {business_model}\nApp: {app_name}\n"
                f"Research:\n{intel[:3000]}\n\n"
                f"Return JSON with sections and key clauses."
            ),
            state=state,
            action="decide_legal",
        )

        # Engineer: full document
        doc = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Write complete {doc_type.replace('_', ' ')}.\n"
                f"Structure:\n{structure[:3000]}\n"
                f"App: {app_name}\nBusiness: {business_model}\n"
                f"Requirements: Professional legal language, "
                f"Arabic+English bilingual, PDPL compliant, "
                f"KSA jurisdiction. Include [EFFECTIVE_DATE] and "
                f"[COMPANY_NAME] placeholders. Return Markdown."
            ),
            state=state,
            action="write_code",
        )
        documents[doc_type] = doc

    return documents


# ═══════════════════════════════════════════════════════════════════
# FIX-27 Handoff Intelligence Pack
# ═══════════════════════════════════════════════════════════════════

HANDOFF_DOCS = [
    "QUICK_START.md",
    "EMERGENCY_RUNBOOK.md",
    "SERVICE_MAP.md",
    "UPDATE_GUIDE.md",
]

PROGRAM_DOCS = [
    "INTEGRATION_TEST_CHECKLIST.md",
    "ARCHITECTURE_OVERVIEW.md",
    "CROSS_SERVICE_TROUBLESHOOTING.md",
]


async def generate_handoff_intelligence_pack(
    state: PipelineState, blueprint_data: dict,
) -> dict[str, str]:
    """Generate the Operator Handoff Intelligence Pack.

    Spec: §4.9, FIX-27
    Per-project: 4 docs (always generated)
    Per-program: 3 docs (when all siblings complete S8)
    All docs use real values from project state.
    """
    docs: dict[str, str] = {}

    # ── Gather project context ──
    deployments = (state.s6_output or {}).get("deployments", {})
    services = (state.s2_output or {}).get("services", {})
    env_vars = (state.s3_output or {}).get("env_vars", {})
    api_endpoints = (state.s2_output or {}).get("api_endpoints", [])
    stack = blueprint_data.get("selected_stack", "unknown")
    app_name = blueprint_data.get("app_name", state.project_id)
    app_category = blueprint_data.get("app_category", "other")
    platforms = blueprint_data.get("target_platforms", [])

    project_context = (
        f"App: {app_name}\n"
        f"Category: {app_category}\n"
        f"Stack: {stack}\n"
        f"Platforms: {', '.join(platforms)}\n"
        f"Deployments: {json.dumps(deployments, indent=2)[:2000]}\n"
        f"Services: {json.dumps(services, indent=2)[:1000]}\n"
        f"Environment Variables: {json.dumps(env_vars, indent=2)[:1000]}\n"
        f"API Endpoints: {json.dumps(api_endpoints, indent=2)[:1000]}\n"
        f"War Room activations: {1 if state.war_room_active else 0}\n"
    )

    # ── Per-Project Documents (always generated) ──

    # 1. Quick Start Guide
    docs["QUICK_START.md"] = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Generate a Quick Start Guide for a zero-IT operator.\n\n"
            f"PROJECT CONTEXT:\n{project_context}\n\n"
            f"REQUIREMENTS:\n"
            f"- Plain language, no jargon\n"
            f"- Every command must be copy-pasteable with REAL values\n"
            f"- Numbered steps: what you're doing, exact command/URL, "
            f"what success looks like, what to do if it fails\n"
            f"- Cover: accessing the app, verifying it runs, restarting, "
            f"checking logs, updating simple content, requesting a rebuild\n"
            f"- Format as Markdown\n"
        ),
        state=state,
        action="general",
    )

    # 2. Emergency Runbook
    docs["EMERGENCY_RUNBOOK.md"] = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Generate an Emergency Runbook for a zero-IT operator.\n\n"
            f"PROJECT CONTEXT:\n{project_context}\n\n"
            f"REQUIREMENTS:\n"
            f"- Cover the 8-12 most likely failure scenarios for "
            f"{stack} and these services\n"
            f"- Each scenario: symptom (plain English), cause (one "
            f"sentence), fix (exact copy-pasteable steps), escalation\n"
            f"- Include: app unreachable, API errors, auth failures, "
            f"third-party SDK issues, cost alerts\n"
            f"- Format as Markdown with clear section headers\n"
        ),
        state=state,
        action="general",
    )

    # 3. Service Map
    docs["SERVICE_MAP.md"] = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Generate a Service Map for a zero-IT operator.\n\n"
            f"PROJECT CONTEXT:\n{project_context}\n\n"
            f"REQUIREMENTS:\n"
            f"- List EVERY external service this app uses\n"
            f"- For each: dashboard URL, API URL, where credentials "
            f"are stored, how to rotate them, monthly cost estimate\n"
            f"- Use ASCII box diagrams for visual clarity\n"
            f"- ONLY include services this project actually uses\n"
            f"- Format as Markdown\n"
        ),
        state=state,
        action="general",
    )

    # 4. Update Guide
    docs["UPDATE_GUIDE.md"] = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Generate an Update Guide for a zero-IT operator.\n\n"
            f"PROJECT CONTEXT:\n{project_context}\n\n"
            f"REQUIREMENTS:\n"
            f"- Table of common changes: what, difficulty (Easy/Medium/"
            f"Hard), method\n"
            f"- Easy: step-by-step with exact file paths, database "
            f"tables, config locations\n"
            f"- Medium: step-by-step with rebuild instructions\n"
            f"- Hard: explain pipeline rebuild is needed\n"
            f"- Tailored to {app_category} — use relevant examples\n"
            f"- Format as Markdown\n"
        ),
        state=state,
        action="general",
    )

    # ── Per-Program Documents (multi-stack only) ──
    program_id = state.project_metadata.get("program_id")
    if program_id:
        program_docs = await _generate_program_docs(state, project_context)
        docs.update(program_docs)

    return docs


async def _generate_program_docs(
    state: PipelineState, project_context: str,
) -> dict[str, str]:
    """Generate per-program docs when all siblings complete S8.

    Spec: FIX-27 (per-program documents)
    Stub for P2 — real implementation queries Neo4j for sibling status.
    """
    program_id = state.project_metadata.get("program_id", "")

    # Stub: return deferred notice
    # Real implementation checks if all siblings have completed S8
    # via Neo4j query, then generates 3 cross-project docs
    return {
        "_PROGRAM_DOCS_DEFERRED": (
            f"Program docs deferred: checking sibling status for "
            f"program_id={program_id}. Generated when last sibling "
            f"completes S8."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# §4.9 S8 Handoff Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S8_HANDOFF)
async def s8_handoff_node(state: PipelineState) -> PipelineState:
    """S8: Handoff — generate legal docs, compile summary,
    generate handoff intelligence pack, deliver everything.

    Spec: §4.9, FIX-27
    Final stage. Terminal → COMPLETED.

    Cost target: <$0.50 base + ~$0.30–$0.50 for handoff docs
    """
    blueprint_data = state.s2_output or {}
    app_name = blueprint_data.get("app_name", state.project_id)
    stack = blueprint_data.get("selected_stack", "unknown")
    platforms = blueprint_data.get("target_platforms", [])

    # ── Step 1: Generate legal documents (DocuGen §3.5) ──
    legal_docs = await generate_legal_documents(state, blueprint_data)

    # ── Step 2: Compile project summary ──
    deployments = (state.s6_output or {}).get("deployments", {})
    summary = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=(
            f"Compile a project handoff summary.\n\n"
            f"App: {app_name}\n"
            f"Stack: {stack}\n"
            f"Platforms: {platforms}\n"
            f"Deployments: {json.dumps(deployments)[:2000]}\n"
            f"Legal docs generated: {list(legal_docs.keys())}\n"
            f"Total AI cost: ${state.total_cost_usd:.2f}\n"
            f"War Room activations: {1 if state.war_room_active else 0}\n"
            f"Snapshot ID: {state.snapshot_id}\n\n"
            f"Return a concise Markdown summary for the operator."
        ),
        state=state,
        action="general",
    )

    # ── Step 2.5: Generate Handoff Intelligence Pack (FIX-27) ──
    handoff_docs = await generate_handoff_intelligence_pack(
        state, blueprint_data,
    )

    # ── Step 3: Push to GitHub ──
    repo = state.project_id
    github_result = await _push_to_github(state, legal_docs, handoff_docs)
    state.project_metadata["github_push"] = github_result

    # ── Step 4: Store patterns in Mother Memory ──
    await _store_in_mother_memory(state, summary, handoff_docs)

    # ── Step 5: Deliver via Telegram ──
    handoff_doc_names = [
        n for n in handoff_docs.keys() if not n.startswith("_")
    ]

    delivery_message = (
        f"🎉 {app_name} is ready!\n\n"
        f"📱 Stack: {stack}\n"
        f"🌍 Platforms: {', '.join(platforms)}\n\n"
    )

    # Add deployment URLs
    for platform, info in deployments.items():
        if isinstance(info, dict):
            if info.get("url"):
                delivery_message += f"🔗 {platform}: {info['url']}\n"
            elif info.get("method") == "airlock_telegram":
                delivery_message += (
                    f"📦 {platform}: Binary sent (manual upload)\n"
                )
            elif info.get("success"):
                delivery_message += f"✓ {platform}: Submitted for review\n"

    delivery_message += (
        f"\n📋 Legal docs: {', '.join(legal_docs.keys())}\n"
        f"💰 Total AI cost: ${state.total_cost_usd:.2f} "
        f"({state.total_cost_usd * 3.75:.2f} SAR)\n"
        f"⏪ Time-travel: /restore State_#{state.snapshot_id}\n"
        f"📂 GitHub: {repo}\n"
    )

    if handoff_doc_names:
        delivery_message += (
            f"📖 Operator docs: {', '.join(handoff_doc_names)}\n"
            f"   → All docs in GitHub: {repo}/docs/\n"
        )

    await send_telegram_message(state.operator_id, delivery_message)

    # Legal disclaimer reminder
    await send_telegram_message(
        state.operator_id,
        f"⚠️ Legal documents generated for {app_name}. "
        f"These are AI-generated DRAFTS — not final legal instruments. "
        f"Have them reviewed by a qualified KSA legal professional "
        f"before publishing.",
    )

    state.s8_output = {
        "delivered": True,
        "summary": summary[:2000],
        "legal_docs": list(legal_docs.keys()),
        "handoff_docs": handoff_doc_names,
        "total_cost_usd": state.total_cost_usd,
        "snapshot_id": state.snapshot_id,
    }

    logger.info(
        f"[{state.project_id}] S8 Handoff complete: "
        f"delivered={True}, "
        f"legal={len(legal_docs)}, "
        f"handoff={len(handoff_doc_names)}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# §4.9 Step 3: GitHub Push
# ═══════════════════════════════════════════════════════════════════

async def _push_to_github(
    state: PipelineState,
    legal_docs: dict[str, str],
    handoff_docs: dict[str, str],
) -> dict:
    """Push legal and handoff docs to the project GitHub repo.

    Spec: §4.9
    Gracefully degrades if GitHub is not configured (DRY_RUN or no token).
    """
    try:
        from factory.integrations.github import github_commit_file
        repo = state.project_id
        committed = 0
        for name, content in legal_docs.items():
            await github_commit_file(
                repo, f"legal/{name}.md", content,
                f"S8 Handoff: legal/{name}",
            )
            committed += 1
        for name, content in handoff_docs.items():
            if not name.startswith("_"):
                await github_commit_file(
                    repo, f"docs/{name}", content,
                    f"S8 Handoff: docs/{name}",
                )
                committed += 1
        logger.info(
            f"[{state.project_id}] S8: Pushed {committed} files to GitHub/{repo}"
        )
        return {"pushed": True, "files": committed}
    except Exception as e:
        logger.debug(f"[{state.project_id}] GitHub push skipped: {e}")
        return {"pushed": False, "reason": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════
# §4.9 Step 4 + FIX-27: Mother Memory Storage
# ═══════════════════════════════════════════════════════════════════

async def _store_in_mother_memory(
    state: PipelineState,
    summary: str,
    handoff_docs: dict[str, str],
) -> None:
    """Store project patterns + handoff docs in Mother Memory.

    Spec: §4.9, FIX-27 — HandoffDoc nodes are permanent (Janitor-exempt).
    """
    try:
        from factory.integrations.neo4j import get_neo4j
        client = get_neo4j()

        blueprint = state.s2_output or {}
        screens = blueprint.get("architecture", {}).get("screens", [])

        await client.store_project_patterns(
            project_id=state.project_id,
            stack=(
                state.selected_stack.value if state.selected_stack else "unknown"
            ),
            screens=screens,
            success=state.project_metadata.get("tests_passed", False),
            war_room_count=state.retry_count,
        )

        await client.store_handoff_docs(
            project_id=state.project_id,
            program_id=state.project_metadata.get("program_id"),
            stack=(
                state.selected_stack.value if state.selected_stack else "unknown"
            ),
            app_category=blueprint.get("app_category", "general"),
            docs={k: v for k, v in handoff_docs.items() if not k.startswith("_")},
        )

        logger.info(
            f"[{state.project_id}] S8: Stored patterns + "
            f"{len(handoff_docs)} handoff docs in Mother Memory"
        )
    except Exception as e:
        logger.debug(f"[{state.project_id}] Mother Memory store skipped: {e}")


# Register with DAG (replaces stub)
register_stage_node("s8_handoff", s8_handoff_node)