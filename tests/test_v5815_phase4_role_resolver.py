"""v5.8.15 Phase 4 (Issue 54) — role resolver / BASIC free-chain enforcement.

Live evidence: `/providers` in BASIC showed `anthropic: ACTIVE` even though
the operator had no paid credit. Root cause: the `/providers` renderer
read the global ai_chain (mode-agnostic) and marked whichever provider
was last used as ACTIVE, regardless of whether BASIC would actually
allow that provider.

These tests verify:
  1. PAID_PROVIDERS codifies every billable provider.
  2. filter_for_mode excludes paid providers in BASIC only.
  3. resolve_provider_for_role applies the BASIC filter defensively even
     if ROLE_PROVIDERS were misconfigured.
  4. status_message(mode) labels paid providers as EXCLUDED in BASIC.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_paid_providers_include_anthropic_and_perplexity():
    from factory.core.provider_intelligence import PAID_PROVIDERS, is_paid

    assert "anthropic" in PAID_PROVIDERS
    assert "perplexity" in PAID_PROVIDERS
    assert is_paid("anthropic") is True
    assert is_paid("gemini") is False
    assert is_paid("groq") is False


def test_filter_for_mode_strips_paid_in_basic():
    from factory.core.provider_intelligence import filter_for_mode

    chain = ["anthropic", "gemini", "groq", "perplexity", "cerebras"]
    assert filter_for_mode(chain, "BASIC") == ["gemini", "groq", "cerebras"]
    # Other modes pass through unchanged
    assert filter_for_mode(chain, "BALANCED") == chain
    assert filter_for_mode(chain, "TURBO") == chain


def test_resolve_provider_for_role_excludes_paid_in_basic_defensively(monkeypatch):
    """Even if ROLE_PROVIDERS were misconfigured to list anthropic under
    BASIC, resolve_provider_for_role must strip it."""
    from factory.core import provider_intelligence as pi_mod
    from factory.core.state import PipelineState

    # Inject a misconfigured chain
    saved = dict(pi_mod.ROLE_PROVIDERS["STRATEGIST"])
    try:
        pi_mod.ROLE_PROVIDERS["STRATEGIST"]["BASIC"] = [
            "anthropic", "gemini", "groq", "perplexity",
        ]
        # Ensure the env "has" keys so the filter can't eliminate via key check
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GEMINI_API_KEY", "g-test")
        monkeypatch.setenv("GROQ_API_KEY", "gr-test")
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pp-test")

        from factory.core.mode_router import MasterMode
        state = PipelineState(project_id="p1", operator_id="op1")
        state.master_mode = MasterMode.BASIC

        chain = pi_mod.provider_intelligence.resolve_provider_for_role(
            "STRATEGIST", state,
        )
        assert "anthropic" not in chain
        assert "perplexity" not in chain
        assert "gemini" in chain or "groq" in chain
    finally:
        pi_mod.ROLE_PROVIDERS["STRATEGIST"] = saved


def test_status_message_basic_shows_anthropic_excluded():
    from factory.core.provider_intelligence import provider_intelligence

    msg = provider_intelligence.status_message("BASIC")
    # Must include the exclusion marker, not ACTIVE or "key present, no calls"
    assert "anthropic" in msg
    assert "excluded" in msg.lower()
    assert "paid" in msg.lower()


def test_status_message_balanced_does_not_exclude_anthropic():
    from factory.core.provider_intelligence import provider_intelligence

    msg = provider_intelligence.status_message("BALANCED")
    # Anthropic line should not carry the exclusion marker in BALANCED
    anthropic_lines = [
        ln for ln in msg.splitlines() if "anthropic" in ln.lower()
    ]
    assert anthropic_lines
    assert not any("excluded" in ln.lower() for ln in anthropic_lines)
