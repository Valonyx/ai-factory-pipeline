"""
Tests for new provider adapters introduced in Issue 20:
  - factory/integrations/cloudflare_provider.py
  - factory/integrations/github_models_provider.py
  - factory/integrations/jina_provider.py

Also tests that _call_single_ai_provider dispatches to them, and that
AI_PROVIDERS list includes the new entries.

Issue 20: Full Free Provider Integration + Smart Chain
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.state import AIRole, RoleContract


# ── Shared test contract fixture ─────────────────────────────────

def _make_contract(role: AIRole = AIRole.ENGINEER) -> RoleContract:
    return RoleContract(
        role=role,
        model="claude-opus-4-6",
        can_read_web=False,
        can_write_code=True,
        can_write_files=True,
        can_plan_architecture=True,
        can_decide_legal=False,
        can_manage_war_room=False,
        max_output_tokens=2048,
    )


# ── 1. cloudflare mock mode returns mock tuple ───────────────────

@pytest.mark.asyncio
async def test_cloudflare_mock_mode(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from factory.integrations.cloudflare_provider import call_cloudflare
    result = await call_cloudflare("hello world", _make_contract())
    text, cost = result
    assert isinstance(text, str) and len(text) > 0
    assert cost >= 0.0


# ── 2. cloudflare raises ValueError when creds missing ───────────

@pytest.mark.asyncio
async def test_cloudflare_missing_creds_raises(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    from factory.integrations.cloudflare_provider import call_cloudflare
    with pytest.raises(ValueError, match="CLOUDFLARE credentials not set"):
        await call_cloudflare("hello", _make_contract())


# ── 3. github_models mock mode returns mock tuple ────────────────

@pytest.mark.asyncio
async def test_github_models_mock_mode(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from factory.integrations.github_models_provider import call_github_models
    result = await call_github_models("hello world", _make_contract())
    text, cost = result
    assert isinstance(text, str) and len(text) > 0
    assert cost >= 0.0


# ── 4. github_models raises ValueError when GITHUB_TOKEN missing ─

@pytest.mark.asyncio
async def test_github_models_missing_token_raises(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    from factory.integrations.github_models_provider import call_github_models
    with pytest.raises(ValueError, match="GITHUB_TOKEN not set"):
        await call_github_models("hello", _make_contract())


# ── 5. jina_reader returns non-empty string or raises ValueError ─

@pytest.mark.asyncio
async def test_jina_reader_no_key_returns_string(monkeypatch):
    """
    call_jina_reader either returns a non-empty string (if network available)
    or raises ValueError/Exception. It must NEVER silently return "".
    """
    import httpx

    # Mock httpx to return clean text — avoids real network call in CI
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Example Domain — This domain is for use in examples."
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        from factory.integrations.jina_provider import call_jina_reader
        result = await call_jina_reader("https://example.com")

    assert isinstance(result, str) and len(result) > 0, (
        "call_jina_reader must return a non-empty string on success"
    )


# ── 6. _call_single_ai_provider dispatches to cloudflare ─────────

@pytest.mark.asyncio
async def test_single_ai_provider_dispatcher_cloudflare():
    from factory.core.roles import _call_single_ai_provider
    contract = _make_contract()

    mock_result = ("cloudflare response", 0.0)
    with patch(
        "factory.integrations.cloudflare_provider.call_cloudflare",
        new=AsyncMock(return_value=mock_result),
    ) as patched:
        result = await _call_single_ai_provider("cloudflare", "test prompt", contract)

    assert result == mock_result
    patched.assert_awaited_once()


# ── 7. _call_single_ai_provider dispatches to github_models ──────

@pytest.mark.asyncio
async def test_single_ai_provider_dispatcher_github_models():
    from factory.core.roles import _call_single_ai_provider
    contract = _make_contract()

    mock_result = ("github models response", 0.0)
    with patch(
        "factory.integrations.github_models_provider.call_github_models",
        new=AsyncMock(return_value=mock_result),
    ) as patched:
        result = await _call_single_ai_provider("github_models", "test prompt", contract)

    assert result == mock_result
    patched.assert_awaited_once()


# ── 8. AI_PROVIDERS includes cloudflare ──────────────────────────

def test_ai_providers_list_includes_new():
    from factory.core.mode_router import AI_PROVIDERS
    names = [p.name for p in AI_PROVIDERS]
    assert "cloudflare" in names, f"cloudflare not in AI_PROVIDERS: {names}"
    assert "github_models" in names, f"github_models not in AI_PROVIDERS: {names}"
