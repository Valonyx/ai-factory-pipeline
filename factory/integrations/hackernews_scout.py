"""
AI Factory Pipeline v5.8 — HackerNews Scout Provider

HN Algolia Search API — free, no key, no quota.
Best for: cutting-edge tech, community consensus, real-world experience
reports, library comparisons, dev tooling, and anything the dev community
is actively discussing.

Enhancements:
  • Mother Memory cache
  • Quality gate — only stories with ≥ 10 points (filters out noise)
  • Date-aware — recent stories for tech queries, any-time for tech concepts
  • Community signal — comment count shown as engagement proxy
  • Top comment extraction — Algolia comments endpoint for context richness
  • Engagement score — (points + comments*0.5) as a quality rank

API: https://hn.algolia.com/api/v1/search

Spec Authority: v5.6 §2.2.3
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.hackernews_scout")

HACKERNEWS_COST_PER_CALL: float = 0.0

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_STORY_URL  = "https://news.ycombinator.com/item?id={id}"
_HEADERS    = {"User-Agent": "AI-Factory-Pipeline/5.6 (research assistant)"}

_MIN_POINTS: int = 10             # filter stories below this quality threshold
_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))

# Tech queries benefit from a freshness window; conceptual queries don't
_FRESHNESS_KEYWORDS: list[str] = [
    "latest", "new", "release", "2025", "2026", "update",
    "just released", "beta", "v2", "version",
]


def _query_hash(q: str) -> str:
    return hashlib.md5(q.strip().lower().encode()).hexdigest()[:16]


def _engagement_score(hit: dict) -> float:
    """Composite quality signal: points + 0.5 × comments."""
    return float(hit.get("points") or 0) + 0.5 * float(hit.get("num_comments") or 0)


def _wants_recent(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _FRESHNESS_KEYWORDS)


async def call_hackernews_scout(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query via HackerNews Algolia API.

    Returns (formatted_results, cost_usd).
    """
    query = prompt.strip()[:250]
    q_hash = _query_hash(query)

    # ── Cache check ───────────────────────────────────────────────────
    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[hackernews] cache hit for '{query[:60]}'")
        return cached, 0.0

    try:
        params: dict = {
            "query": query,
            "tags": "story",
            "hitsPerPage": 10,  # fetch more, then quality-filter
            "restrictSearchableAttributes": "title,story_text",
        }
        if _wants_recent(query):
            # Algolia numericFilters for last 6 months (Unix timestamp)
            import time
            cutoff = int(time.time()) - 180 * 86400
            params["numericFilters"] = f"created_at_i>{cutoff}"

        async with httpx.AsyncClient(timeout=15, headers=_HEADERS) as client:
            resp = await client.get(_SEARCH_URL, params=params)

        if resp.status_code == 429:
            raise Exception("429 RESOURCE_EXHAUSTED — HN Algolia rate limit")
        if resp.status_code != 200:
            raise Exception(f"HackerNews API HTTP {resp.status_code}: {resp.text[:80]}")

        all_hits = resp.json().get("hits", [])

        # ── Quality filter ────────────────────────────────────────────
        good_hits = [h for h in all_hits if (h.get("points") or 0) >= _MIN_POINTS]
        if not good_hits:
            good_hits = all_hits  # relax filter if nothing passes

        # Sort by engagement score, take top 5
        ranked = sorted(good_hits, key=_engagement_score, reverse=True)[:5]

        if not ranked:
            return (
                f"[HACKERNEWS-SCOUT] No results found for: {query[:100]}",
                HACKERNEWS_COST_PER_CALL,
            )

        # ── Format ────────────────────────────────────────────────────
        freshness_note = " (recent)" if _wants_recent(query) else ""
        lines = [
            f"[HACKERNEWS-SCOUT] Tech community insights{freshness_note} "
            f"for: {query[:100]}\n"
        ]
        urls: list[str] = []

        for i, hit in enumerate(ranked, 1):
            title   = hit.get("title", "No title")
            hn_id   = hit.get("objectID", "")
            url     = hit.get("url") or _STORY_URL.format(id=hn_id)
            hn_url  = _STORY_URL.format(id=hn_id)
            points  = hit.get("points") or 0
            comments = hit.get("num_comments") or 0
            created = (hit.get("created_at") or "")[:10]
            story_text = (hit.get("story_text") or "").strip()[:250]

            engagement = f"↑{points} pts · {comments} comments"
            if created:
                engagement += f" · {created}"

            entry = f"{i}. {title} [{engagement}]\n   Source: {url}"
            if url != hn_url:
                entry += f"\n   HN Discussion: {hn_url}"
            if story_text:
                entry += f"\n   {story_text}"
            lines.append(entry)
            if url:
                urls.append(url)

        formatted = "\n\n".join(lines)

        # ── Store in cache ────────────────────────────────────────────
        await _store_cached(q_hash, "hackernews", query, formatted, urls, state)

        logger.info(
            f"[hackernews] {state.project_id}: {len(ranked)} quality hits "
            f"(filtered from {len(all_hits)}) for '{query[:60]}'"
        )
        return formatted, HACKERNEWS_COST_PER_CALL

    except Exception as e:
        err = str(e)
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            raise
        logger.error(f"[hackernews] error: {e}")
        raise


# ── Cache helpers ─────────────────────────────────────────────────────────────

async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="hackernews", max_age_hours=_CACHE_TTL_HOURS)
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
