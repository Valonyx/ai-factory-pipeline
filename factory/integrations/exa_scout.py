"""
AI Factory Pipeline v5.8 — Exa.ai Scout Provider (Fallback #4)

Exa (formerly Metaphor) uses neural/semantic search instead of keyword matching.
It retrieves actual full-page content — not just snippets — making it the best
search provider for research where semantic precision matters.

Unique capabilities exploited here:
  • highlights   — AI-extracted key sentences from each page (dense context)
  • summary      — per-page LLM summary scoped to the exact query
  • livecrawl    — bypass Exa's index and fetch fresh content in real-time
  • category     — restrict to domain-specific corpora (github, arxiv, news, etc.)
  • find_similar — given a URL, find semantically related pages
  • autoprompt   — Exa rewrites the query for better neural recall

Free tier:
  1,000 searches/month (permanent free tier, no credit card required)
  Sign up: https://exa.ai → Dashboard → API Keys → Create key
  Resets: 1st of each month

Env var:
  EXA_API_KEY — the API key from the Exa dashboard

Integration with Mother Memory:
  Successful results are cached as scout_cache insights so they can be
  retrieved in future pipeline calls without consuming quota. The cache
  expires after EXA_CACHE_TTL_HOURS (default 4h) to keep results fresh.

Spec Authority: v5.8 §2.2.3, §2.10 (Mother Memory integration)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.exa_scout")

EXA_COST_PER_CALL: float = 0.0  # free tier
EXA_CACHE_TTL_HOURS: int = int(os.getenv("EXA_CACHE_TTL_HOURS", "4"))

_EXA_SEARCH_URL = "https://api.exa.ai/search"

# Keywords that indicate the query needs real-time data (bypass Exa's index)
_LIVECRAWL_KEYWORDS = {
    "latest", "current", "recent", "2024", "2025", "2026",
    "new", "update", "changelog", "release", "now", "today",
}

# Query patterns that benefit from category-restricted search
_CATEGORY_PATTERNS: list[tuple[list[str], str]] = [
    (["github", "repo", "repository", "open source", "npm", "pypi", "package"], "github"),
    (["paper", "research", "arxiv", "study", "academic"], "research paper"),
    (["news", "announcement", "press release", "blog"], "news"),
    (["pdf", "documentation", "spec", "specification", "standard"], "pdf"),
]


def _query_hash(query: str) -> str:
    """Stable 16-char hash for a normalised query string (cache key)."""
    return hashlib.md5(query.strip().lower().encode()).hexdigest()[:16]


def _needs_livecrawl(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in _LIVECRAWL_KEYWORDS)


def _detect_category(query: str) -> str | None:
    q_lower = query.lower()
    for keywords, category in _CATEGORY_PATTERNS:
        if any(kw in q_lower for kw in keywords):
            return category
    return None


def _get_key() -> str:
    return os.getenv("EXA_API_KEY", "")


async def call_exa_scout(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query via Exa.ai neural search.

    Enhancements over basic search:
      - highlights: AI-extracted key sentences (denser context for the pipeline)
      - summary: per-page LLM summary scoped to the query (zero extra calls)
      - livecrawl: bypasses cache for time-sensitive queries
      - category: domain-aware search corpus selection
      - autoprompt: Exa rewrites the query for better neural recall
      - Memory cache: checks Mother Memory before consuming Exa quota

    Returns (formatted_results, cost_usd).
    """
    api_key = _get_key()
    if not api_key:
        raise ValueError("EXA_API_KEY not set")

    query = prompt.strip()[:300]
    q_hash = _query_hash(query)

    # ── Pre-call: check Mother Memory cache ─────────────────────────────────
    cached = await _get_cached_result(q_hash, state)
    if cached:
        logger.info(f"[exa] cache hit for '{query[:60]}' — skipping API call")
        return cached, EXA_COST_PER_CALL

    # ── Build request payload ─────────────────────────────────────────────
    livecrawl = "always" if _needs_livecrawl(query) else "fallback"
    category = _detect_category(query)

    payload: dict = {
        "query": query,
        "num_results": 5,
        "type": "auto",           # Exa auto-selects neural vs keyword
        "use_autoprompt": True,   # Exa rewrites for better neural recall
        "livecrawl": livecrawl,
        "contents": {
            "text": {"max_characters": 800},
            "highlights": {
                "num_sentences": 5,       # dense context per page
                "highlights_per_url": 2,  # top 2 highlight blocks per page
            },
            "summary": {
                "query": query,           # page summary scoped to our question
            },
        },
    }
    if category:
        payload["category"] = category
        logger.debug(f"[exa] using category={category!r} for query")

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    # ── API call ────────────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(_EXA_SEARCH_URL, headers=headers, json=payload)

        if r.status_code == 401:
            raise Exception("401 Unauthorized — check EXA_API_KEY")
        if r.status_code == 429:
            raise Exception("429 RESOURCE_EXHAUSTED — Exa monthly limit reached")
        if r.status_code != 200:
            raise Exception(f"Exa HTTP {r.status_code}: {r.text[:120]}")

        data = r.json()
        results = data.get("results", [])

        if not results:
            return (
                f"[EXA-SCOUT] No results found for: {query[:100]}",
                EXA_COST_PER_CALL,
            )

        # ── Format output ─────────────────────────────────────────────────
        formatted = _format_results(query, results, livecrawl, category)

        # ── Post-call: cache in Mother Memory ─────────────────────────────
        urls = [r.get("url", "") for r in results if r.get("url")]
        await _cache_result(q_hash, query, formatted, urls, state)

        logger.info(
            f"[exa] {state.project_id}: {len(results)} results "
            f"(livecrawl={livecrawl}, category={category!r})"
        )
        return formatted, EXA_COST_PER_CALL

    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            raise
        if "401" in err or "Unauthorized" in err:
            raise
        logger.error(f"[exa] error: {e}")
        raise


def _format_results(
    query: str,
    results: list[dict],
    livecrawl: str,
    category: str | None,
) -> str:
    """Format Exa results into a rich research block for the pipeline."""
    meta_parts = ["neural search"]
    if livecrawl == "always":
        meta_parts.append("live-crawled")
    if category:
        meta_parts.append(f"corpus={category}")
    meta = ", ".join(meta_parts)

    lines = [f"[EXA-SCOUT] Research results ({meta}) for: {query[:100]}\n"]

    collected_urls: list[str] = []

    for i, res in enumerate(results, 1):
        title = res.get("title", "No title")
        url = res.get("url", "")
        published = res.get("publishedDate", "")
        date_str = f" ({published[:10]})" if published else ""

        # Prefer summary → highlights → text (in order of quality for research)
        summary = (res.get("summary") or "").strip()
        highlights = res.get("highlights") or []
        text_body = (res.get("text") or "").strip()

        if summary:
            body = summary[:600]
            source_label = "Summary"
        elif highlights:
            body = " … ".join(h.strip() for h in highlights[:3])[:600]
            source_label = "Key passages"
        elif text_body:
            body = text_body[:400]
            source_label = "Excerpt"
        else:
            body = "No content available"
            source_label = "Excerpt"

        lines.append(
            f"{i}. {title}{date_str}\n"
            f"   [{source_label}] {body}\n"
            f"   Source: {url}"
        )

        if url:
            collected_urls.append(url)

    # Append source list for easy citation extraction downstream
    if collected_urls:
        lines.append(
            f"\nSOURCES ({len(collected_urls)}):\n"
            + "\n".join(f"  • {u}" for u in collected_urls)
        )

    return "\n\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Mother Memory Scout Cache
# ═══════════════════════════════════════════════════════════════════

_CACHE_PREFIX = "EXA_CACHE:"


async def _cache_result(
    q_hash: str,
    query: str,
    result: str,
    urls: list[str],
    state: "PipelineState",
) -> None:
    """Store Exa result in Mother Memory for future reuse."""
    try:
        from factory.memory.mother_memory import store_scout_cache
        await store_scout_cache(
            query_hash=q_hash,
            source="exa",
            query_preview=query[:80],
            result_preview=result[:600],
            urls=urls,
            operator_id=state.operator_id or "",
            project_id=state.project_id,
        )
    except Exception as e:
        logger.debug(f"[exa] cache write skipped: {e}")


async def _get_cached_result(
    q_hash: str,
    state: "PipelineState",
) -> str | None:
    """Return a cached Exa result from Mother Memory if still fresh."""
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        entry = await get_cached_scout_result(
            query_hash=q_hash,
            source="exa",
            max_age_hours=EXA_CACHE_TTL_HOURS,
        )
        if entry:
            return f"[EXA-SCOUT][CACHED] {entry}"
    except Exception as e:
        logger.debug(f"[exa] cache read skipped: {e}")
    return None
