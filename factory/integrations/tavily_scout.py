"""
AI Factory Pipeline v5.6 — Tavily Free-Tier Scout

DEV ALTERNATIVE for Perplexity Scout when API funds are unavailable.
Switch back to Perplexity by setting SCOUT_PROVIDER=perplexity in .env.

Free-tier limits (as of 2026-04):
  - 1,000 API calls/month, no credit card required
  - Get key at: app.tavily.com → sign up → API Keys
  - Package: tavily-python

Tavily returns structured search results with URLs, titles, and content
snippets. This module formats them to match the Scout's existing output
contract so all downstream stages receive the same format.

Dev note (NB3-DEV-002): Added as a free-tier Scout alternative when
Perplexity required a $50 minimum balance. The Scout degradation chain
(§2.2.3 [C5]) remains intact — Tavily is inserted as attempt #0 before
Perplexity attempts. Set SCOUT_PROVIDER=perplexity to bypass Tavily.

Spec Authority: v5.6 §2.2.3, §3.1, ADR-049, FIX-19
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract, PipelineState

logger = logging.getLogger("factory.integrations.tavily_scout")

# Nominal cost per search (Tavily free tier = $0)
TAVILY_COST_PER_CALL: float = 0.0001


async def call_tavily_scout(
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
) -> tuple[str, float]:
    """Execute a Scout research query via Tavily free-tier search API.

    Returns formatted research results matching the Scout output contract:
      - Numbered list of findings with source URLs
      - [UNVERIFIED] prefix removed (Tavily returns real sources)
      - [TAVILY-SCOUT] prefix to distinguish from Perplexity

    Falls back to UNVERIFIED stub when TAVILY_API_KEY is absent.
    """
    api_key = os.getenv("TAVILY_API_KEY", "")

    if not api_key:
        logger.warning(
            f"[{state.project_id}] TAVILY_API_KEY not set — "
            "Scout in UNVERIFIED fallback mode. "
            "Get free key at app.tavily.com"
        )
        return (
            f"[UNVERIFIED] No Scout provider configured. "
            f"Research query: {prompt[:200]}",
            0.0,
        )

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        # Run search synchronously (Tavily client is sync)
        import asyncio
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: client.search(
                query=prompt,
                max_results=5,
                include_answer=True,
                search_depth="advanced",
            ),
        )

        # Format output to match Scout contract
        lines: list[str] = ["[TAVILY-SCOUT] Research results:\n"]

        if results.get("answer"):
            lines.append(f"Summary: {results['answer']}\n")

        for i, result in enumerate(results.get("results", []), 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")[:300]
            lines.append(f"{i}. {title}\n   URL: {url}\n   {content}\n")

        formatted = "\n".join(lines)
        logger.info(
            f"[{state.project_id}] Tavily Scout: "
            f"{len(results.get('results', []))} results for '{prompt[:60]}'"
        )
        return formatted, TAVILY_COST_PER_CALL

    except Exception as e:
        logger.warning(
            f"[{state.project_id}] Tavily Scout failed: {e} — "
            "falling back to UNVERIFIED"
        )
        return (
            f"[UNVERIFIED] Tavily search failed ({e}). "
            f"Query: {prompt[:200]}",
            0.0,
        )
