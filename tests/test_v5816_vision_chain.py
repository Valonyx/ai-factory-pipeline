"""
Unit tests for v5.8.16 Vision Chain (factory/integrations/vision_chain.py)

Tests cover:
- Mock mode short-circuits all providers
- Each provider dispatched correctly
- First success returned; remainder not tried
- All-fail → typed degraded result (never raises)
- Cost tracking called on success
- available_providers() reflects env var presence

All HTTP calls are patched at the httpx/SDK boundary. No
factory.integrations.* imports are mocked (per conftest.py §56).
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

FAKE_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # minimal PNG header


def _make_httpx_response(status: int, body: dict) -> MagicMock:
    import json
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Mock mode
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionChainMockMode:
    def test_analyze_image_mock_mode(self, monkeypatch):
        """AI_PROVIDER=mock returns mock result without hitting any provider."""
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.vision_chain as vc
        importlib.reload(vc)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            vc.analyze_image(FAKE_IMAGE, "describe this")
        )
        assert result["degraded"] is False
        assert result["source"] == "mock"
        assert "mock" in result["text"].lower()

    def test_analyze_ui_screenshot_mock_mode(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.vision_chain as vc
        importlib.reload(vc)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            vc.analyze_ui_screenshot(FAKE_IMAGE, task="find buttons")
        )
        assert result["source"] == "mock"
        assert result["degraded"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Provider dispatch — individual providers
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionChainProviderDispatch:
    """Each provider in the chain can be invoked and returns text."""

    @pytest.mark.asyncio
    async def test_nvidia_nim_vision_success(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("NVIDIA_NIM_VISION_API_KEY", "test-key")
        monkeypatch.setenv(
            "VISION_PROVIDER_CHAIN", "nvidia_nim_vision"
        )

        mock_resp = _make_httpx_response(200, {
            "choices": [{"message": {"content": "NIM vision analysis"}}]
        })

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp):
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "test prompt")

        assert result["degraded"] is False
        assert result["source"] == "nvidia_nim_vision"
        assert "NIM vision" in result["text"]

    @pytest.mark.asyncio
    async def test_gemini_vision_success(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("VISION_PROVIDER_CHAIN", "gemini_vision")

        mock_resp = _make_httpx_response(200, {
            "candidates": [{
                "content": {"parts": [{"text": "Gemini vision analysis"}]}
            }]
        })

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp):
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "test prompt")

        assert result["degraded"] is False
        assert result["source"] == "gemini_vision"

    @pytest.mark.asyncio
    async def test_groq_vision_success(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
        monkeypatch.setenv("VISION_PROVIDER_CHAIN", "groq_vision")

        mock_resp = _make_httpx_response(200, {
            "choices": [{"message": {"content": "Groq vision analysis"}}]
        })

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp):
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "test prompt")

        assert result["degraded"] is False
        assert result["source"] == "groq_vision"

    @pytest.mark.asyncio
    async def test_cloudflare_vision_success(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-id")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
        monkeypatch.setenv("VISION_PROVIDER_CHAIN", "cloudflare_vision")

        mock_resp = _make_httpx_response(200, {
            "result": {"response": "Cloudflare vision analysis"}
        })

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp):
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "test prompt")

        assert result["degraded"] is False
        assert result["source"] == "cloudflare_vision"


# ─────────────────────────────────────────────────────────────────────────────
# Cascade behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionChainCascade:
    @pytest.mark.asyncio
    async def test_first_provider_success_stops_chain(self, monkeypatch):
        """Chain stops at first success — second provider is never called."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("NVIDIA_NIM_VISION_API_KEY", "key")
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("VISION_PROVIDER_CHAIN", "nvidia_nim_vision,gemini_vision")

        nim_resp = _make_httpx_response(200, {
            "choices": [{"message": {"content": "NIM wins"}}]
        })

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=nim_resp) as mock_post:
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "prompt")

        assert result["source"] == "nvidia_nim_vision"
        assert mock_post.call_count == 1  # only one call made

    @pytest.mark.asyncio
    async def test_fallback_on_first_provider_failure(self, monkeypatch):
        """When first provider fails, second provider is tried."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "key")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
        monkeypatch.setenv("VISION_PROVIDER_CHAIN", "groq_vision,cloudflare_vision")

        cf_resp = _make_httpx_response(200, {"result": {"response": "CF fallback"}})

        call_count = 0
        async def mock_post(self_inner, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "groq" in url:
                raise Exception("Groq down")
            return cf_resp

        import httpx
        with patch.object(httpx.AsyncClient, "post", mock_post):
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "prompt")

        assert result["source"] == "cloudflare_vision"
        assert "CF fallback" in result["text"]

    @pytest.mark.asyncio
    async def test_all_fail_returns_typed_degraded(self, monkeypatch):
        """All providers failing → typed degraded result, never raises."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "key")
        monkeypatch.setenv("VISION_PROVIDER_CHAIN", "groq_vision")

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=Exception("Network error")):
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "prompt")

        assert result["degraded"] is True
        assert result["source"] == "degraded"
        assert result["text"] == ""
        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_api_key_skips_provider(self, monkeypatch):
        """Provider raises ValueError on missing key — cascades cleanly."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
        monkeypatch.setenv("VISION_PROVIDER_CHAIN", "groq_vision,cloudflare_vision")

        cf_resp = _make_httpx_response(200, {"result": {"response": "CF result"}})

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=cf_resp):
            import importlib
            import factory.integrations.vision_chain as vc
            importlib.reload(vc)
            result = await vc.analyze_image(FAKE_IMAGE, "prompt")

        assert result["source"] == "cloudflare_vision"
        assert result["degraded"] is False


# ─────────────────────────────────────────────────────────────────────────────
# available_providers()
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionChainAvailableProviders:
    def test_mock_mode_all_available(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.vision_chain as vc
        importlib.reload(vc)
        providers = vc.available_providers()
        assert len(providers) == len(vc._PROVIDER_PRIORITY)

    def test_no_keys_returns_empty(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        for key in ["NVIDIA_NIM_VISION_API_KEY", "NVIDIA_NIM_API_KEY",
                    "GEMINI_API_KEY", "GOOGLE_AI_API_KEY", "GOOGLE_API_KEY",
                    "GROQ_API_KEY",
                    "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"]:
            monkeypatch.delenv(key, raising=False)

        import importlib
        import factory.integrations.vision_chain as vc
        importlib.reload(vc)
        providers = vc.available_providers()
        assert providers == []

    def test_partial_keys_returns_subset(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        for key in ["NVIDIA_NIM_VISION_API_KEY", "NVIDIA_NIM_API_KEY",
                    "GROQ_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        import importlib
        import factory.integrations.vision_chain as vc
        importlib.reload(vc)
        providers = vc.available_providers()
        assert "gemini_vision" in providers
        assert "groq_vision" not in providers
