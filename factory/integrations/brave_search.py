"""
AI Factory Pipeline v5.8 — Brave Search Provider (Free Tier)

Brave Search API provides web search results without tracking.
Free tier: 2,000 queries/month (no credit card required).

Free account: https://brave.com/search/api (Data for Good plan)
API key env var: BRAVE_SEARCH_API_KEY

Output format matches the Scout contract so all downstream stages
receive the same structured research results regardless of provider.

Docs: https://api.search.brave.com/app/documentation/web-search/get-started
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.brave_search")

BRAVE_COST_PER_CALL: float = 0.0001  # free tier


async def call_brave_search(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query via Brave Search API.

    Returns (formatted_results, cost_usd).
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        logger.warning("[BRAVE] BRAVE_SEARCH_API_KEY not set — get free key at brave.com/search/api")
        raise ValueError("BRAVE_SEARCH_API_KEY not configured")

    # Extract search query from prompt (first 200 chars, cleaned)
    query = prompt.strip()[:200]

    import httpx
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": query,
        "count": 5,
        "text_decorations": False,
        "search_lang": "en",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
            )

        if response.status_code == 429:
            raise Exception("429 RESOURCE_EXHAUSTED — Brave Search rate limit")
        if response.status_code == 401:
            raise Exception("401 Unauthorized — check BRAVE_SEARCH_API_KEY")
        response.raise_for_status()

        data = response.json()
        results = data.get("web", {}).get("results", [])

        if not results:
            return (
                f"[BRAVE-SCOUT] No results found for: {query[:100]}",
                BRAVE_COST_PER_CALL,
            )

        lines = [f"[BRAVE-SCOUT] Research results for: {query[:100]}\n"]
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "No title")
            url = r.get("url", "")
            description = r.get("description", "No description")
            lines.append(f"{i}. {title}\n   {description}\n   Source: {url}")

        formatted = "\n\n".join(lines)
        logger.info(f"Brave Search [{state.project_id}]: {len(results)} results")
        return formatted, BRAVE_COST_PER_CALL

    except Exception as e:
        logger.error(f"Brave Search error: {e}")
        raise
