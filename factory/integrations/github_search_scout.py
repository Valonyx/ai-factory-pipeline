"""
AI Factory Pipeline v5.8 — GitHub Search Scout (Code/Repo Search, GITHUB_TOKEN)

Uses the existing GITHUB_TOKEN to search GitHub repositories, code, and topics.
Provides real-world implementation examples, popular libraries, and community
projects relevant to technical questions.

Authenticated: 5,000 req/hour. Falls back to 60 req/hour without token.
No separate signup needed — reuses the existing GITHUB_TOKEN from .env.

Best for: finding reference implementations, popular libraries by category,
code snippets showing API usage, framework adoption, and real project patterns.

Spec Authority: v5.8 §2.2.3 (Scout provider interface)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.github_search_scout")

GITHUB_COST_PER_CALL: float = 0.0
_CACHE_TTL_HOURS: int = int(os.getenv("SCOUT_CACHE_TTL_HOURS", "4"))
_GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

_TIMEOUT = aiohttp.ClientTimeout(total=12)
_BASE_URL = "https://api.github.com"
_MAX_REPOS = 4

# ═══════════════════════════════════════════════════════════════════
# Search Strategy by Domain
# ═══════════════════════════════════════════════════════════════════

# Each domain gets a different search mode:
#   "repos"  — find popular repositories (stars-sorted)
#   "topics" — find topic pages + top repos under that topic
#   "code"   — full-text code search (requires auth, uses more quota)
_DOMAIN_MODE: dict[str, str] = {
    "tech":      "repos",
    "market":    "repos",
    "legal":     "topics",
    "community": "repos",
    "factual":   "repos",
    "general":   "repos",
}

# Language hints per domain to narrow repo search
_DOMAIN_LANGUAGES: dict[str, str] = {
    "tech":    "language:TypeScript OR language:Python OR language:Kotlin OR language:Swift",
    "market":  "",
    "legal":   "",
    "general": "",
}


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

async def call_github_search(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
    domain: str = "tech",
) -> tuple[str, float]:
    """Search GitHub for relevant repositories and implementations.

    Returns repository names, descriptions, star counts, and topics,
    giving the Strategist a view of real-world adoption and patterns.
    """
    query = prompt.strip()[:200]
    q_hash = _query_hash(query)

    cached = await _get_cached(q_hash)
    if cached:
        logger.info(f"[github-search] cache hit for '{query[:60]}'")
        return cached, GITHUB_COST_PER_CALL

    mode = _DOMAIN_MODE.get(domain, "repos")
    lang_filter = _DOMAIN_LANGUAGES.get(domain, "")

    # Build search query
    search_q = query
    if lang_filter:
        search_q = f"{query} {lang_filter}"

    repos = await _search_repos(search_q)

    if not repos:
        return (
            f"[GITHUB-SEARCH-NO-RESULTS] No GitHub repositories found for: {query[:100]}",
            GITHUB_COST_PER_CALL,
        )

    formatted = _format_results(repos, query)
    await _store_cached(q_hash, "github_search", query, formatted, state)
    logger.info(f"[github-search] {len(repos)} repos found for '{query[:60]}'")
    return formatted, GITHUB_COST_PER_CALL


# ═══════════════════════════════════════════════════════════════════
# GitHub API Calls
# ═══════════════════════════════════════════════════════════════════

def _build_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if _GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {_GITHUB_TOKEN}"
    return headers


async def _search_repos(query: str) -> list[dict]:
    """Search GitHub repositories, sorted by stars."""
    params = {
        "q":        query,
        "sort":     "stars",
        "order":    "desc",
        "per_page": _MAX_REPOS + 2,  # fetch extra, filter below
    }
    try:
        async with aiohttp.ClientSession(
            timeout=_TIMEOUT, headers=_build_headers()
        ) as session:
            async with session.get(
                f"{_BASE_URL}/search/repositories", params=params
            ) as resp:
                _log_rate_limit(resp.headers)
                if resp.status == 403:
                    logger.warning("[github-search] rate limit hit")
                    return []
                if resp.status != 200:
                    logger.debug(f"[github-search] HTTP {resp.status}")
                    return []
                data = await resp.json()

        items = data.get("items", [])
        # Filter: must have meaningful description and some stars
        filtered = [
            r for r in items
            if r.get("description") and r.get("stargazers_count", 0) >= 10
        ]
        return filtered[:_MAX_REPOS]

    except Exception as e:
        logger.debug(f"[github-search] error: {e}")
        return []


def _log_rate_limit(headers: "aiohttp.CIMultiDictProxy") -> None:
    remaining = headers.get("X-RateLimit-Remaining", "?")
    reset     = headers.get("X-RateLimit-Reset", "")
    if remaining != "?" and int(remaining) < 20:
        logger.warning(f"[github-search] rate limit low: {remaining} remaining")


# ═══════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════

def _format_results(repos: list[dict], query: str) -> str:
    lines = [f"[GITHUB SEARCH — Repository Landscape]", f"Query: {query}", ""]
    for i, r in enumerate(repos, 1):
        name        = r.get("full_name", "unknown/unknown")
        desc        = r.get("description", "No description")[:180]
        stars       = r.get("stargazers_count", 0)
        language    = r.get("language", "")
        topics      = ", ".join(r.get("topics", [])[:6])
        url         = r.get("html_url", "")
        updated     = r.get("updated_at", "")[:10]

        lines.append(f"{i}. {name} ★{stars:,}")
        lines.append(f"   {desc}")
        if language:
            lines.append(f"   Language: {language}")
        if topics:
            lines.append(f"   Topics: {topics}")
        lines.append(f"   Last updated: {updated} | {url}")
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
        return await get_cached_scout_result(q_hash, source="github_search", max_age_hours=_CACHE_TTL_HOURS)
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
