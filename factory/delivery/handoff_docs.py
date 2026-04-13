"""
AI Factory Pipeline v5.6 — Handoff Intelligence Pack (FIX-27)

Implements:
  - Contract 9 (§8.10): generate_handoff_intelligence_pack()
  - 4 per-project docs (generated for every project)
  - 3 per-program docs (generated when all siblings complete)
  - Mother Memory storage for handoff docs

Per-Project Docs:
  1. App Operations Manual — how to run/maintain/update the app
  2. Technical Architecture Guide — stack, APIs, data model
  3. Troubleshooting Playbook — common issues + fixes
  4. Cost & Performance Summary — budget, metrics, recommendations

Per-Program Docs (multi-stack only):
  5. Cross-Stack Integration Map — how components connect
  6. Unified Deployment Guide — deploy all stacks together
  7. Program Health Dashboard Config — monitoring setup

Spec Authority: v5.6 §4.9 FIX-27, Contract 9
"""

from __future__ import annotations

import logging
from typing import Optional

from factory.core.state import AIRole, PipelineState
from factory.core.roles import call_ai
from factory.telegram.notifications import send_telegram_message

logger = logging.getLogger("factory.delivery.handoff_docs")


# ═══════════════════════════════════════════════════════════════════
# Document Definitions
# ═══════════════════════════════════════════════════════════════════

PER_PROJECT_DOCS = {
    "app_operations_manual": {
        "title": "App Operations Manual",
        "prompt_template": (
            "Write an App Operations Manual for {app_name} ({stack}).\n"
            "Include: how to start/stop, update content, manage users, "
            "monitor health, apply patches, backup procedures.\n"
            "Audience: Non-technical operator. Write step-by-step.\n"
            "Blueprint: {blueprint_summary}\n"
            "Return Markdown."
        ),
    },
    "technical_architecture_guide": {
        "title": "Technical Architecture Guide",
        "prompt_template": (
            "Write a Technical Architecture Guide for {app_name} ({stack}).\n"
            "Include: stack overview, API endpoints, data model, "
            "third-party integrations, deployment architecture, "
            "environment variables, security considerations.\n"
            "Blueprint: {blueprint_summary}\n"
            "Return Markdown."
        ),
    },
    "troubleshooting_playbook": {
        "title": "Troubleshooting Playbook",
        "prompt_template": (
            "Write a Troubleshooting Playbook for {app_name} ({stack}).\n"
            "Include: common errors and fixes, health check procedures, "
            "log locations, escalation paths, War Room history analysis.\n"
            "War Room history: {war_room_summary}\n"
            "Return Markdown with problem → diagnosis → fix format."
        ),
    },
    "cost_performance_summary": {
        "title": "Cost & Performance Summary",
        "prompt_template": (
            "Write a Cost & Performance Summary for {app_name} ({stack}).\n"
            "Include: total cost breakdown by role/stage, "
            "AI call count, token usage, build times, "
            "optimization recommendations for future projects.\n"
            "Cost data: ${total_cost:.2f} total\n"
            "Phase costs: {phase_costs}\n"
            "Return Markdown with tables."
        ),
    },
}

PER_PROGRAM_DOCS = {
    "cross_stack_integration_map": {
        "title": "Cross-Stack Integration Map",
        "prompt_template": (
            "Write a Cross-Stack Integration Map for program {program_id}.\n"
            "Stacks: {stacks}\n"
            "Describe: how the stacks communicate, shared APIs, "
            "data flows, authentication boundaries, deployment order.\n"
            "Return Markdown with diagrams (Mermaid)."
        ),
    },
    "unified_deployment_guide": {
        "title": "Unified Deployment Guide",
        "prompt_template": (
            "Write a Unified Deployment Guide for program {program_id}.\n"
            "Stacks: {stacks}\n"
            "Include: deployment sequence, dependency order, "
            "rollback procedures, health verification steps, "
            "environment setup for each stack.\n"
            "Return Markdown."
        ),
    },
    "program_health_dashboard": {
        "title": "Program Health Dashboard Configuration",
        "prompt_template": (
            "Write a Program Health Dashboard Configuration for "
            "program {program_id}.\n"
            "Stacks: {stacks}\n"
            "Include: monitoring endpoints, alert thresholds, "
            "uptime targets, log aggregation setup, "
            "recommended monitoring tools.\n"
            "Return Markdown."
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════
# FIX-27: generate_handoff_intelligence_pack
# ═══════════════════════════════════════════════════════════════════


async def generate_handoff_intelligence_pack(
    state: PipelineState,
    blueprint_data: dict,
) -> dict[str, str]:
    """Generate Handoff Intelligence Pack.

    Spec: Contract 9 (§8.10) [FIX-27]

    4 per-project docs (always generated).
    3 per-program docs (if multi-stack + all siblings complete).

    Cost: ~$0.30-$0.50 per project (4 Engineer calls);
          ~$0.50-$0.80 for multi-stack programs (7 Engineer calls).
    """
    app_name = blueprint_data.get("app_name", state.project_id)
    stack = str(getattr(state, "selected_stack", "unknown"))
    documents: dict[str, str] = {}

    # ── Per-project documents (4 calls) ──
    for doc_id, doc_def in PER_PROJECT_DOCS.items():
        try:
            content = await _generate_doc(
                state, doc_def, app_name, stack, blueprint_data,
            )
            documents[doc_id] = content
            logger.info(
                f"[{state.project_id}] Handoff doc: {doc_id} ✅"
            )
        except Exception as e:
            logger.warning(
                f"[{state.project_id}] Handoff doc {doc_id} failed: {e}"
            )
            documents[doc_id] = (
                f"# {doc_def['title']}\n\n"
                f"_Generation failed: {str(e)[:200]}_\n"
            )

    # ── Per-program documents (if multi-stack) ──
    program_id = state.project_metadata.get("program_id")
    if program_id:
        siblings_complete = await _check_siblings_complete(
            state, program_id,
        )
        if siblings_complete:
            stacks = await _get_program_stacks(state, program_id)
            for doc_id, doc_def in PER_PROGRAM_DOCS.items():
                try:
                    content = await _generate_program_doc(
                        state, doc_def, program_id, stacks,
                    )
                    documents[doc_id] = content
                    logger.info(
                        f"[{state.project_id}] Program doc: {doc_id} ✅"
                    )
                except Exception as e:
                    logger.warning(
                        f"[{state.project_id}] Program doc "
                        f"{doc_id} failed: {e}"
                    )

    # Store in state
    state.project_metadata["handoff_intelligence_pack"] = list(
        documents.keys()
    )

    # Notify operator
    await send_telegram_message(
        state.operator_id,
        f"📚 Handoff Intelligence Pack ready ({len(documents)} docs)\n"
        + "\n".join(
            f"  • {PER_PROJECT_DOCS.get(k, PER_PROGRAM_DOCS.get(k, {})).get('title', k)}"
            for k in documents
        ),
    )

    return documents


# ═══════════════════════════════════════════════════════════════════
# Document Generation
# ═══════════════════════════════════════════════════════════════════


async def _generate_doc(
    state: PipelineState,
    doc_def: dict,
    app_name: str,
    stack: str,
    blueprint_data: dict,
) -> str:
    """Generate a single per-project handoff document."""
    prompt = doc_def["prompt_template"].format(
        app_name=app_name,
        stack=stack,
        blueprint_summary=str(blueprint_data)[:2000],
        war_room_summary=str(state.war_room_history[-5:])[:1000],
        total_cost=state.total_cost_usd,
        phase_costs=str(state.phase_costs)[:500],
    )

    content = await call_ai(
        role=AIRole.ENGINEER,
        prompt=prompt,
        state=state,
        action="write_code",
    )

    header = (
        f"<!-- Handoff Intelligence Pack — {doc_def['title']} -->\n"
        f"<!-- Project: {state.project_id} | Stack: {stack} -->\n\n"
    )
    return header + content


async def _generate_program_doc(
    state: PipelineState,
    doc_def: dict,
    program_id: str,
    stacks: list[str],
) -> str:
    """Generate a single per-program handoff document."""
    prompt = doc_def["prompt_template"].format(
        program_id=program_id,
        stacks=", ".join(stacks),
    )

    content = await call_ai(
        role=AIRole.ENGINEER,
        prompt=prompt,
        state=state,
        action="write_code",
    )

    header = (
        f"<!-- Handoff Intelligence Pack — {doc_def['title']} -->\n"
        f"<!-- Program: {program_id} -->\n\n"
    )
    return header + content


# ═══════════════════════════════════════════════════════════════════
# Multi-Stack Helpers
# ═══════════════════════════════════════════════════════════════════


async def _check_siblings_complete(
    state: PipelineState,
    program_id: str,
) -> bool:
    """Check if all sibling projects in a program are complete."""
    try:
        from factory.integrations.neo4j import get_neo4j
        neo4j = get_neo4j()
        siblings = neo4j.find_nodes("ProjectNode", {
            "program_id": program_id,
        })
        return all(
            s.get("status") in ("complete", "S9_HANDOFF")
            for s in siblings
        )
    except Exception:
        return False


async def _get_program_stacks(
    state: PipelineState,
    program_id: str,
) -> list[str]:
    """Get all stacks in a multi-stack program."""
    try:
        from factory.integrations.neo4j import get_neo4j
        neo4j = get_neo4j()
        siblings = neo4j.find_nodes("ProjectNode", {
            "program_id": program_id,
        })
        return list(set(s.get("stack", "unknown") for s in siblings))
    except Exception:
        return [str(getattr(state, "selected_stack", "unknown"))]


# ═══════════════════════════════════════════════════════════════════
# Mother Memory Storage (Contract 10)
# ═══════════════════════════════════════════════════════════════════


async def store_handoff_docs_in_memory(
    project_id: str,
    program_id: Optional[str],
    stack: str,
    app_category: str,
    docs: dict[str, str],
) -> None:
    """Store handoff docs in Mother Memory for cross-project access.

    Spec: Contract 10 (§8.10) [FIX-27]
    """
    try:
        from factory.integrations.neo4j import get_neo4j
        from datetime import datetime, timezone
        neo4j = get_neo4j()

        for doc_id, content in docs.items():
            await neo4j.create_node("HandoffDoc", {
                "project_id": project_id,
                "program_id": program_id or "",
                "stack": stack,
                "app_category": app_category,
                "doc_type": doc_id,
                "content_preview": content[:500],
                "content_length": len(content),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        logger.info(
            f"[{project_id}] Stored {len(docs)} handoff docs in Memory"
        )
    except Exception as e:
        logger.error(f"Failed to store handoff docs: {e}")