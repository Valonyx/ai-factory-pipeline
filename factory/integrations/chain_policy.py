"""
AI Factory Pipeline v5.8 — Chain Policy

FIX-CHAIN: mode-aware provider chain selection.

Maps the operator's Master axis (BASIC / BALANCED / TURBO / CUSTOM) to:
  - an ordered provider list (possibly overriding AI_PROVIDER_CHAIN)
  - a per-call latency cap (ms) after which the chain falls to the next provider
  - a cost gate for BASIC (zero paid providers)

The chain_policy module is the single authority that translates "master mode"
into a concrete provider ordering. ProviderChain handles status/fallback;
chain_policy handles the initial list + per-mode constraints.
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

logger = logging.getLogger("factory.integrations.chain_policy")

# ─────────────────────────────────────────────────────────────────────
# Latency caps per mode (ms).  If an in-flight call exceeds this
# threshold AND a cheaper fallback is available, the chain pre-empts
# the slow provider on the NEXT call (not mid-flight — async boundary).
# ─────────────────────────────────────────────────────────────────────
LATENCY_CAP_MS: dict[str, int] = {
    "BASIC":    30_000,   # generous — free providers are slower
    "BALANCED": 20_000,
    "TURBO":    10_000,   # aggressive — pay for speed
    "CUSTOM":   20_000,   # default for custom; caller may override
}

# ─────────────────────────────────────────────────────────────────────
# Canonical per-mode AI chains.
# These are applied when the env var AI_PROVIDER_CHAIN is not set AND
# the operator has not configured a CUSTOM chain in their prefs.
# ─────────────────────────────────────────────────────────────────────
_MODE_AI_CHAINS: dict[str, list[str]] = {
    # BASIC: free-only. Gemini + Groq + OpenRouter free models.
    # Anthropic is intentionally absent — it bills per token.
    "BASIC": ["gemini", "groq", "openrouter", "cerebras", "together", "mistral"],
    # BALANCED: paid-first when key present, full free fallback.
    "BALANCED": ["anthropic", "gemini", "groq", "openrouter", "cerebras", "together", "mistral"],
    # TURBO: best quality first, cost ignored.
    "TURBO":    ["anthropic", "gemini", "groq", "openrouter", "cerebras", "together", "mistral"],
    # CUSTOM: operator-configured — resolved at call time.
    "CUSTOM":   [],
}


def get_ai_chain_for_mode(
    mode_name: str,
    operator_prefs: dict | None = None,
) -> list[str]:
    """Return the ordered AI provider list for a given Master-axis mode.

    Resolution order:
      1. CUSTOM mode with operator_prefs["custom_ai_chain"] set → use that list
      2. AI_PROVIDER_CHAIN env var set (non-empty) → use that list (operator override)
      3. Canonical per-mode list from _MODE_AI_CHAINS

    Provider names are normalised via normalize_provider_name() so the
    operator can write "claude,gpt4" and get ["anthropic","openrouter"].
    """
    from factory.integrations.provider_chain import normalize_provider_name

    upper = (mode_name or "BALANCED").upper()

    # 1. CUSTOM mode — operator-supplied list in prefs
    if upper == "CUSTOM" and operator_prefs:
        raw = operator_prefs.get("custom_ai_chain", "")
        if raw and isinstance(raw, str):
            parsed = [normalize_provider_name(p.strip()) for p in raw.split(",") if p.strip()]
            if parsed:
                logger.debug(f"[chain-policy] CUSTOM chain from prefs: {parsed}")
                return parsed

    # 2. AI_PROVIDER_CHAIN env override (applies to all modes)
    env_chain = os.getenv("AI_PROVIDER_CHAIN", "").strip()
    if env_chain:
        parsed = [normalize_provider_name(p.strip()) for p in env_chain.split(",") if p.strip()]
        if parsed:
            logger.debug(f"[chain-policy] env AI_PROVIDER_CHAIN override: {parsed}")
            return parsed

    # 3. Canonical per-mode default
    chain = _MODE_AI_CHAINS.get(upper, _MODE_AI_CHAINS["BALANCED"])
    if not chain:
        # CUSTOM with no prefs entry — fall back to BALANCED
        chain = _MODE_AI_CHAINS["BALANCED"]
        logger.warning(
            f"[chain-policy] CUSTOM mode has no custom_ai_chain in prefs "
            f"and AI_PROVIDER_CHAIN is not set — falling back to BALANCED chain"
        )
    return list(chain)


def get_scout_chain_for_mode(
    mode_name: str,
    operator_prefs: dict | None = None,
) -> list[str]:
    """Return the ordered Scout provider list for a given Master-axis mode.

    BASIC only uses key-free scout providers to enforce the $0 cost gate.
    All other modes use the full chain from SCOUT_PROVIDER_CHAIN (or the
    canonical default).
    """
    from factory.integrations.provider_chain import normalize_provider_name

    upper = (mode_name or "BALANCED").upper()

    # CUSTOM — check prefs first
    if upper == "CUSTOM" and operator_prefs:
        raw = operator_prefs.get("custom_scout_chain", "")
        if raw and isinstance(raw, str):
            parsed = [normalize_provider_name(p.strip()) for p in raw.split(",") if p.strip()]
            if parsed:
                return parsed

    # Env override
    env_chain = os.getenv("SCOUT_PROVIDER_CHAIN", "").strip()
    if env_chain:
        parsed = [normalize_provider_name(p.strip()) for p in env_chain.split(",") if p.strip()]
        if parsed:
            if upper == "BASIC":
                parsed = _filter_paid_scout(parsed)
            return parsed if parsed else _free_scout_chain()

    # BASIC: key-free only
    if upper == "BASIC":
        return _free_scout_chain()

    # All others: full default
    from factory.integrations.provider_chain import _SCOUT_DEFAULT_CHAIN  # type: ignore[attr-defined]
    return list(_SCOUT_DEFAULT_CHAIN)


def _free_scout_chain() -> list[str]:
    """Scout providers that require no API key and incur no cost."""
    return ["duckduckgo", "wikipedia", "hackernews", "reddit", "stackoverflow", "github_search", "ai_scout"]


_PAID_SCOUT: frozenset[str] = frozenset({"perplexity", "brave", "tavily", "exa"})


def _filter_paid_scout(providers: Sequence[str]) -> list[str]:
    return [p for p in providers if p not in _PAID_SCOUT]


def latency_cap_ms(mode_name: str) -> int:
    """Return the per-call latency cap in milliseconds for the given mode."""
    return LATENCY_CAP_MS.get((mode_name or "BALANCED").upper(), LATENCY_CAP_MS["BALANCED"])


def exceeds_latency_cap(mode_name: str, observed_ms: float) -> bool:
    """Return True when a provider's observed latency exceeds the mode cap."""
    return observed_ms > latency_cap_ms(mode_name)
