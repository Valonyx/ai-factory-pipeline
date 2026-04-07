"""
AI Factory Pipeline v5.6 — SearXNG Scout (Meta-Search, No Key, No Quota)

Routes search queries through a rotation of public SearXNG instances.
SearXNG aggregates results from Google, Bing, DuckDuckGo, and 70+ other
engines simultaneously — much broader coverage than any single provider.

No API key required. No signup. No quota.
Rotates across 5 public instances to distribute load and ensure availability.

Spec Authority: v5.6 §2.2.3 (Scout provider interface)
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.searxng_scout")

SEARXNG_COST_PER_CALL: float = 0.0

# ═══════════════════════════════════════════════════════════════════
# Public SearXNG Instance Rotation
# ═══════════════════════════════════════════════════════════════════

# Curated list of stable public instances. Rotated randomly each call
# to distribute load and avoid any single instance being overloaded.
# Instance health is implicitly tracked by request failures.
_PUBLIC_INSTANCES = [
    "https://searx.be",
    "https://search.inetol.net",
    "https://searxng.world",
    "https://opnxng.com",
    "https://searx.tiekoetter.com",
]

# ═══════════════════════════════════════════════════════════════════
# Category & Engine Routing
# ═══════════════════════════════════════════════════════════════════

# Map query domains to SearXNG engine groups for better results
_DOMAIN_ENGINES: dict[str, str] = {
    "tech":      "general,it",
    "legal":     "general",
    "market":    "general",
    "community": "general,social media",
    "factual":   "general,encyclopedias",
    "general":   "general",
}

_TIMEOUT = aiohttp.ClientTimeout(total=12)
_MAX_RESULTS = 5
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AI-Research-Bot/1.0)",
    "Accept": "application/json",
}


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

async def call_searxng(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
    domain: str = "general",
) -> tuple[str, float]:
    """Search via rotating public SearXNG instances.

    Tries up to 3 instances on failure. Returns formatted research
    results with titles, snippets, and source URLs.
    """
    query = prompt.strip()[:300]
    q_hash = _query_hash(query)

    # Cache check
    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[searxng] cache hit for '{query[:60]}'")
        return cached, SEARXNG_COST_PER_CALL

    engines = _DOMAIN_ENGINES.get(domain, "general")

    # Rotate instance order — shuffle once per call
    instances = _PUBLIC_INSTANCES.copy()
    random.shuffle(instances)

    last_error = ""
    for instance in instances[:3]:
        try:
            result = await _query_instance(instance, query, engines)
            if result:
                formatted = _format_results(result, query, instance)
                await _store_cached(q_hash, "searxng", query, formatted, state)
                logger.info(f"[searxng] {len(result)} results via {instance}")
                return formatted, SEARXNG_COST_PER_CALL
        except Exception as e:
            last_error = str(e)
            logger.debug(f"[searxng] {instance} failed: {e}")
            continue

    logger.warning(f"[searxng] all instances failed. Last error: {last_error}")
    return (
        f"[SEARXNG-UNAVAILABLE] All public SearXNG instances returned no results. "
        f"Query: {query[:100]}",
        SEARXNG_COST_PER_CALL,
    )


# ═══════════════════════════════════════════════════════════════════
# Instance Query
# ═══════════════════════════════════════════════════════════════════

async def _query_instance(
    base_url: str,
    query: str,
    engines: str,
) -> list[dict]:
    """Fetch results from a single SearXNG instance via its JSON API."""
    params = {
        "q":        query,
        "format":   "json",
        "engines":  engines,
        "safesearch": "0",
        "language": "en",
    }
    url = f"{base_url}/search"

    async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as session:
        async with session.get(url, params=params, allow_redirects=True) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            data = await resp.json(content_type=None)

    results = data.get("results", [])
    # Quality filter: non-empty content/snippet
    filtered = [
        r for r in results
        if r.get("content") or r.get("snippet")
    ]
    return filtered[:_MAX_RESULTS]


# ═══════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════

def _format_results(results: list[dict], query: str, instance: str) -> str:
    lines = [f"[SEARXNG META-SEARCH via {instance}]\nQuery: {query}\n"]
    for i, r in enumerate(results, 1):
        title   = r.get("title", "Untitled")
        snippet = r.get("content") or r.get("snippet", "")
        url     = r.get("url", "")
        # engines that returned this result
        engines = ", ".join(r.get("engines", []))
        lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet[:250]}")
        if engines:
            lines.append(f"   Sources: {engines}")
        if url:
            lines.append(f"   URL: {url}")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Cache Helpers
# ═══════════════════════════════════════════════════════════════════

import hashlib
import os

_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))


def _query_hash(q: str) -> str:
    return hashlib.md5(q.strip().lower().encode()).hexdigest()[:16]


async def _get_cached(q_hash: str) -> str | None:
    try:
        from factory.memory.mother_memory import get_cached_scout_result
        return await get_cached_scout_result(q_hash, source="searxng", max_age_hours=_CACHE_TTL_HOURS)
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
