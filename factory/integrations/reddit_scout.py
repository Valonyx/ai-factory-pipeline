"""
AI Factory Pipeline v5.8 — Reddit Scout (Community Discussions, No Key, No Quota)

Queries Reddit's public JSON search API for community insights, real-world
experience reports, and developer discussions. No API key, no signup.

Best for: developer opinions, product reviews, community sentiment,
"should I use X or Y" decisions, regional market insights.

Note: Reddit returns ~25 results/request. Anonymous access has soft rate
limits (~60 req/min) but no hard monthly quota.

Spec Authority: v5.8 §2.2.3 (Scout provider interface)
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.reddit_scout")

REDDIT_COST_PER_CALL: float = 0.0
_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_MAX_RESULTS = 5
_MIN_SCORE = 5   # skip posts with very few upvotes

# Subreddits by domain — weighted for relevance
_DOMAIN_SUBREDDITS: dict[str, list[str]] = {
    "tech":      ["programming", "webdev", "reactnative", "flutter", "learnprogramming", "devops"],
    "market":    ["startups", "entrepreneur", "SideProject", "mobiledev", "androiddev", "iosdev"],
    "legal":     ["legaladvice", "privacytoolsIO", "gdpr"],
    "community": ["programming", "cscareerquestions", "devops", "SoftwareEngineering"],
    "factual":   ["explainlikeimfive", "answers", "AskTechSupport"],
    "general":   ["programming", "technology", "startups", "mobiledev"],
}

_HEADERS = {
    "User-Agent": "AI-Research-Bot/1.0 (research assistant; contact: research@example.com)",
    "Accept": "application/json",
}


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

async def call_reddit(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
    domain: str = "general",
) -> tuple[str, float]:
    """Search Reddit's public JSON API for community insights.

    Searches across domain-relevant subreddits, filters by score,
    and formats top posts with their top comment excerpts.
    """
    query = prompt.strip()[:200]
    q_hash = _query_hash(query)

    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[reddit] cache hit for '{query[:60]}'")
        return cached, REDDIT_COST_PER_CALL

    subreddits = _DOMAIN_SUBREDDITS.get(domain, _DOMAIN_SUBREDDITS["general"])
    # Search across a combined subreddit multi to reduce requests
    subreddit_str = "+".join(subreddits[:4])

    results = await _search_reddit(query, subreddit_str)
    if not results:
        # Fallback: global Reddit search
        results = await _search_reddit(query, "all")

    if not results:
        return (
            f"[REDDIT-NO-RESULTS] No Reddit discussions found for: {query[:100]}",
            REDDIT_COST_PER_CALL,
        )

    formatted = _format_results(results, query, subreddit_str)
    await _store_cached(q_hash, "reddit", query, formatted, state)
    logger.info(f"[reddit] {len(results)} posts found for '{query[:60]}'")
    return formatted, REDDIT_COST_PER_CALL


# ═══════════════════════════════════════════════════════════════════
# Reddit Search
# ═══════════════════════════════════════════════════════════════════

async def _search_reddit(query: str, subreddit: str) -> list[dict]:
    """Query Reddit's public JSON search endpoint."""
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q":        query,
        "sort":     "relevance",
        "t":        "year",    # last year for freshness
        "limit":    25,
        "restrict_sr": "true" if subreddit != "all" else "false",
    }

    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.debug(f"[reddit] HTTP {resp.status} for r/{subreddit}")
                    return []
                data = await resp.json()

        posts = data.get("data", {}).get("children", [])
        results = []
        for child in posts:
            post = child.get("data", {})
            score = post.get("score", 0)
            if score < _MIN_SCORE:
                continue
            results.append({
                "title":       post.get("title", ""),
                "selftext":    post.get("selftext", "")[:300],
                "score":       score,
                "num_comments": post.get("num_comments", 0),
                "subreddit":   post.get("subreddit", ""),
                "permalink":   f"https://reddit.com{post.get('permalink', '')}",
                "created_utc": post.get("created_utc", 0),
            })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:_MAX_RESULTS]

    except Exception as e:
        logger.debug(f"[reddit] search error for r/{subreddit}: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════

def _format_results(results: list[dict], query: str, subreddits: str) -> str:
    lines = [
        f"[REDDIT COMMUNITY INSIGHTS]",
        f"Query: {query}",
        f"Subreddits: r/{subreddits.replace('+', ', r/')}",
        "",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r['subreddit']}] {r['title']}")
        lines.append(f"   Score: {r['score']} | Comments: {r['num_comments']}")
        if r["selftext"]:
            lines.append(f"   {r['selftext'][:200]}")
        lines.append(f"   {r['permalink']}")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Cache Helpers
# ═══════════════════════════════════════════════════════════════════

def _query_hash(q: str) -> str:
    return hashlib.md5(q.strip().lower().encode()).hexdigest()[:16]


async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="reddit", max_age_hours=_CACHE_TTL_HOURS)
    except Exception:
        return None


async def _store_cached(
    q_hash: str, source: str, query: str, result: str, state: "PipelineState"
) -> None:
    try:
        from factory.memory.mother_memory import store_scout_cache
        await store_scout_cache(
            query_hash=q_hash, source=source,
            query_preview=query[:80], result_preview=result[:600],
            urls=[], operator_id=state.operator_id or "",
            project_id=state.project_id,
        )
    except Exception:
        pass
