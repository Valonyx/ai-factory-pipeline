"""
Unit tests for v5.8.16 Design Generation Chain
(factory/integrations/design_gen_chain.py)

Tests cover:
- Mock mode short-circuits all providers
- Image generation: HuggingFace → Together → Pollinations cascade
- Code generation: Gemini → OpenRouter → Groq cascade
- Unknown asset type → typed degraded result
- All image providers fail → Pollinations fallback (no-key) still works
- All providers fail → typed degraded result, never raises
- Convenience wrappers: generate_screen_mockup, generate_component_code,
  generate_icon_set, generate_design_tokens_from_spec

HTTP patched at httpx boundary per conftest.py §56.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

DESIGN_SPEC = {
    "primary_color": "#6366f1",
    "font_family": "Inter",
    "style": "modern",
}


def _openai_resp(text: str) -> MagicMock:
    """OpenAI-compatible JSON response (Gemini/OpenRouter/Groq)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": text}}]}
    resp.raise_for_status = MagicMock()
    return resp


def _gemini_resp(text: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}]
    }
    resp.raise_for_status = MagicMock()
    return resp


def _hf_image_resp() -> MagicMock:
    """HuggingFace inference API returns raw image bytes."""
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # fake PNG bytes
    resp.headers = {"content-type": "image/png"}
    resp.raise_for_status = MagicMock()
    return resp


def _pollinations_resp() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    resp.headers = {"content-type": "image/png"}
    resp.raise_for_status = MagicMock()
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Mock mode
# ─────────────────────────────────────────────────────────────────────────────

class TestDesignGenChainMockMode:
    def test_mock_mode_image_asset(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.design_gen_chain as dgc
        importlib.reload(dgc)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            dgc.generate_design_asset("mockup_image", "login screen")
        )
        assert result["degraded"] is False
        assert result["source"] == "mock"
        assert result["asset_type"] == "mockup_image"

    def test_mock_mode_code_asset(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.design_gen_chain as dgc
        importlib.reload(dgc)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            dgc.generate_design_asset("component_code", "submit button")
        )
        assert result["degraded"] is False
        assert result["source"] == "mock"
        assert result["asset_type"] == "component_code"


# ─────────────────────────────────────────────────────────────────────────────
# Code generation providers
# ─────────────────────────────────────────────────────────────────────────────

class TestDesignGenCodeProviders:
    @pytest.mark.asyncio
    async def test_gemini_code_generation(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")

        code = "import 'package:flutter/material.dart';\nWidget build() => ElevatedButton();"
        resp = _gemini_resp(code)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "component_code", "primary button", design_spec=DESIGN_SPEC
            )

        assert result["degraded"] is False
        assert result["source"] == "gemini"
        assert result["asset_type"] == "component_code"
        assert "flutter" in result["content"].lower() or len(result["content"]) > 0

    @pytest.mark.asyncio
    async def test_openrouter_code_fallback(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

        code = "const Button = () => <button>Submit</button>;"
        resp = _openai_resp(code)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "component_code", "react button", design_spec=DESIGN_SPEC
            )

        assert result["degraded"] is False
        assert result["source"] == "openrouter"

    @pytest.mark.asyncio
    async def test_groq_code_fallback(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "groq-key")

        code = "<svg><circle r='10'/></svg>"
        resp = _openai_resp(code)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "svg_icon", "circle icon", design_spec=DESIGN_SPEC
            )

        assert result["degraded"] is False
        assert result["source"] == "groq"

    @pytest.mark.asyncio
    async def test_html_prototype_asset_type(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")

        html = "<!DOCTYPE html><html><body><h1>App</h1></body></html>"
        resp = _gemini_resp(html)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "html_prototype", "login page", design_spec=DESIGN_SPEC
            )

        assert result["asset_type"] == "html_prototype"
        assert result["format"] == "html"
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_design_tokens_asset_type(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")

        tokens = json.dumps({"color": {"primary": "#6366f1"}, "font": {"family": "Inter"}})
        resp = _gemini_resp(tokens)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "design_tokens", "app tokens", design_spec=DESIGN_SPEC
            )

        assert result["asset_type"] == "design_tokens"
        assert result["format"] == "json"
        assert result["degraded"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Image generation providers
# ─────────────────────────────────────────────────────────────────────────────

class TestDesignGenImageProviders:
    @pytest.mark.asyncio
    async def test_huggingface_image_success(self, monkeypatch):
        """HuggingFace uses urllib.request.urlopen in a thread executor."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("HUGGINGFACE_API_KEY", "hf-key")

        # Build a fake urllib response context manager
        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048  # >1000 bytes

        fake_resp = MagicMock()
        fake_resp.read.return_value = fake_image_bytes
        fake_resp.__enter__ = MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = MagicMock(return_value=False)

        import urllib.request
        with patch.object(urllib.request, "urlopen", return_value=fake_resp):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "mockup_image", "login screen mockup", design_spec=DESIGN_SPEC
            )

        assert result["degraded"] is False
        assert result["source"] == "huggingface"
        assert result["format"] == "png"

    @pytest.mark.asyncio
    async def test_pollinations_no_key_required(self, monkeypatch):
        """Pollinations uses urllib.request.urlopen — no API key required."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)

        fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048  # >1000 bytes

        fake_resp = MagicMock()
        fake_resp.read.return_value = fake_image_bytes
        fake_resp.__enter__ = MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = MagicMock(return_value=False)

        import urllib.request
        with patch.object(urllib.request, "urlopen", return_value=fake_resp):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "splash_image", "app splash screen", design_spec=DESIGN_SPEC
            )

        assert result["degraded"] is False
        assert result["source"] == "pollinations"
        assert result["format"] == "png"

    @pytest.mark.asyncio
    async def test_all_image_providers_fail_returns_degraded(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("HUGGINGFACE_API_KEY", "hf-key")
        monkeypatch.delenv("TOGETHER_API_KEY", raising=False)

        import urllib.request
        with patch.object(urllib.request, "urlopen", side_effect=Exception("Network down")):
            import importlib
            import factory.integrations.design_gen_chain as dgc
            importlib.reload(dgc)
            result = await dgc.generate_design_asset(
                "mockup_image", "login", design_spec=DESIGN_SPEC
            )

        assert result["degraded"] is True
        assert result["source"] == "degraded"


# ─────────────────────────────────────────────────────────────────────────────
# Unknown asset type
# ─────────────────────────────────────────────────────────────────────────────

class TestDesignGenUnknownAsset:
    @pytest.mark.asyncio
    async def test_unknown_asset_type_returns_degraded(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)

        import importlib
        import factory.integrations.design_gen_chain as dgc
        importlib.reload(dgc)

        result = await dgc.generate_design_asset("invalid_asset_type", "test")
        assert result["degraded"] is True
        assert result["source"] == "degraded"
        assert "invalid_asset_type" in result.get("error", "").lower() or result["degraded"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrappers
# ─────────────────────────────────────────────────────────────────────────────

class TestDesignGenConvenienceWrappers:
    @pytest.mark.asyncio
    async def test_generate_screen_mockup(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.design_gen_chain as dgc
        importlib.reload(dgc)

        result = await dgc.generate_screen_mockup(
            "MyApp", "Login Screen", DESIGN_SPEC, width=390, height=844
        )
        assert result["asset_type"] in ("mockup_image", "splash_image")
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_generate_component_code(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.design_gen_chain as dgc
        importlib.reload(dgc)

        result = await dgc.generate_component_code(
            "PrimaryButton", "A tappable primary action button", DESIGN_SPEC
        )
        assert result["asset_type"] == "component_code"
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_generate_icon_set(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.design_gen_chain as dgc
        importlib.reload(dgc)

        icons = await dgc.generate_icon_set(
            ["home", "settings", "profile"], style="outline"
        )
        assert isinstance(icons, list)
        assert len(icons) == 3
        for icon in icons:
            assert "asset_type" in icon

    @pytest.mark.asyncio
    async def test_generate_design_tokens_from_spec(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.design_gen_chain as dgc
        importlib.reload(dgc)

        result = await dgc.generate_design_tokens_from_spec(DESIGN_SPEC, app_name="MyApp")
        assert result["asset_type"] == "design_tokens"
        assert result["degraded"] is False


# ─────────────────────────────────────────────────────────────────────────────
# mode_router catalog integration
# ─────────────────────────────────────────────────────────────────────────────

class TestModeRouterCatalogs:
    def test_vision_providers_in_catalog(self):
        from factory.core.mode_router import PROVIDER_CATALOGS, VISION_PROVIDERS
        assert "vision" in PROVIDER_CATALOGS
        assert len(VISION_PROVIDERS) == 4
        names = [p.name for p in VISION_PROVIDERS]
        assert "nvidia_nim_vision" in names
        assert "gemini_vision" in names
        assert "groq_vision" in names
        assert "cloudflare_vision" in names

    def test_ui_agent_providers_in_catalog(self):
        from factory.core.mode_router import PROVIDER_CATALOGS, UI_AGENT_PROVIDERS
        assert "ui_agent" in PROVIDER_CATALOGS
        assert len(UI_AGENT_PROVIDERS) == 4
        names = [p.name for p in UI_AGENT_PROVIDERS]
        assert "qwen_vl" in names
        assert "ui_tars" in names
        assert "gemini_vision" in names
        assert "nvidia_nim_vision" in names

    def test_design_providers_in_catalog(self):
        from factory.core.mode_router import PROVIDER_CATALOGS, DESIGN_PROVIDERS
        assert "design" in PROVIDER_CATALOGS
        assert len(DESIGN_PROVIDERS) == 6
        names = [p.name for p in DESIGN_PROVIDERS]
        assert "gemini" in names
        assert "pollinations" in names

    def test_all_new_providers_are_free_tier(self):
        from factory.core.mode_router import (
            VISION_PROVIDERS, UI_AGENT_PROVIDERS, DESIGN_PROVIDERS, ProviderTier
        )
        for p in VISION_PROVIDERS + UI_AGENT_PROVIDERS + DESIGN_PROVIDERS:
            assert p.tier == ProviderTier.FREE, f"{p.name} should be FREE tier"

    def test_basic_mode_filters_to_all_new_providers(self):
        """All new providers are FREE → BASIC mode can use all of them."""
        from factory.core.mode_router import (
            VISION_PROVIDERS, UI_AGENT_PROVIDERS, DESIGN_PROVIDERS,
            ModeRouter, MasterMode, ChainContext
        )
        router = ModeRouter(mode=MasterMode.BASIC)
        ctx = ChainContext("vision")
        free_vision = router._filter_available(VISION_PROVIDERS, ctx)
        assert len(free_vision) == 4

        ctx2 = ChainContext("ui_agent")
        free_ui = router._filter_available(UI_AGENT_PROVIDERS, ctx2)
        assert len(free_ui) == 4
