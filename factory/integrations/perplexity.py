"""
AI Factory Pipeline v5.6 — Perplexity Sonar Client (Scout)

Implements:
  - §3.1   Perplexity Sonar integration
  - §3.1.1 API client with sonar / sonar-pro auto-selection
  - §2.2.3 Research Degradation Policy [C5]
  - ADR-049 Scout context-tier ceiling enforcement
  - FIX-19  Context tier limits

Spec Authority: v5.6 §3.1, §2.2.3, ADR-049, FIX-19
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from factory.core.state import (
    CONTEXT_TIER_LIMITS,
    PipelineState,
    RoleContract,
    SCOUT_MAX_CONTEXT_TIER,
)

logger = logging.getLogger("factory.integrations.perplexity")

# ═══════════════════════════════════════════════════════════════════
# §3.1.1 Pricing (per million tokens, USD)
# Verified 2026-02-27 from perplexity.ai/api-pricing
# ═══════════════════════════════════════════════════════════════════

PERPLEXITY_PRICING: dict[str, dict[str, float]] = {
    "sonar":     {"input": 1.00, "output": 1.00, "request_per_1k": 5.00},
    "sonar-pro": {"input": 3.00, "output": 15.00, "request_per_1k": 5.00},
}

# §3.1.2 Sonar Pro trigger keywords
SONAR_PRO_TRIGGERS = [
    "regulation", "compliance", "legal", "pdpl", "cst", "sama",
    "ministry of commerce", "license", "permit",
    "root cause", "dependency conflict", "breaking change",
    "migration guide", "deprecated",
    "competing apps", "market analysis", "trending", "design trends",
]

# ADR-049 / FIX-19: Hard ceiling on Scout context tier
_TIER_CEILING = SCOUT_MAX_CONTEXT_TIER  # from state.py


class PerplexityUnavailableError(Exception):
    """Raised when all degradation chain options are exhausted."""
    pass


# ═══════════════════════════════════════════════════════════════════
# §3.1.1 Model Selection
# ═══════════════════════════════════════════════════════════════════


def select_scout_model(prompt: str) -> str:
    """Auto-select sonar or sonar-pro based on prompt content.

    Spec: §3.1.2
    sonar-pro triggered by complexity keywords.
    """
    prompt_lower = prompt.lower()
    if any(trigger in prompt_lower for trigger in SONAR_PRO_TRIGGERS):
        return "sonar-pro"
    return "sonar"


def effective_tier(requested_tier: str) -> str:
    """Enforce SCOUT_MAX_CONTEXT_TIER ceiling (ADR-049 / FIX-19).

    Never allows a tier larger than the ceiling defined in state.py.
    """
    tier_order = ["small", "medium", "large"]
    ceiling_idx = tier_order.index(_TIER_CEILING) if _TIER_CEILING in tier_order else 1
    requested_idx = tier_order.index(requested_tier) if requested_tier in tier_order else 1
    return tier_order[min(requested_idx, ceiling_idx)]


# ═══════════════════════════════════════════════════════════════════
# §3.1 Real API Call
# ═══════════════════════════════════════════════════════════════════


async def call_perplexity(
    prompt: str,
    tier: str = "medium",
    state: Optional[PipelineState] = None,
) -> tuple[str, float, list[str]]:
    """Call Perplexity Sonar API.

    Spec: §3.1
    Returns (response_text, cost_usd, citations).
    Raises PerplexityUnavailableError on any API failure.
    """
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        raise PerplexityUnavailableError("PERPLEXITY_API_KEY not set")

    # Enforce tier ceiling and get limits
    capped_tier = effective_tier(tier)
    limits = CONTEXT_TIER_LIMITS.get(capped_tier, CONTEXT_TIER_LIMITS["medium"])

    # Truncate prompt to tier ceiling (4 chars ≈ 1 token)
    max_chars = limits["max_tokens"] * 4
    if len(prompt) > max_chars:
        prompt = prompt[:max_chars]
        logger.warning(
            f"Scout prompt truncated to {capped_tier} tier "
            f"({limits['max_tokens']} tokens)"
        )

    model = select_scout_model(prompt)

    timeout = httpx.Timeout(30.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": limits["max_tokens"],
                    "search_recency_filter": limits.get("recency_filter", "month"),
                    "web_search_options": {
                        "search_context_size": capped_tier,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

    except httpx.ConnectTimeout:
        raise PerplexityUnavailableError("Perplexity connect timeout")
    except httpx.ReadTimeout:
        raise PerplexityUnavailableError("Perplexity read timeout")
    except httpx.HTTPStatusError as e:
        raise PerplexityUnavailableError(
            f"Perplexity HTTP {e.response.status_code}: {e.response.text[:200]}"
        )
    except httpx.NetworkError as e:
        raise PerplexityUnavailableError(f"Perplexity network error: {e}")

    response_text = data["choices"][0]["message"]["content"]
    citations = _extract_citations(data)

    # Cost calculation
    usage = data.get("usage", {})
    pricing = PERPLEXITY_PRICING.get(model, PERPLEXITY_PRICING["sonar"])
    in_tok = usage.get("prompt_tokens", len(prompt) // 4)
    out_tok = usage.get("completion_tokens", len(response_text) // 4)
    cost = (
        in_tok / 1_000_000 * pricing["input"]
        + out_tok / 1_000_000 * pricing["output"]
        + pricing["request_per_1k"] / 1_000  # per-request fee
    )

    logger.info(
        f"Scout: model={model} tier={capped_tier} "
        f"tokens={in_tok}in/{out_tok}out "
        f"citations={len(citations)} cost=${cost:.4f}"
    )
    return response_text, cost, citations


def _extract_citations(data: dict) -> list[str]:
    """Extract citation URLs from Perplexity response.

    Handles both new search_results format and legacy citations format.
    """
    # New format: search_results list
    search_results = data.get("search_results", [])
    if search_results:
        return [r.get("url", "") for r in search_results if r.get("url")]

    # Legacy format: citations list
    citations = data.get("citations", [])
    if citations and isinstance(citations[0], str):
        return citations
    if citations and isinstance(citations[0], dict):
        return [c.get("url", "") for c in citations if c.get("url")]

    return []


# ═══════════════════════════════════════════════════════════════════
# §2.2.3 Research Degradation Policy [C5]
# ═══════════════════════════════════════════════════════════════════


async def call_perplexity_safe(
    prompt: str,
    contract: RoleContract,
    state: PipelineState,
    tier: str = "medium",
) -> tuple[str, float]:
    """Safe Scout call with full degradation chain.

    Spec: §2.2.3 Research Degradation Policy [C5]

    Chain:
      1. Real Perplexity API call
      2. Retry once on transient failure
      3. Return UNVERIFIED-tagged fallback (never halts pipeline)

    Never raises — Scout failures are non-fatal per spec.
    Returns (response_text, cost_usd).
    """
    # Dry-run / no key → mock immediately
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        capped_tier = effective_tier(tier)
        limits = CONTEXT_TIER_LIMITS.get(capped_tier, CONTEXT_TIER_LIMITS["medium"])
        model = select_scout_model(prompt)
        logger.info(
            f"[MOCK] Calling Perplexity {model} "
            f"(tier={capped_tier}, max_sources={limits.get('max_sources', 5)})"
        )
        return (
            f"[MOCK Perplexity {model}] Research for: {prompt[:100]}...",
            0.005,
        )

    # Attempt 1
    try:
        text, cost, citations = await call_perplexity(prompt, tier, state)
        # Append citation count for pipeline transparency
        if citations:
            text += f"\n\n[{len(citations)} sources consulted]"
        return text, cost
    except PerplexityUnavailableError as e:
        logger.warning(f"Scout attempt 1 failed: {e} — retrying")

    # Attempt 2 (retry with small tier to reduce timeout risk)
    try:
        text, cost, citations = await call_perplexity(prompt, "small", state)
        if citations:
            text += f"\n\n[{len(citations)} sources consulted]"
        return text, cost
    except PerplexityUnavailableError as e:
        logger.warning(f"Scout attempt 2 failed: {e} — using UNVERIFIED fallback")

    # Degradation fallback — never halts pipeline (§2.2.3 [C5])
    fallback = (
        f"[UNVERIFIED — Perplexity unavailable]\n"
        f"Research could not be completed for: {prompt[:200]}\n"
        f"Proceeding with available context. Manual verification required."
    )
    logger.warning(
        f"[{state.project_id}] Scout degraded to UNVERIFIED fallback"
    )
    return fallback, 0.0
