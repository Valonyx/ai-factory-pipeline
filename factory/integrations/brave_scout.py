"""
AI Factory Pipeline v5.8 — Brave Search Scout (paid, independent web index)

Brave Search maintains an independent web index (not a Google/Bing reseller),
making it valuable for unfiltered results and cross-checking against other
providers. Paid-only — no free tier available.

Requires: BRAVE_SEARCH_API_KEY (api.search.brave.com)

Best for: general web search, cross-validation with other providers,
fresh news results, and when DuckDuckGo/SearXNG don't find enough.

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

logger = logging.getLogger("factory.integrations.brave_scout")

BRAVE_COST_PER_CALL: float = 0.0
_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))
_API_KEY: str = os.getenv("BRAVE_SEARCH_API_KEY", "")

_BASE_URL = "https://api.search.brave.com/res/v1"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_MAX_RESULTS = 5


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

async def call_brave(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
    freshness: str = "any",
) -> tuple[str, float]:
    """Search using Brave's independent web index.

    Returns web results with descriptions and news results for
    freshness-sensitive queries. Raises ValueError if API key absent.
    """
    if not _API_KEY:
        raise ValueError("BRAVE_SEARCH_API_KEY not configured")

    query = prompt.strip()[:300]
    q_hash = _query_hash(query)

    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[brave] cache hit for '{query[:60]}'")
        return cached, BRAVE_COST_PER_CALL

    web_results, news_results = await _search(query, freshness)

    if not web_results and not news_results:
        return (
            f"[BRAVE-NO-RESULTS] No results found for: {query[:100]}",
            BRAVE_COST_PER_CALL,
        )

    formatted = _format_results(web_results, news_results, query)
    urls = [r.get("url", "") for r in web_results if r.get("url")]
    await _store_cached(q_hash, "brave", query, formatted, urls, state)
    logger.info(f"[brave] {len(web_results)} web + {len(news_results)} news results")
    return formatted, BRAVE_COST_PER_CALL


# ═══════════════════════════════════════════════════════════════════
# Brave Search API
# ═══════════════════════════════════════════════════════════════════

async def _search(query: str, freshness: str) -> tuple[list[dict], list[dict]]:
    """Call Brave Search Web API and optionally News API."""
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": _API_KEY,
    }
    params: dict = {
        "q":     query,
        "count": _MAX_RESULTS,
        "safesearch": "off",
    }
    # For realtime queries, add freshness filter
    if freshness == "realtime":
        params["freshness"] = "pd"   # past day

    web_results: list[dict] = []
    news_results: list[dict] = []

    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            # Web search
            async with session.get(
                f"{_BASE_URL}/web/search", headers=headers, params=params
            ) as resp:
                if resp.status == 429:
                    raise RuntimeError("429 rate limit — brave quota exhausted")
                if resp.status == 401:
                    raise ValueError("Brave API key invalid or expired")
                if resp.status == 200:
                    data = await resp.json()
                    web_items = data.get("web", {}).get("results", [])
                    web_results = [
                        {
                            "title":       r.get("title", ""),
                            "description": r.get("description", "")[:300],
                            "url":         r.get("url", ""),
                            "age":         r.get("age", ""),
                        }
                        for r in web_items[:_MAX_RESULTS]
                        if r.get("description")
                    ]

            # News for realtime freshness
            if freshness == "realtime" and params.get("freshness"):
                news_params = {**params, "count": 3}
                async with session.get(
                    f"{_BASE_URL}/news/search", headers=headers, params=news_params
                ) as resp2:
                    if resp2.status == 200:
                        data2 = await resp2.json()
                        news_items = data2.get("results", [])
                        news_results = [
                            {
                                "title":       n.get("title", ""),
                                "description": n.get("description", "")[:200],
                                "url":         n.get("url", ""),
                                "age":         n.get("age", ""),
                                "source":      n.get("meta_url", {}).get("hostname", ""),
                            }
                            for n in news_items[:3]
                        ]

    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        logger.debug(f"[brave] request error: {e}")

    return web_results, news_results


# ═══════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════

def _format_results(
    web_results: list[dict], news_results: list[dict], query: str
) -> str:
    lines = [f"[BRAVE SEARCH — Independent Web Index]", f"Query: {query}", ""]

    if web_results:
        lines.append("WEB RESULTS:")
        for i, r in enumerate(web_results, 1):
            age = f" [{r['age']}]" if r.get("age") else ""
            lines.append(f"{i}. {r['title']}{age}")
            if r["description"]:
                lines.append(f"   {r['description']}")
            if r["url"]:
                lines.append(f"   {r['url']}")
            lines.append("")

    if news_results:
        lines.append("RECENT NEWS:")
        for n in news_results:
            source = f" ({n['source']})" if n.get("source") else ""
            age    = f" [{n['age']}]"     if n.get("age")    else ""
            lines.append(f"• {n['title']}{source}{age}")
            if n["description"]:
                lines.append(f"  {n['description']}")
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
        return await get_cached_scout_result(q_hash, source="brave", max_age_hours=_CACHE_TTL_HOURS)
    except Exception:
        return None


async def _store_cached(
    q_hash: str, source: str, query: str, result: str,
    urls: list[str], state: "PipelineState"
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
