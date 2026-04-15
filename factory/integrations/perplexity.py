"""
AI Factory Pipeline v5.8 — Perplexity Sonar Client (Scout)

Implements:
  - §3.1   Perplexity Sonar integration
  - §3.1.1 API client with sonar / sonar-pro auto-selection
  - §2.2.3 Research Degradation Policy [C5]
  - ADR-049 Scout context-tier ceiling enforcement
  - FIX-19  Context tier limits

Spec Authority: v5.8 §3.1, §2.2.3, ADR-049, FIX-19
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from factory.core.state import (
    CONTEXT_TIER_LIMITS,
    PipelineState,
    RoleContract,
)

# Module-level reference so tests can patch factory.integrations.perplexity.mother_memory
try:
    from factory.integrations.neo4j import mother_memory
except Exception:
    mother_memory = None  # type: ignore

logger = logging.getLogger("factory.integrations.perplexity")

# ═══════════════════════════════════════════════════════════════════
# §3.1.1 Pricing (per million tokens, USD)
# Verified 2026-02-27 from perplexity.ai/api-pricing
# ═══════════════════════════════════════════════════════════════════

PERPLEXITY_PRICING: dict[str, dict[str, float]] = {
    "sonar":                {"input": 1.00, "output": 1.00,  "request_per_1k": 5.00},
    "sonar-pro":            {"input": 3.00, "output": 15.00, "request_per_1k": 5.00},
    "sonar-reasoning-pro":  {"input": 2.00, "output": 8.00,  "request_per_1k": 5.00},
}

# Per-1k request fees by model and context tier (§3.1.1)
REQUEST_FEES_PER_1K: dict[str, dict[str, float]] = {
    "sonar":               {"low": 5.0, "medium": 8.0,  "high": 12.0},
    "sonar-pro":           {"low": 6.0, "medium": 10.0, "high": 14.0},
    "sonar-reasoning-pro": {"low": 6.0, "medium": 10.0, "high": 14.0},
}

# ADR-049 / FIX-19: Hard ceiling on Scout context tier.
# Module-level so tests can override: perplexity.SCOUT_MAX_CONTEXT_TIER = "small"
SCOUT_MAX_CONTEXT_TIER: str = os.getenv("SCOUT_MAX_CONTEXT_TIER", "medium")

# §3.1.2 Sonar Pro trigger keywords
SONAR_PRO_TRIGGERS = [
    "regulation", "compliance", "legal", "pdpl", "cst", "sama",
    "ministry of commerce", "license", "permit",
    "root cause", "dependency conflict", "breaking change",
    "migration guide", "deprecated",
    "competing apps", "market analysis", "trending", "design trends",
]

__all__ = [
    "PERPLEXITY_PRICING", "REQUEST_FEES_PER_1K", "CONTEXT_TIER_LIMITS",
    "SCOUT_MAX_CONTEXT_TIER", "SONAR_PRO_TRIGGERS", "PerplexityUnavailableError",
    "select_scout_model", "effective_tier", "calculate_cost",
    "extract_citations", "call_perplexity", "call_perplexity_safe",
    "_synthesize_from_cache", "reset_client", "get_perplexity_client",
]


class PerplexityUnavailableError(Exception):
    """Raised when all degradation chain options are exhausted."""
    pass


# ═══════════════════════════════════════════════════════════════════
# §3.1.1 Model Selection
# ═══════════════════════════════════════════════════════════════════

_TIER_TO_MODEL = {
    "simple":   "sonar",
    "standard": "sonar-pro",
    "deep":     "sonar-reasoning-pro",
}


def select_scout_model(tier: str, requires_reasoning: bool = False) -> str:
    """Select Sonar model based on query tier.

    Spec: §3.1.2
    - simple   → sonar
    - standard → sonar-pro
    - deep     → sonar-reasoning-pro
    - requires_reasoning=True → sonar-reasoning-pro
    """
    if requires_reasoning:
        return "sonar-reasoning-pro"
    return _TIER_TO_MODEL.get(tier.lower(), "sonar-pro")


def effective_tier(requested_tier: Optional[str] = None) -> str:
    """Return the effective Scout context tier, respecting the ceiling.

    ADR-049 / FIX-19: Never exceeds SCOUT_MAX_CONTEXT_TIER.
    When called with no args, returns the module-level ceiling (validated).
    """
    tier_order = ["small", "medium", "large"]
    # Read module attribute dynamically so test overrides work
    ceiling = sys.modules[__name__].SCOUT_MAX_CONTEXT_TIER
    ceiling_idx = tier_order.index(ceiling) if ceiling in tier_order else 1  # default medium

    if requested_tier is None:
        return tier_order[ceiling_idx]

    requested_idx = tier_order.index(requested_tier) if requested_tier in tier_order else 1
    return tier_order[min(requested_idx, ceiling_idx)]


# ═══════════════════════════════════════════════════════════════════
# §3.1 OpenAI-compatible client (Perplexity uses OpenAI SDK)
# ═══════════════════════════════════════════════════════════════════

_client = None  # AsyncOpenAI singleton


def reset_client() -> None:
    """Reset the client singleton (used in tests)."""
    global _client
    _client = None


def get_perplexity_client():
    """Return (or create) the Perplexity AsyncOpenAI client singleton."""
    global _client
    if _client is None:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise PerplexityUnavailableError("openai package not installed")
        api_key = os.getenv("PERPLEXITY_API_KEY", "")
        if not api_key:
            raise PerplexityUnavailableError("PERPLEXITY_API_KEY not set")
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.perplexity.ai",
        )
    return _client


# ═══════════════════════════════════════════════════════════════════
# §3.1 Real API Call
# ═══════════════════════════════════════════════════════════════════


async def call_perplexity(
    query: str,
    model: str = "sonar-pro",
    context_tier: str = "medium",
    max_tokens: Optional[int] = None,
) -> tuple[str, float, list[dict], dict]:
    """Call Perplexity Sonar API.

    Spec: §3.1
    Returns (response_text, cost_usd, citations, usage_dict).
    Raises PerplexityUnavailableError on any API failure.
    """
    # Enforce tier ceiling
    capped_tier = effective_tier(context_tier)
    limits = CONTEXT_TIER_LIMITS.get(capped_tier, CONTEXT_TIER_LIMITS["medium"])

    # Clamp max_tokens to tier ceiling
    tier_max = limits["max_tokens"]
    if max_tokens is None:
        max_tokens = tier_max
    else:
        max_tokens = min(max_tokens, tier_max)

    # Truncate prompt to tier ceiling (4 chars ≈ 1 token)
    max_chars = tier_max * 4
    if len(query) > max_chars:
        query = query[:max_chars]
        logger.warning(f"Scout prompt truncated to {capped_tier} tier ({tier_max} tokens)")

    client = get_perplexity_client()

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": query}],
            max_tokens=max_tokens,
        )
    except PerplexityUnavailableError:
        raise
    except Exception as e:
        raise PerplexityUnavailableError(f"Perplexity API error: {e}")

    response_text = response.choices[0].message.content
    citations = extract_citations(response)

    # Usage and cost
    usage_obj = response.usage
    in_tok = getattr(usage_obj, "prompt_tokens", len(query) // 4)
    out_tok = getattr(usage_obj, "completion_tokens", len(response_text) // 4)
    usage = {"input_tokens": in_tok, "output_tokens": out_tok}

    pricing = PERPLEXITY_PRICING.get(model, PERPLEXITY_PRICING["sonar"])
    request_fee = REQUEST_FEES_PER_1K.get(model, REQUEST_FEES_PER_1K["sonar"]).get(capped_tier, 8.0) / 1_000
    cost = (
        in_tok / 1_000_000 * pricing["input"]
        + out_tok / 1_000_000 * pricing["output"]
        + request_fee
    )

    logger.info(
        f"Scout: model={model} tier={capped_tier} "
        f"tokens={in_tok}in/{out_tok}out "
        f"citations={len(citations)} cost=${cost:.4f}"
    )
    return response_text, cost, citations, usage


# ═══════════════════════════════════════════════════════════════════
# Citation extraction
# ═══════════════════════════════════════════════════════════════════


def _item_to_dict(item) -> dict:
    """Convert a citation item (dict or object) to a plain dict."""
    if isinstance(item, dict):
        return {
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "date": item.get("date", ""),
            "snippet": item.get("snippet", ""),
        }
    # SimpleNamespace or other object
    return {
        "url": getattr(item, "url", ""),
        "title": getattr(item, "title", ""),
        "date": getattr(item, "date", ""),
        "snippet": getattr(item, "snippet", ""),
    }


def extract_citations(response) -> list[dict]:
    """Extract citation dicts from a Perplexity response object.

    Handles:
    - New API: response.search_results (list of dicts or objects)
    - Legacy API: response.citations (list of URL strings or dicts)
    Returns list of {"url": ..., "title": ..., "date": ..., "snippet": ...}
    """
    # New format: search_results attribute
    search_results = getattr(response, "search_results", None)
    if search_results:
        return [_item_to_dict(r) for r in search_results if _item_to_dict(r).get("url") or getattr(r, "url", "") or (isinstance(r, dict) and r.get("url"))]

    # Legacy format: citations attribute
    citations = getattr(response, "citations", None)
    if citations:
        result = []
        for c in citations:
            if isinstance(c, str):
                result.append({"url": c, "title": "", "date": "", "snippet": ""})
            elif isinstance(c, dict):
                result.append(_item_to_dict(c))
            else:
                result.append(_item_to_dict(c))
        return result

    return []


# ═══════════════════════════════════════════════════════════════════
# §2.2.3 Research Degradation Policy [C5]
# ═══════════════════════════════════════════════════════════════════


def _synthesize_from_cache(cached: list) -> str:
    """Synthesize a response from cached research entries.

    Spec: §2.2.3 [C5] degradation chain
    Returns attributed text or "" if empty.
    """
    if not cached:
        return ""
    lines = []
    for item in cached:
        source_id = item.get("source_id", "?")
        content = item.get("content", "")
        url = item.get("url", "")
        lines.append(f"[{source_id}] {content} ({url})")
    return "\n".join(lines)


async def call_perplexity_safe(
    prompt: str,
    contract,
    state: PipelineState,
    tier: str = "medium",
) -> tuple[str, float]:
    """Safe Scout call with full degradation chain.

    Spec: §2.2.3 Research Degradation Policy [C5]

    Chain:
      1. Real Perplexity API call
      2. Retry once on transient failure
      3. Cache synthesis from Mother Memory
      4. Return UNVERIFIED-tagged fallback (never halts pipeline)

    Never raises — Scout failures are non-fatal per spec.
    Returns (response_text, cost_usd).
    """
    model = getattr(contract, "model", "sonar-pro")
    capped_tier = effective_tier(tier)
    limits = CONTEXT_TIER_LIMITS.get(capped_tier, CONTEXT_TIER_LIMITS["medium"])

    # Truncate prompt to tier ceiling
    max_chars = limits["max_tokens"] * 4
    if len(prompt) > max_chars:
        prompt = prompt[:max_chars]

    # Attempt 1
    try:
        client = get_perplexity_client()
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=limits["max_tokens"],
        )
        text = response.choices[0].message.content
        citations = extract_citations(response)
        usage_obj = response.usage
        in_tok = getattr(usage_obj, "prompt_tokens", len(prompt) // 4)
        out_tok = getattr(usage_obj, "completion_tokens", len(text) // 4)
        pricing = PERPLEXITY_PRICING.get(model, PERPLEXITY_PRICING["sonar"])
        cost = (
            in_tok / 1_000_000 * pricing["input"]
            + out_tok / 1_000_000 * pricing["output"]
            + pricing["request_per_1k"] / 1_000
        )
        if citations:
            text += f"\n\n[{len(citations)} sources consulted]"
        return text, cost
    except PerplexityUnavailableError as e:
        logger.warning(f"Scout attempt 1 failed: {e} — retrying")
    except Exception as e:
        logger.warning(f"Scout attempt 1 error: {e} — retrying")

    # Attempt 2 with small tier
    try:
        client = get_perplexity_client()
        small_limits = CONTEXT_TIER_LIMITS.get("small", CONTEXT_TIER_LIMITS["medium"])
        small_prompt = prompt[:small_limits["max_tokens"] * 4]
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": small_prompt}],
            max_tokens=small_limits["max_tokens"],
        )
        text = response.choices[0].message.content
        return text, 0.001
    except Exception as e:
        logger.warning(f"Scout attempt 2 failed: {e} — using cache/UNVERIFIED")

    # Cache fallback (Mother Memory)
    try:
        _mm = sys.modules[__name__].mother_memory
        if _mm is None:
            raise ImportError("mother_memory not available")
        cached = await _mm(
            stack=getattr(state, "stack", "react-native"),
            screens=[],
            category=(state.project_metadata.get("app_category", "other")
                      if hasattr(state, "project_metadata") else "other"),
        )
        if cached:
            synthesized = _synthesize_from_cache(cached if isinstance(cached, list) else [cached])
            if synthesized:
                return (
                    f"[CACHED — from Mother Memory]\n{synthesized}",
                    0.0,
                )
    except Exception:
        pass

    # Final fallback — never halts pipeline (§2.2.3 [C5])
    fallback = (
        f"[UNVERIFIED — Perplexity unavailable]\n"
        f"Research could not be completed for: {prompt[:200]}\n"
        f"Proceeding with available context. Manual verification required."
    )
    logger.warning(f"[{state.project_id}] Scout degraded to UNVERIFIED fallback")
    return fallback, 0.0


# ═══════════════════════════════════════════════════════════════════
# §3.1.1 Cost Calculator
# ═══════════════════════════════════════════════════════════════════


def calculate_cost(model: str, input_tokens: int, output_tokens: int, tier: str = "medium") -> float:
    """Calculate Perplexity call cost including request fee.

    Spec: §3.1.1
    Total = token cost + per-request fee
    """
    pricing = PERPLEXITY_PRICING.get(model, PERPLEXITY_PRICING["sonar"])
    token_cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
    )
    request_fee = REQUEST_FEES_PER_1K.get(model, REQUEST_FEES_PER_1K["sonar"]).get(tier, 8.0) / 1000
    return token_cost + request_fee
