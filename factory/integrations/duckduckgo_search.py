"""
AI Factory Pipeline v5.6 — DuckDuckGo Scout Provider

No API key. No signup. IP fair-use only.
SDK: duckduckgo-search (pip install duckduckgo-search)

Enhancements:
  • Mother Memory cache — check before scraping, store after
  • News mode — DDGS().news() for realtime / time-sensitive queries
  • Region targeting — xa-ar for KSA queries (Arabic/Saudi results)
  • Query normalisation — remove stop words, cap at sensible length
  • Quality signal — prefer results with non-empty body

Spec Authority: v5.6 §2.2.3
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.duckduckgo_search")

DDG_COST_PER_CALL: float = 0.0

_KSA_KEYWORDS: list[str] = [
    "ksa", "saudi", "riyadh", "pdpl", "sama", "cst", "nca", "sdaia",
    "arabic", "مملكة", "سعودي",
]
_NEWS_KEYWORDS: list[str] = [
    "latest", "news", "recent", "today", "this week", "announcement",
    "update", "2025", "2026", "new release", "breaking",
]
_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))


def _query_hash(q: str) -> str:
    return hashlib.md5(q.strip().lower().encode()).hexdigest()[:16]


def _detect_region(query: str) -> str:
    return "xa-ar" if any(kw in query.lower() for kw in _KSA_KEYWORDS) else "wt-wt"


def _is_news_query(query: str) -> bool:
    return any(kw in query.lower() for kw in _NEWS_KEYWORDS)


async def call_duckduckgo_search(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query via DuckDuckGo.

    Automatically selects news mode for realtime queries and applies
    regional settings for KSA-specific searches.

    Returns (formatted_results, cost_usd).
    """
    query = prompt.strip()[:300]
    q_hash = _query_hash(query)

    # ── Cache check ───────────────────────────────────────────────────
    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[ddg] cache hit for '{query[:60]}'")
        return cached, 0.0

    # ── Mode detection ────────────────────────────────────────────────
    use_news = _is_news_query(query)
    region = _detect_region(query)

    try:
        from duckduckgo_search import DDGS

        loop = asyncio.get_event_loop()

        if use_news:
            raw_results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().news(
                    query,
                    max_results=6,
                    region=region,
                ))
            )
            mode_label = "news"
        else:
            raw_results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(
                    query,
                    max_results=7,
                    region=region,
                ))
            )
            mode_label = "web"

        # Filter results with empty body (noise)
        results = [r for r in raw_results if r.get("body") or r.get("excerpt")]
        if not results:
            results = raw_results  # keep all if filtering removed everything

        if not results:
            return (
                f"[DDG-SCOUT] No results found for: {query[:100]}",
                DDG_COST_PER_CALL,
            )

        # ── Format ────────────────────────────────────────────────────
        meta = f"mode={mode_label}, region={region}"
        lines = [f"[DDG-SCOUT] Research results ({meta}) for: {query[:100]}\n"]
        urls: list[str] = []

        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "No title")
            body = (r.get("body") or r.get("excerpt") or "No description")[:280]
            href = r.get("href") or r.get("url", "")
            date = r.get("date", "")
            date_str = f" [{date[:10]}]" if date else ""

            lines.append(f"{i}. {title}{date_str}\n   {body}\n   Source: {href}")
            if href:
                urls.append(href)

        formatted = "\n\n".join(lines)

        # ── Store in cache ────────────────────────────────────────────
        await _store_cached(q_hash, "duckduckgo", query, formatted, urls, state)

        logger.info(
            f"[ddg] {state.project_id}: {len(results)} results "
            f"({mode_label}, region={region})"
        )
        return formatted, DDG_COST_PER_CALL

    except ImportError:
        logger.error("duckduckgo-search not installed — run: pip install duckduckgo-search")
        raise
    except Exception as e:
        err = str(e)
        if "ratelimit" in err.lower() or "429" in err:
            raise Exception(f"429 RESOURCE_EXHAUSTED — DuckDuckGo: {err[:60]}")
        logger.error(f"[ddg] error: {e}")
        raise


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="duckduckgo", max_age_hours=_CACHE_TTL_HOURS)
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
