"""
AI Factory Pipeline v5.8 — Stage Enrichment: Scout + Memory Context Injection

Every pipeline stage (S0–S8) calls `enrich_prompt()` before its main AI call.
This pulls in two layers of context that make AI output higher quality:

  1. MOTHER MEMORY — past decisions, insights, and operator preferences from
     Neo4j/Supabase/Upstash/Turso. Avoids repeating work and stays consistent.

  2. SCOUT CHAIN — fresh real-world data: market research, docs, competitor
     features, compliance rules. Tavily/Exa/DuckDuckGo/Wikipedia etc.
     Only called when the stage explicitly opts in (scout=True) to avoid
     burning quota on stages where fresh data isn't needed.

This makes the pipeline resilient: when Anthropic credits are zero, Gemini
or Groq still produce high-quality output because they receive the same rich
context that Anthropic would have had. The Scout+Memory enrichment compensates
for weaker models with better information.

Spec Authority: v5.6 §2.2.4 (Context Enrichment), §6.7 (Vector Backend)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("factory.core.stage_enrichment")

# Max characters of memory context to inject per stage
_MEMORY_CONTEXT_LIMIT = 2000
# Max characters of scout context to inject per stage
_SCOUT_CONTEXT_LIMIT = 1500


# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════


async def enrich_prompt(
    stage_name: str,
    prompt: str,
    state,
    scout: bool = False,
    scout_query: Optional[str] = None,
) -> str:
    """Prepend relevant memory + optional scout research to a stage prompt.

    Args:
        stage_name: e.g. "s0_intake", "s2_blueprint", "s4_codegen"
        prompt: The original AI prompt for this stage.
        state: PipelineState — used for project_id, operator_id, prior outputs.
        scout: If True, perform a Scout lookup to add fresh real-world context.
        scout_query: Custom scout query. If None, auto-derived from stage+state.

    Returns:
        Enriched prompt with memory and/or scout context prepended.
    """
    sections: list[str] = []

    # ── Layer 1: Mother Memory ──
    memory_ctx = await _get_memory_context(stage_name, state)
    if memory_ctx:
        sections.append(
            f"[MEMORY CONTEXT — from past projects and decisions]\n{memory_ctx}"
        )

    # ── Layer 2: Scout research ──
    if scout:
        query = scout_query or _auto_scout_query(stage_name, state)
        scout_ctx = await _get_scout_context(query, state)
        if scout_ctx:
            sections.append(
                f"[RESEARCH CONTEXT — current web research]\n{scout_ctx}"
            )

    if not sections:
        return prompt

    prefix = "\n\n".join(sections)
    return f"{prefix}\n\n---\n\n{prompt}"


async def store_stage_insight(
    stage_name: str,
    state,
    fact: str,
    category: str = "pipeline",
    ttl_hours: int = 168,  # 7 days default
) -> None:
    """Store a key insight from a stage into Mother Memory for future use.

    Call this after important stage decisions (stack choice, auth method, etc.)
    """
    try:
        from factory.memory.mother_memory import store_insight
        await store_insight(
            operator_id=state.operator_id,
            project_id=state.project_id,
            category=category,
            fact=fact,
            source=stage_name,
            relevance_score=0.8,
            ttl_hours=ttl_hours,
        )
    except Exception as e:
        logger.debug(f"[{stage_name}] store_insight failed (non-critical): {e}")


# ═══════════════════════════════════════════════════════════════════
# Memory Context
# ═══════════════════════════════════════════════════════════════════


async def _get_memory_context(stage_name: str, state) -> str:
    """Retrieve relevant insights from Mother Memory for this stage."""
    try:
        from factory.memory.mother_memory import get_relevant_insights
        insights = await get_relevant_insights(
            operator_id=state.operator_id,
            project_id=state.project_id,
            category=_stage_memory_category(stage_name),
            limit=5,
        )
        if not insights:
            return ""
        lines = [f"- {ins.get('fact', '')}" for ins in insights if ins.get("fact")]
        context = "\n".join(lines)
        return context[:_MEMORY_CONTEXT_LIMIT]
    except Exception as e:
        logger.debug(f"[{stage_name}] Memory context unavailable: {e}")
        return ""


def _stage_memory_category(stage_name: str) -> str:
    """Map stage name to memory category."""
    mapping = {
        "s0_intake":    "requirements",
        "s1_legal":     "legal",
        "s2_blueprint": "design",
        "s4_codegen":   "code",
        "s5_build":     "build",
        "s6_test":      "testing",
        "s7_deploy":    "deployment",
        "s8_verify":    "compliance",
        "s9_handoff":   "delivery",
    }
    return mapping.get(stage_name, "pipeline")


# ═══════════════════════════════════════════════════════════════════
# Scout Context
# ═══════════════════════════════════════════════════════════════════


async def _get_scout_context(query: str, state) -> str:
    """Run a Scout search and return formatted results."""
    if not query:
        return ""
    try:
        from factory.core.roles import call_ai
        from factory.core.state import AIRole
        result = await call_ai(
            role=AIRole.SCOUT,
            prompt=query,
            state=state,
            action="research",
        )
        return result[:_SCOUT_CONTEXT_LIMIT] if result else ""
    except Exception as e:
        logger.debug(f"Scout context unavailable: {e}")
        return ""


def _auto_scout_query(stage_name: str, state) -> str:
    """Build a relevant scout query for the given stage."""
    app_name = (state.s0_output or {}).get("app_name", "")
    category = (state.s0_output or {}).get("app_category", "")
    stack = (state.s2_output or {}).get("selected_stack", "")
    region = state.project_metadata.get("region", "Saudi Arabia")

    queries = {
        "s0_intake": (
            f"Top competing apps for {app_name or category} in {region}. "
            f"Key features, pricing, user ratings 2025-2026."
        ),
        "s1_legal": (
            f"Legal requirements for {category} app in Saudi Arabia 2025-2026. "
            f"PDPL compliance, data protection, app store policies."
        ),
        "s2_blueprint": (
            f"Best UI/UX patterns for {category} mobile app 2025-2026. "
            f"Material Design 3, iOS HIG, accessibility guidelines."
        ),
        "s4_codegen": (
            f"Best practices for {stack} development 2025-2026. "
            f"Common patterns, state management, Firebase integration."
        ),
        "s5_build": (
            f"{stack} build optimization and CI/CD best practices 2025."
        ),
        "s6_test": (
            f"Testing strategies for {stack} mobile apps. "
            f"Unit testing, integration testing, UI automation 2025."
        ),
        "s7_deploy": (
            f"App store submission requirements Apple/Google 2025-2026. "
            f"Review guidelines, metadata, screenshots."
        ),
        "s8_verify": (
            f"App store compliance checklist for {category} app 2025. "
            f"Privacy policy, permissions, age rating requirements."
        ),
        "s9_handoff": (
            f"App launch checklist for {category} app in {region} 2025."
        ),
    }
    return queries.get(stage_name, f"Best practices for {stage_name} phase of mobile app development")


# ═══════════════════════════════════════════════════════════════════
# Mother Memory: get_relevant_insights stub for graceful fallback
# ═══════════════════════════════════════════════════════════════════

# Imported lazily — if mother_memory doesn't have get_relevant_insights,
# we patch it here so stages don't fail.

def _patch_mother_memory_if_needed() -> None:
    """Ensure mother_memory.get_relevant_insights exists (backward compat)."""
    try:
        import factory.memory.mother_memory as mm
        if not hasattr(mm, "get_relevant_insights"):
            async def _stub_get_relevant_insights(
                operator_id: str = "",
                project_id: str = "",
                category: str = "",
                limit: int = 5,
            ) -> list:
                return []
            mm.get_relevant_insights = _stub_get_relevant_insights
    except ImportError:
        pass


_patch_mother_memory_if_needed()
