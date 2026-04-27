"""
Tests for FIX-CHAIN: mode-aware provider chain selection, latency caps,
and graceful handling of all-providers-unreachable scenarios.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("PIPELINE_ENV", "ci")


# ─── get_ai_chain_for_mode ────────────────────────────────────────────────────

def test_basic_excludes_paid_providers():
    """BASIC mode must not include Anthropic (billed per token)."""
    os.environ.pop("AI_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_ai_chain_for_mode
    chain = get_ai_chain_for_mode("BASIC")
    assert "anthropic" not in chain, "BASIC mode must exclude paid Anthropic"
    assert len(chain) > 0


def test_balanced_includes_both_paid_and_free():
    """BALANCED mode must include anthropic AND at least one free provider."""
    os.environ.pop("AI_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_ai_chain_for_mode
    chain = get_ai_chain_for_mode("BALANCED")
    assert "anthropic" in chain
    free_providers = {"gemini", "groq", "openrouter", "cerebras", "together", "mistral"}
    assert any(p in free_providers for p in chain), "BALANCED should include free fallbacks"


def test_turbo_starts_with_highest_quality():
    """TURBO mode must start with anthropic (highest quality)."""
    os.environ.pop("AI_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_ai_chain_for_mode
    chain = get_ai_chain_for_mode("TURBO")
    assert chain[0] == "anthropic", "TURBO mode must prioritize anthropic"


def test_custom_mode_uses_prefs_chain():
    """CUSTOM mode with operator_prefs must use the custom_ai_chain list."""
    os.environ.pop("AI_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_ai_chain_for_mode
    prefs = {"custom_ai_chain": "anthropic,gemini"}
    chain = get_ai_chain_for_mode("CUSTOM", operator_prefs=prefs)
    assert chain == ["anthropic", "gemini"]


def test_custom_mode_fallback_when_no_prefs():
    """CUSTOM mode with no prefs/env must fall back to BALANCED chain."""
    os.environ.pop("AI_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_ai_chain_for_mode, _MODE_AI_CHAINS
    chain = get_ai_chain_for_mode("CUSTOM", operator_prefs={})
    assert chain == _MODE_AI_CHAINS["BALANCED"]


def test_env_override_takes_precedence():
    """AI_PROVIDER_CHAIN env var must override the mode-based chain."""
    os.environ["AI_PROVIDER_CHAIN"] = "gemini,groq"
    try:
        from importlib import reload
        import factory.integrations.chain_policy as cp
        chain = cp.get_ai_chain_for_mode("TURBO")
        assert chain == ["gemini", "groq"]
    finally:
        del os.environ["AI_PROVIDER_CHAIN"]


# ─── Latency cap ─────────────────────────────────────────────────────────────

def test_latency_cap_drops_slow_providers():
    from factory.integrations.chain_policy import exceeds_latency_cap, latency_cap_ms

    cap = latency_cap_ms("TURBO")
    assert cap == 10_000

    assert exceeds_latency_cap("TURBO", 11_000) is True
    assert exceeds_latency_cap("TURBO", 9_000) is False


def test_basic_has_most_generous_latency_cap():
    from factory.integrations.chain_policy import latency_cap_ms
    assert latency_cap_ms("BASIC") >= latency_cap_ms("BALANCED")
    assert latency_cap_ms("BALANCED") >= latency_cap_ms("TURBO")


def test_unknown_mode_uses_balanced_cap():
    from factory.integrations.chain_policy import latency_cap_ms, LATENCY_CAP_MS
    assert latency_cap_ms("UNKNOWN") == LATENCY_CAP_MS["BALANCED"]


# ─── Scout chain ─────────────────────────────────────────────────────────────

def test_basic_scout_excludes_paid():
    os.environ.pop("SCOUT_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_scout_chain_for_mode, _PAID_SCOUT
    chain = get_scout_chain_for_mode("BASIC")
    overlap = set(chain) & _PAID_SCOUT
    assert not overlap, f"BASIC scout chain must not include paid providers: {overlap}"


def test_balanced_scout_uses_full_chain():
    os.environ.pop("SCOUT_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_scout_chain_for_mode
    chain = get_scout_chain_for_mode("BALANCED")
    assert len(chain) >= 3


# ─── Graceful all-providers-unreachable ──────────────────────────────────────

def test_chain_handles_empty_provider_list_gracefully():
    """get_ai_chain_for_mode must never return an empty list for named modes."""
    os.environ.pop("AI_PROVIDER_CHAIN", None)
    from factory.integrations.chain_policy import get_ai_chain_for_mode
    for mode in ("BASIC", "BALANCED", "TURBO"):
        chain = get_ai_chain_for_mode(mode)
        assert chain, f"Mode {mode} returned empty provider chain"
