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
import os
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
    Queries Neo4j for sibling ProjectNode status. If all siblings are
    in S8_HANDOFF or completed, generates 3 cross-project documents:
      - Cross-Stack Integration Map
      - Unified Deployment Guide
      - Program Health Dashboard Configuration
    """
    program_id = state.project_metadata.get("program_id", "")
    if not program_id:
        return {}

    # ── Check sibling completion via Neo4j ──
    siblings_done = False
    stacks: list[str] = []
    try:
        from factory.integrations.neo4j import get_neo4j

        neo4j = get_neo4j()
        siblings = neo4j.find_nodes("ProjectNode", {"program_id": program_id})
        if siblings:
            siblings_done = all(
                s.get("status") in ("complete", "S8_HANDOFF", "COMPLETED")
                for s in siblings
            )
            stacks = list({s.get("stack", "unknown") for s in siblings if s.get("stack")})
        else:
            # No siblings registered — this is a single-project run
            logger.info(f"[{state.project_id}] No siblings for program_id={program_id} — skipping program docs")
            return {}
    except Exception as e:
        logger.warning(f"[{state.project_id}] Neo4j sibling check failed: {e}")
        return {
            "_PROGRAM_DOCS_DEFERRED": (
                f"Program docs deferred (Neo4j unavailable): "
                f"program_id={program_id}. Will retry on next S8 run."
            ),
        }

    if not siblings_done:
        logger.info(
            f"[{state.project_id}] Program docs deferred: "
            f"not all siblings complete for program_id={program_id}"
        )
        return {
            "_PROGRAM_DOCS_DEFERRED": (
                f"Program docs deferred: waiting for sibling completion. "
                f"program_id={program_id}, stacks={stacks}"
            ),
        }

    # ── All siblings complete — generate 3 cross-project docs ──
    stacks_str = ", ".join(stacks) if stacks else "multi-stack"
    logger.info(
        f"[{state.project_id}] All siblings complete — generating program docs "
        f"for program_id={program_id}, stacks={stacks}"
    )

    program_doc_prompts = {
        "CROSS_STACK_INTEGRATION_MAP.md": (
            f"Write a Cross-Stack Integration Map for program {program_id}.\n"
            f"Stacks: {stacks_str}\n"
            f"Context: {project_context[:1500]}\n\n"
            f"Describe: how the stacks communicate, shared APIs, "
            f"data flows, authentication boundaries, deployment order.\n"
            f"Return Markdown with Mermaid diagrams where helpful."
        ),
        "UNIFIED_DEPLOYMENT_GUIDE.md": (
            f"Write a Unified Deployment Guide for program {program_id}.\n"
            f"Stacks: {stacks_str}\n"
            f"Context: {project_context[:1500]}\n\n"
            f"Include: deployment sequence, dependency order, "
            f"rollback procedures, health verification steps, "
            f"environment setup for each stack.\n"
            f"Return Markdown."
        ),
        "PROGRAM_HEALTH_DASHBOARD.md": (
            f"Write a Program Health Dashboard Configuration for "
            f"program {program_id}.\n"
            f"Stacks: {stacks_str}\n"
            f"Context: {project_context[:1500]}\n\n"
            f"Include: monitoring endpoints, alert thresholds, "
            f"uptime targets, log aggregation setup, "
            f"recommended monitoring tools.\n"
            f"Return Markdown."
        ),
    }

    docs: dict[str, str] = {}
    for filename, prompt in program_doc_prompts.items():
        try:
            content = await call_ai(
                role=AIRole.ENGINEER,
                prompt=prompt,
                state=state,
                action="general",
            )
            header = (
                f"<!-- Program Handoff Doc — {filename} -->\n"
                f"<!-- Program: {program_id} | Stacks: {stacks_str} -->\n\n"
            )
            docs[filename] = header + content
            logger.info(f"[{state.project_id}] Program doc generated: {filename}")
        except Exception as e:
            logger.warning(f"[{state.project_id}] Program doc {filename} failed: {e}")
            docs[filename] = f"# {filename}\n\n_Generation failed: {e}_\n"

    return docs


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

    from factory.core.stage_enrichment import enrich_prompt, store_stage_insight

    # ── Step 1: Generate legal documents (DocuGen §3.5) ──
    legal_docs = await generate_legal_documents(state, blueprint_data)

    # ── Step 2: Compile project summary ──
    deployments = (state.s6_output or {}).get("deployments", {})
    _summary_base = (
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
    )
    _summary_prompt = await enrich_prompt("s8_handoff", _summary_base, state, scout=False)
    summary = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=_summary_prompt,
        state=state,
        action="general",
    )
    # Store delivery insights for future projects
    await store_stage_insight(
        "s8_handoff", state,
        fact=f"App {app_name} ({stack}) delivered. Cost: ${state.total_cost_usd:.2f}. "
             f"Platforms: {platforms}.",
        category="delivery",
        ttl_hours=720,  # 30 days
    )

    # ── Step 2.5: Generate Handoff Intelligence Pack (FIX-27) ──
    handoff_docs = await generate_handoff_intelligence_pack(
        state, blueprint_data,
    )

    # ── Step 3: Push to GitHub ──
    github_owner = os.getenv("GITHUB_OWNER", "")
    repo = f"{github_owner}/{state.project_id}" if github_owner else state.project_id
    github_result = await _push_to_github(state, legal_docs, handoff_docs, repo=repo)
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

    github_url = (
        f"https://github.com/{repo}" if github_result.get("pushed") else repo
    )
    delivery_message += (
        f"\n📋 Legal docs: {', '.join(legal_docs.keys())}\n"
        f"💰 Total AI cost: ${state.total_cost_usd:.2f} "
        f"({state.total_cost_usd * 3.75:.2f} SAR)\n"
        f"⏪ Time-travel: /restore State_#{state.snapshot_id}\n"
        f"📂 GitHub: {github_url}\n"
    )

    if handoff_doc_names:
        delivery_message += (
            f"📖 Operator docs: {', '.join(handoff_doc_names)}\n"
            f"   → All docs in GitHub: {github_url}/docs/\n"
        )

    await send_telegram_message(state.operator_id, delivery_message)

    # ── Send legal docs as Telegram files so operator gets them directly ──
    await _send_docs_via_telegram(state, app_name, legal_docs, handoff_docs)

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
    repo: Optional[str] = None,
) -> dict:
    """Push legal and handoff docs to the project GitHub repo.

    Spec: §4.9
    Gracefully degrades if GitHub is not configured (DRY_RUN or no token).
    """
    try:
        from factory.integrations.github import github_commit_file
        if repo is None:
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
        screens = blueprint.get("screens", [])

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


async def _send_docs_via_telegram(
    state: PipelineState,
    app_name: str,
    legal_docs: dict[str, str],
    handoff_docs: dict[str, str],
) -> None:
    """Send legal and handoff documents as Telegram files.

    Writes each doc to a temp file and sends via send_telegram_file.
    Gives operator direct access without needing GitHub.
    """
    import os
    import tempfile

    from factory.telegram.notifications import send_telegram_file

    all_docs = {
        **{f"legal_{k}.md": v for k, v in legal_docs.items()},
        **{k: v for k, v in handoff_docs.items() if not k.startswith("_")},
    }

    if not all_docs:
        return

    sent = 0
    for filename, content in all_docs.items():
        if not content or len(content) < 20:
            continue
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=f"_{filename}", delete=False, encoding="utf-8",
            )
            tmp.write(content)
            tmp.close()
            ok = await send_telegram_file(
                state.operator_id,
                tmp.name,
                caption=f"📄 {filename} — {app_name}",
            )
            if ok:
                sent += 1
            os.unlink(tmp.name)
        except Exception as e:
            logger.debug(f"[{state.project_id}] Doc send failed ({filename}): {e}")

    if sent > 0:
        logger.info(
            f"[{state.project_id}] S8: Sent {sent} documents via Telegram"
        )


# Register with DAG (replaces stub)
register_stage_node("s8_handoff", s8_handoff_node)

def _compile_project_summary(state) -> dict:
    """Compile a project summary dict from pipeline state.

    Spec: §4.9 S8 Handoff — summary for handoff intelligence pack.
    """
    from datetime import datetime, timezone as _tz
    blueprint = state.s2_output or {}
    return {
        "project_id": state.project_id,
        "app_name": blueprint.get("app_name", state.idea_name),
        "stack": blueprint.get("selected_stack", "unknown"),
        "platforms": blueprint.get("target_platforms", []),
        "total_cost_usd": state.total_cost_usd,
        "stages_completed": len(state.stage_history),
        "handoff_docs": HANDOFF_DOCS,
        "completed_at": datetime.now(_tz.utc).isoformat(),
    }
