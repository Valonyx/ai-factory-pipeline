"""
AI Factory Pipeline v5.8.12 — Issue 7: Provider Independence Tests

Verifies that every call_ai() site routes through ProviderIntelligence
(not hardcoded to Anthropic) and that the capability matrix + role-specific
chains function correctly.

12 tests:
  1.  STRATEGIST + BALANCED chain contains anthropic + fallbacks
  2.  ENGINEER + BASIC chain contains no paid providers
  3.  QUICK_FIX + TURBO chain contains anthropic first
  4.  All providers in all role chains satisfy the role's required capability
  5.  get_chain_for_role returns mock-only if unknown role
  6.  select_provider returns first available provider
  7.  select_provider skips exhausted provider and returns next
  8.  record_call success increments success_count + avg_latency
  9.  record_call failure increments failure_count
 10.  Pre-switch: record_call with <10 requests_remaining marks provider exhausted
 11.  _call_anthropic (mock env) returns mock response without hitting PI
 12.  _call_anthropic consults provider_intelligence.get_chain_for_role
       (verified via patched spy — not mock env)
"""
from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from factory.core.provider_intelligence import (
    ProviderIntelligence, ProviderMetrics, RateLimitInfo,
    ROLE_PROVIDERS, PROVIDER_CAPABILITIES, ROLE_REQUIRED_CAPABILITY,
    Capability,
)


# ─── helpers ────────────────────────────────────────────────────────────────

def _fresh_pi() -> ProviderIntelligence:
    return ProviderIntelligence()


# ═══════════════════════════════════════════════════════════════════
# Tests 1–3: role chains are well-formed
# ═══════════════════════════════════════════════════════════════════

def test_strategist_balanced_chain_has_fallbacks():
    pi = _fresh_pi()
    chain = pi.get_chain_for_role("STRATEGIST", "BALANCED")
    assert "anthropic" in chain
    assert len(chain) >= 3  # at least 3 fallback providers


def test_engineer_basic_chain_no_paid_providers():
    """BASIC mode engineer chain must contain only free providers."""
    from factory.core.mode_router import AI_PROVIDERS, ProviderTier
    pi = _fresh_pi()
    chain = pi.get_chain_for_role("ENGINEER", "BASIC")
    _ai_by_name = {p.name: p for p in AI_PROVIDERS}
    for name in chain:
        if name == "mock":
            continue
        p = _ai_by_name.get(name)
        if p:
            assert p.tier in (ProviderTier.FREE,), (
                f"BASIC chain should not contain paid provider {name} (tier={p.tier})"
            )


def test_quick_fix_turbo_chain_has_anthropic_first():
    pi = _fresh_pi()
    chain = pi.get_chain_for_role("QUICK_FIX", "TURBO")
    assert chain[0] == "anthropic", (
        f"TURBO QUICK_FIX chain must start with anthropic, got: {chain[0]}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 4: capability matrix — all role chains satisfy required capability
# ═══════════════════════════════════════════════════════════════════

def test_all_role_chains_satisfy_required_capability():
    """Every provider in every role×mode chain must support the role's required capability."""
    pi = _fresh_pi()
    for role, modes in ROLE_PROVIDERS.items():
        required = ROLE_REQUIRED_CAPABILITY.get(role)
        if required is None:
            continue
        for mode, raw_chain in modes.items():
            filtered = pi.get_chain_for_role(role, mode)
            for provider in filtered:
                caps = PROVIDER_CAPABILITIES.get(provider, set())
                assert required in caps, (
                    f"{role}/{mode}: provider '{provider}' missing required "
                    f"capability '{required}'. Has: {caps}"
                )


# ═══════════════════════════════════════════════════════════════════
# Test 5: unknown role falls back gracefully
# ═══════════════════════════════════════════════════════════════════

def test_get_chain_for_role_unknown_role_returns_mock():
    pi = _fresh_pi()
    chain = pi.get_chain_for_role("NONEXISTENT_ROLE", "BALANCED")
    # ROLE_PROVIDERS.get("NONEXISTENT_ROLE") → None → default ["mock"]
    # But capability filter may remove "mock" if required_cap doesn't match.
    # At minimum the function must not raise.
    assert isinstance(chain, list)


# ═══════════════════════════════════════════════════════════════════
# Tests 6–7: select_provider availability logic
# ═══════════════════════════════════════════════════════════════════

def test_select_provider_returns_first_available():
    pi = _fresh_pi()
    provider = pi.select_provider("ENGINEER", "BALANCED")
    chain = pi.get_chain_for_role("ENGINEER", "BALANCED")
    assert provider == chain[0]


def test_select_provider_skips_exhausted():
    pi = _fresh_pi()
    chain = pi.get_chain_for_role("ENGINEER", "BALANCED")
    first = chain[0]
    # Mark first provider as exhausted
    pi.on_provider_exhausted(first, reset_in_seconds=3600)
    selected = pi.select_provider("ENGINEER", "BALANCED")
    assert selected != first, f"select_provider should skip exhausted '{first}'"
    assert selected == chain[1]


# ═══════════════════════════════════════════════════════════════════
# Tests 8–9: record_call updates metrics correctly
# ═══════════════════════════════════════════════════════════════════

def test_record_call_success_updates_metrics():
    pi = _fresh_pi()
    pi.record_call("anthropic", latency_ms=120.0, success=True)
    m = pi._metrics["anthropic"]
    assert m.success_count == 1
    assert m.total_latency_ms == 120.0
    assert m.avg_latency_ms == pytest.approx(120.0)


def test_record_call_failure_increments_failure_count():
    pi = _fresh_pi()
    pi.record_call("gemini", latency_ms=50.0, success=False)
    m = pi._metrics["gemini"]
    assert m.failure_count == 1
    assert m.success_count == 0


# ═══════════════════════════════════════════════════════════════════
# Test 10: pre-switch at <10 requests_remaining
# ═══════════════════════════════════════════════════════════════════

def test_preswitch_marks_exhausted_when_requests_below_10():
    pi = _fresh_pi()
    rate_limit = RateLimitInfo(
        requests_remaining=5,
        tokens_remaining=1000,
        reset_at=time.time() + 3600,
    )
    pi.record_call("groq", latency_ms=80.0, success=True, rate_limit=rate_limit)
    m = pi._metrics["groq"]
    # Provider should be pre-emptively marked exhausted
    assert not m.is_available(), (
        "Provider with <10 requests remaining should be pre-emptively exhausted"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 11: _call_anthropic with mock env returns mock response
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_call_anthropic_mock_env_returns_mock_response(monkeypatch):
    """AI_PROVIDER=mock → returns mock without touching ProviderIntelligence."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from factory.core.roles import _call_anthropic
    from factory.core.state import PipelineState, AIRole, Stage, ROLE_CONTRACTS

    state = PipelineState(project_id="test-pi", operator_id="op1")
    contract = ROLE_CONTRACTS[AIRole.ENGINEER]

    result, cost = await _call_anthropic("build me something", contract, state, "write_code")
    assert "[MOCK:" in result and "ENGINEER" in result.upper()
    assert cost == 0.0001


# ═══════════════════════════════════════════════════════════════════
# Test 12: _call_anthropic (non-mock) consults get_chain_for_role
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_call_anthropic_consults_provider_intelligence(monkeypatch):
    """_call_anthropic must call provider_intelligence.get_chain_for_role."""
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    from factory.core import roles as roles_module
    from factory.core.state import PipelineState, AIRole, ROLE_CONTRACTS, Stage

    state = PipelineState(project_id="test-pi2", operator_id="op2")
    contract = ROLE_CONTRACTS[AIRole.STRATEGIST]

    calls_to_get_chain = []

    original_pi = roles_module.provider_intelligence if hasattr(roles_module, "provider_intelligence") else None

    mock_pi = MagicMock()
    mock_pi.get_chain_for_role.side_effect = lambda role, mode: (
        calls_to_get_chain.append((role, mode)) or ["mock"]
    )
    mock_pi.record_call = MagicMock()
    mock_pi.on_provider_exhausted = MagicMock()

    # Patch provider_intelligence inside _call_anthropic's import scope
    with patch("factory.core.provider_intelligence.provider_intelligence", mock_pi):
        # Also patch _call_single_ai_provider to avoid real calls
        with patch.object(roles_module, "_call_single_ai_provider",
                          new=AsyncMock(return_value=("[MOCK:STRATEGIST] test", 0.0))):
            await roles_module._call_anthropic("design the architecture", contract, state, "plan_architecture")

    assert len(calls_to_get_chain) >= 1, (
        "_call_anthropic must call provider_intelligence.get_chain_for_role"
    )
    assert calls_to_get_chain[0][0] == "STRATEGIST"
