"""
AI Factory Pipeline v5.8 — Tavily Scout Provider

Free-tier web search with an AI-synthesized answer field.
Primary search Scout for development (Perplexity requires $50 balance).

Free tier: 1,000 calls/month. Resets 1st of each month.
Key: TAVILY_API_KEY (app.tavily.com — no credit card)

Enhancements over original:
  • Mother Memory cache — checked before every API call; results stored after
  • KSA domain priority — legal queries get Saudi government sites first
  • Domain-aware search depth (advanced for legal/compliance, basic for general)
  • Structured URL extraction for downstream citation use
  • include_domains param for authoritative KSA sources on legal queries
  • Quota detection that feeds back into scout_chain state

Spec Authority: v5.6 §2.2.3, §3.1
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.tavily_scout")

TAVILY_COST_PER_CALL: float = 0.0001

# Official KSA regulatory and government domains for legal searches
_KSA_DOMAINS: list[str] = [
    "sdaia.gov.sa", "sama.gov.sa", "cst.gov.sa", "nca.gov.sa",
    "ndmo.gov.sa", "mcit.gov.sa", "moj.gov.sa", "mc.gov.sa",
    "zatca.gov.sa", "monshaat.gov.sa", "vision2030.gov.sa",
]

# Keywords that warrant KSA domain priority
_KSA_LEGAL_KEYWORDS: list[str] = [
    "pdpl", "sama", "cst", "nca", "ndmo", "sdaia",
    "saudi", "ksa", "kingdom", "arabic", "riyadh",
]

_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))


def _query_hash(query: str) -> str:
    return hashlib.md5(query.strip().lower().encode()).hexdigest()[:16]


def _is_ksa_legal(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _KSA_LEGAL_KEYWORDS)


def _is_legal_or_compliance(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in [
        "regulation", "compliance", "legal", "pdpl", "sama", "cst",
        "privacy", "policy", "guideline", "requirement", "law",
    ])


async def call_tavily_scout(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query via Tavily.

    Returns (formatted_results, cost_usd).
    """
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not set")

    query = prompt.strip()[:400]
    q_hash = _query_hash(query)

    # ── Cache check ───────────────────────────────────────────────────
    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[tavily] cache hit for '{query[:60]}'")
        return cached, 0.0

    # ── Build search params ───────────────────────────────────────────
    search_depth = "advanced" if _is_legal_or_compliance(query) else "basic"
    include_domains = _KSA_DOMAINS if _is_ksa_legal(query) else []

    try:
        from tavily import TavilyClient
        import asyncio

        client = TavilyClient(api_key=api_key)
        loop = asyncio.get_event_loop()

        kwargs: dict = dict(
            query=query,
            max_results=5,
            include_answer=True,
            search_depth=search_depth,
        )
        if include_domains:
            kwargs["include_domains"] = include_domains

        results = await loop.run_in_executor(
            None, lambda: client.search(**kwargs)
        )

        # ── Format output ─────────────────────────────────────────────
        lines: list[str] = [f"[TAVILY-SCOUT] Research results for: {query[:100]}\n"]

        if results.get("answer"):
            lines.append(f"Summary: {results['answer']}\n")

        urls: list[str] = []
        for i, r in enumerate(results.get("results", []), 1):
            title = r.get("title", "No title")
            url = r.get("url", "")
            content = r.get("content", "")[:350]
            score = r.get("score", 0.0)
            score_str = f" [relevance: {score:.2f}]" if score else ""
            lines.append(
                f"{i}. {title}{score_str}\n"
                f"   URL: {url}\n"
                f"   {content}"
            )
            if url:
                urls.append(url)

        if urls:
            lines.append(f"\nSOURCES ({len(urls)}):\n" + "\n".join(f"  • {u}" for u in urls))

        formatted = "\n\n".join(lines)

        # ── Store in cache ────────────────────────────────────────────
        await _store_cached(q_hash, "tavily", query, formatted, urls, state)

        logger.info(
            f"[tavily] {state.project_id}: {len(results.get('results', []))} results "
            f"depth={search_depth} ksa_domains={bool(include_domains)}"
        )
        return formatted, TAVILY_COST_PER_CALL

    except Exception as e:
        err = str(e)
        # Map Tavily-specific errors to standard signals
        if "quota" in err.lower() or "429" in err or "rate" in err.lower():
            raise Exception(f"429 RESOURCE_EXHAUSTED — Tavily: {err[:80]}")
        if "401" in err or "403" in err or "unauthorized" in err.lower():
            raise Exception(f"401 Unauthorized — Tavily: {err[:80]}")
        logger.error(f"[tavily] error: {e}")
        raise


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="tavily", max_age_hours=_CACHE_TTL_HOURS)
    except Exception:
        return None


async def _store_cached(
    q_hash: str, source: str, query: str, result: str,
    urls: list[str], state: "PipelineState",
) -> None:
    try:
        from factory.memory.mother_memory import store_scout_cache
        await store_scout_cache(
            query_hash=q_hash, source=source,
            query_preview=query[:80], result_preview=result[:600],
            urls=urls, operator_id=state.operator_id or "",
            project_id=state.project_id,
        )
    except Exception:
        pass
