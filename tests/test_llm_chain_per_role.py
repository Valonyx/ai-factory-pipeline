"""
Tests for FIX-LLM-CAT: per-role chain definitions, Gemini key alias,
Cohere reclassification, and latency cap enforcement.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("PIPELINE_ENV", "ci")


# ─── Per-role chains ──────────────────────────────────────────────────────────

def test_strategist_chain_returns_at_least_3_providers():
    from factory.integrations.chain_policy import get_ai_chain_for_role
    for mode in ("BASIC", "BALANCED", "TURBO"):
        chain = get_ai_chain_for_role("strategist", mode)
        assert len(chain) >= 3, f"Strategist chain for {mode} has <3 providers: {chain}"


def test_engineer_chain_prefers_mistral_codestral():
    """Mistral Codestral (accessed via 'mistral') should head the engineer chain."""
    from factory.integrations.chain_policy import get_ai_chain_for_role
    for mode in ("BASIC", "BALANCED"):
        chain = get_ai_chain_for_role("engineer", mode)
        assert "mistral" in chain, f"Engineer {mode} chain must include mistral (Codestral): {chain}"
        assert chain[0] == "mistral", f"Engineer {mode} chain head should be mistral, got {chain[0]}"


def test_quick_fix_chain_uses_groq_first():
    """Quick Fix needs lowest latency — groq should lead."""
    from factory.integrations.chain_policy import get_ai_chain_for_role
    chain = get_ai_chain_for_role("quick_fix", "BASIC")
    assert chain[0] == "groq", f"Quick Fix BASIC head should be groq, got {chain[0]}"


def test_embeddings_chain_includes_cohere():
    """Cohere embed-v4 is best free embeddings — must be in BASIC embeddings chain."""
    from factory.integrations.chain_policy import get_ai_chain_for_role
    chain = get_ai_chain_for_role("embeddings", "BASIC")
    assert "cohere" in chain, f"Embeddings BASIC chain must include cohere: {chain}"


def test_unknown_role_falls_back_to_mode_chain():
    """Unknown role must return the mode-level chain, not an empty list."""
    from factory.integrations.chain_policy import get_ai_chain_for_role
    chain = get_ai_chain_for_role("nonexistent_role", "BASIC")
    assert chain, "Unknown role must fall back to mode-level chain, not return empty"


def test_turbo_strategist_starts_with_anthropic_when_key_present():
    """TURBO Strategist should prefer Anthropic when the key is available."""
    from factory.integrations.chain_policy import _ROLE_AI_CHAINS
    chain = _ROLE_AI_CHAINS["strategist"]["TURBO"]
    assert chain[0] == "anthropic"


# ─── Gemini key alias ─────────────────────────────────────────────────────────

def test_get_gemini_api_key_uses_google_ai_api_key():
    """get_gemini_api_key() must find GOOGLE_AI_API_KEY when GEMINI_API_KEY is absent."""
    backup = os.environ.pop("GEMINI_API_KEY", None)
    os.environ["GOOGLE_AI_API_KEY"] = "test-google-key"
    try:
        from importlib import reload
        import factory.integrations.gemini as gm
        reload(gm)
        key = gm.get_gemini_api_key()
        assert key == "test-google-key"
    finally:
        del os.environ["GOOGLE_AI_API_KEY"]
        if backup:
            os.environ["GEMINI_API_KEY"] = backup


def test_get_gemini_api_key_falls_back_to_gemini_api_key():
    """get_gemini_api_key() must also accept GEMINI_API_KEY."""
    backup_ga = os.environ.pop("GOOGLE_AI_API_KEY", None)
    backup_gp = os.environ.pop("GOOGLE_API_KEY", None)
    os.environ["GEMINI_API_KEY"] = "test-gemini-key"
    try:
        from importlib import reload
        import factory.integrations.gemini as gm
        reload(gm)
        key = gm.get_gemini_api_key()
        assert key == "test-gemini-key"
    finally:
        del os.environ["GEMINI_API_KEY"]
        if backup_ga:
            os.environ["GOOGLE_AI_API_KEY"] = backup_ga
        if backup_gp:
            os.environ["GOOGLE_API_KEY"] = backup_gp


def test_provider_intelligence_has_key_gemini_with_google_ai_key():
    """has_key('gemini') must return True when GOOGLE_AI_API_KEY is set."""
    os.environ["GOOGLE_AI_API_KEY"] = "test-key"
    try:
        from importlib import reload
        import factory.integrations.gemini as gm
        import factory.core.provider_intelligence as pi
        reload(gm)
        reload(pi)
        assert pi.has_key("gemini") is True
    finally:
        pass  # key already set in env from .env file


# ─── Cohere reclassification ─────────────────────────────────────────────────

def test_cohere_not_in_paid_providers():
    """Cohere must NOT be in PAID_PROVIDERS — it has a free trial tier."""
    from factory.core.provider_intelligence import PAID_PROVIDERS
    assert "cohere" not in PAID_PROVIDERS, (
        "Cohere has a real free trial tier (1,000 req/month) and must not be "
        "classified as paid-only"
    )


def test_cohere_not_excluded_from_basic_embeddings():
    """BASIC embeddings chain must include cohere."""
    from factory.integrations.chain_policy import _ROLE_AI_CHAINS
    basic_embeddings = _ROLE_AI_CHAINS["embeddings"]["BASIC"]
    assert "cohere" in basic_embeddings


# ─── Latency cap per role ─────────────────────────────────────────────────────

def test_quick_fix_has_stricter_latency_than_strategist():
    """Quick Fix latency cap must be tighter than Strategist."""
    from factory.integrations.chain_policy import ROLE_LATENCY_CAP_MS
    assert ROLE_LATENCY_CAP_MS["quick_fix"] < ROLE_LATENCY_CAP_MS["strategist"]


def test_role_latency_cap_returns_reasonable_values():
    from factory.integrations.chain_policy import role_latency_cap_ms
    # Quick Fix should have a cap — not unbounded
    cap = role_latency_cap_ms("quick_fix", "TURBO")
    assert cap > 0
    assert cap <= 15_000, f"Quick Fix latency cap should be ≤15s, got {cap}ms"


def test_provider_chain_ping_knows_github_token():
    """provider_intelligence must map github_models → GITHUB_TOKEN env var."""
    from factory.core.provider_intelligence import _KEY_ENV_VARS
    assert "github_models" in _KEY_ENV_VARS, "provider_intelligence must list github_models"
    assert _KEY_ENV_VARS["github_models"] == "GITHUB_TOKEN"
