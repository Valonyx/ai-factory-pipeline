"""
Tests for factory.core.provider_intelligence — ProviderIntelligence,
ROLE_PROVIDERS, PROVIDER_CAPABILITIES, and capability-filtered chains.

Issue 20: Full Free Provider Integration + Smart Chain
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from factory.core.provider_intelligence import (
    PROVIDER_CAPABILITIES,
    ROLE_PROVIDERS,
    Capability,
    ProviderIntelligence,
    ProviderMetrics,
    RateLimitInfo,
)


# ── Helpers ───────────────────────────────────────────────────────

def fresh_pi() -> ProviderIntelligence:
    """Return a fresh ProviderIntelligence instance (no shared state)."""
    return ProviderIntelligence()


# ── 1. STRATEGIST + BASIC → free providers only, no anthropic ────

def test_get_chain_for_role_basic_strategist():
    pi = fresh_pi()
    chain = pi.get_chain_for_role("STRATEGIST", "BASIC")
    assert len(chain) > 0, "chain must not be empty"
    assert "anthropic" not in chain, "BASIC mode must not include anthropic"
    # All providers in chain must support REASONING
    for p in chain:
        assert Capability.REASONING in PROVIDER_CAPABILITIES.get(p, set()), (
            f"{p} in BASIC STRATEGIST chain but lacks REASONING capability"
        )


# ── 2. ENGINEER + TURBO → anthropic is first ────────────────────

def test_get_chain_for_role_turbo_engineer():
    pi = fresh_pi()
    chain = pi.get_chain_for_role("ENGINEER", "TURBO")
    assert len(chain) > 0, "TURBO ENGINEER chain must not be empty"
    assert chain[0] == "anthropic", (
        f"TURBO ENGINEER chain should start with anthropic, got: {chain[0]}"
    )


# ── 3. Capability filter — SCOUT requires SEARCH_GROUNDING ───────

def test_capability_filter():
    pi = fresh_pi()
    # SCOUT BASIC chain — all entries must have SEARCH_GROUNDING
    chain = pi.get_chain_for_role("SCOUT", "BASIC")
    for provider in chain:
        caps = PROVIDER_CAPABILITIES.get(provider, set())
        assert Capability.SEARCH_GROUNDING in caps, (
            f"{provider} in SCOUT chain but lacks SEARCH_GROUNDING"
        )
    # Providers with only CHAT should NOT appear
    chat_only = [
        p for p, caps in PROVIDER_CAPABILITIES.items()
        if caps == {Capability.CHAT}
    ]
    for p in chat_only:
        assert p not in chain, f"chat-only provider {p} should not be in SCOUT chain"


# ── 4. select_provider skips exhausted providers ─────────────────

def test_select_provider_skips_exhausted():
    pi = fresh_pi()
    chain = pi.get_chain_for_role("STRATEGIST", "BASIC")
    assert len(chain) >= 2, "need at least 2 providers to test skip"
    first = chain[0]
    # Exhaust the first provider
    pi.on_provider_exhausted(first, reset_in_seconds=9999)
    selected = pi.select_provider("STRATEGIST", "BASIC")
    assert selected != first, "select_provider must skip exhausted provider"
    assert selected is not None, "a non-exhausted fallback must be found"


# ── 5. record_call updates metrics ───────────────────────────────

def test_record_call_updates_metrics():
    pi = fresh_pi()
    pi.record_call("groq", 150.0, True)
    m = pi._metrics["groq"]
    assert m.success_count == 1
    assert m.avg_latency_ms > 0.0
    assert m.avg_latency_ms == pytest.approx(150.0)


# ── 6. Rate-limit pre-switch exhausts provider ───────────────────

def test_rate_limit_pre_switch():
    pi = fresh_pi()
    rl = RateLimitInfo(
        requests_remaining=5,
        reset_at=time.time() + 3600,
    )
    pi.record_call("groq", 100.0, True, rate_limit=rl)
    m = pi._metrics["groq"]
    assert not m.is_available(), (
        "provider with <10 requests remaining must be marked exhausted"
    )


# ── 7. on_provider_exhausted causes select to skip provider ──────

def test_on_provider_exhausted():
    pi = fresh_pi()
    pi.on_provider_exhausted("gemini", reset_in_seconds=9999)
    m = pi._metrics["gemini"]
    assert not m.is_available()
    # STRATEGIST BALANCED starts with anthropic — exhaust that too, gemini skipped
    pi.on_provider_exhausted("anthropic", reset_in_seconds=9999)
    selected = pi.select_provider("STRATEGIST", "BALANCED")
    assert selected not in ("anthropic", "gemini"), (
        "select_provider must skip all exhausted providers"
    )


# ── 8. status_message contains role names ────────────────────────

def test_status_message_contains_roles():
    pi = fresh_pi()
    msg = pi.status_message()
    assert "STRATEGIST" in msg
    assert "ENGINEER" in msg


# ── 9. ROLE_PROVIDERS has all four roles ─────────────────────────

def test_role_providers_all_roles_present():
    assert "STRATEGIST" in ROLE_PROVIDERS
    assert "ENGINEER" in ROLE_PROVIDERS
    assert "QUICK_FIX" in ROLE_PROVIDERS
    assert "SCOUT" in ROLE_PROVIDERS


# ── 10. Chat-only providers not in SCOUT chain ───────────────────

def test_provider_capabilities_no_scout_in_chat_only():
    """Providers with only CHAT capability should not appear in SCOUT chains."""
    pi = fresh_pi()
    for mode in ("BASIC", "BALANCED", "CUSTOM", "TURBO"):
        chain = pi.get_chain_for_role("SCOUT", mode)
        for provider in chain:
            caps = PROVIDER_CAPABILITIES.get(provider, set())
            assert Capability.SEARCH_GROUNDING in caps, (
                f"SCOUT/{mode}: {provider} lacks SEARCH_GROUNDING"
            )
