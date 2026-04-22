"""
Unit tests for v5.8.16 UI Agent Chain (factory/integrations/ui_agent_chain.py)

Tests cover:
- Mock mode short-circuits all providers
- Provider dispatch (qwen_vl, gemini_vision, nvidia_nim_vision)
- Cascade: first success stops chain
- All-fail → typed degraded result with action="fail"
- Missing key → cascades to next provider (no raises from chain)
- ui_tars skipped when not configured (is_available=False)
- parse_screen_elements returns list

HTTP patched at httpx boundary per conftest.py §56.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _nim_resp(text: str) -> MagicMock:
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


def _cf_resp(text: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"result": {"response": text}}
    resp.raise_for_status = MagicMock()
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Mock mode
# ─────────────────────────────────────────────────────────────────────────────

class TestUIAgentChainMockMode:
    def test_plan_ui_action_mock_mode(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.ui_agent_chain as uac
        importlib.reload(uac)

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            uac.plan_ui_action(FAKE_PNG, "click the login button")
        )
        assert result["source"] == "mock"
        assert result["degraded"] is False
        assert result["action"] == "done"

    def test_parse_screen_elements_mock_mode(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "mock")
        import importlib
        import factory.integrations.ui_agent_chain as uac
        importlib.reload(uac)

        import asyncio
        elements = asyncio.get_event_loop().run_until_complete(
            uac.parse_screen_elements(FAKE_PNG)
        )
        assert isinstance(elements, list)
        assert len(elements) > 0
        assert "label" in elements[0]


# ─────────────────────────────────────────────────────────────────────────────
# Provider dispatch
# ─────────────────────────────────────────────────────────────────────────────

class TestUIAgentChainProviderDispatch:
    @pytest.mark.asyncio
    async def test_qwen_vl_success(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "qwen_vl")

        action_json = json.dumps({
            "action": "click",
            "target": "Login button",
            "coordinates": [0.5, 0.8],
            "value": None,
            "reasoning": "Login button is visible"
        })
        resp = _nim_resp(action_json)  # OpenRouter uses same format

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "click login")

        assert result["source"] == "qwen_vl"
        assert result["action"] == "click"
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_gemini_vision_success(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "gemini_vision")

        action_json = json.dumps({
            "action": "type",
            "target": "Search field",
            "value": "hello world",
            "reasoning": "Search input is focused"
        })
        resp = _gemini_resp(action_json)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "type in search")

        assert result["source"] == "gemini_vision"
        assert result["action"] == "type"
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_nvidia_nim_vision_success(self, monkeypatch):
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("NVIDIA_NIM_VISION_API_KEY", "nim-key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "nvidia_nim_vision")

        action_json = json.dumps({
            "action": "scroll",
            "target": "page",
            "value": "down",
            "reasoning": "Need to scroll to see more content"
        })
        resp = _nim_resp(action_json)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "scroll down")

        assert result["source"] == "nvidia_nim_vision"
        assert result["action"] == "scroll"
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_ui_tars_skipped_when_not_configured(self, monkeypatch):
        """ui_tars provider raises ValueError when not configured → cascades."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("UI_TARS_ENDPOINT", raising=False)
        monkeypatch.setenv("NVIDIA_NIM_VISION_API_KEY", "nim-key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "ui_tars,nvidia_nim_vision")

        action_json = json.dumps({
            "action": "done",
            "target": None,
            "value": None,
            "reasoning": "Task complete"
        })
        resp = _nim_resp(action_json)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "finish")

        # Should have fallen back to nvidia_nim_vision
        assert result["source"] == "nvidia_nim_vision"
        assert result["degraded"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Cascade & degradation
# ─────────────────────────────────────────────────────────────────────────────

class TestUIAgentChainCascade:
    @pytest.mark.asyncio
    async def test_all_fail_returns_typed_degraded(self, monkeypatch):
        """All providers down → action='fail', degraded=True, never raises."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "qwen_vl")

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock,
                          side_effect=Exception("network error")):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "do something")

        assert result["action"] == "fail"
        assert result["degraded"] is True
        assert result["source"] == "degraded"

    @pytest.mark.asyncio
    async def test_cascade_on_provider_exception(self, monkeypatch):
        """Provider raises HTTP exception → cascades to next provider."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "qwen_vl,gemini_vision")

        action_json = json.dumps({
            "action": "click",
            "target": "Submit",
            "value": None,
            "reasoning": "Gemini saved the day"
        })

        async def mock_post(self_inner, url, **kwargs):
            if "openrouter" in url:
                raise Exception("OpenRouter 503 Service Unavailable")
            return _gemini_resp(action_json)

        import httpx
        with patch.object(httpx.AsyncClient, "post", mock_post):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "click submit")

        # qwen_vl raises → cascades to gemini_vision
        assert result["source"] == "gemini_vision"
        assert result["action"] == "click"

    @pytest.mark.asyncio
    async def test_parse_fail_returns_typed_fail_not_exception(self, monkeypatch):
        """When provider can't parse JSON it returns action='fail', not an exception.
        The chain treats this as a completed (though failed) action — no cascade."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "qwen_vl")

        # Return garbled non-JSON from the model
        garbled_resp = MagicMock()
        garbled_resp.status_code = 200
        garbled_resp.json.return_value = {"choices": [{"message": {"content": "not json at all"}}]}
        garbled_resp.raise_for_status = MagicMock()

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=garbled_resp):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "click submit")

        # qwen_vl internally returns action="fail" on parse error (not raises)
        assert result["source"] == "qwen_vl"
        assert result["action"] == "fail"
        assert result["degraded"] is False  # chain succeeded, model action failed

    @pytest.mark.asyncio
    async def test_missing_key_cascades(self, monkeypatch):
        """qwen_vl missing key → ValueError → cascades to gemini_vision."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "qwen_vl,gemini_vision")

        action_json = json.dumps({
            "action": "done",
            "target": None,
            "value": None,
            "reasoning": "Finished"
        })
        resp = _gemini_resp(action_json)

        import httpx
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=resp):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "done")

        assert result["source"] == "gemini_vision"
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_history_passed_to_provider(self, monkeypatch):
        """History list is forwarded to the provider call."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "key")
        monkeypatch.setenv("UI_AGENT_PROVIDER_CHAIN", "qwen_vl")

        history = [
            {"action": "click", "target": "Home"},
            {"action": "type", "target": "Search", "value": "query"},
        ]

        action_json = json.dumps({
            "action": "click",
            "target": "Result 1",
            "value": None,
            "reasoning": "First result matches"
        })

        captured_payload: dict = {}
        async def mock_post(self_inner, url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"choices": [{"message": {"content": action_json}}]}
            resp.raise_for_status = MagicMock()
            return resp

        import httpx
        with patch.object(httpx.AsyncClient, "post", mock_post):
            import importlib
            import factory.integrations.ui_agent_chain as uac
            importlib.reload(uac)
            result = await uac.plan_ui_action(FAKE_PNG, "click result", history=history)

        assert result["action"] == "click"
        # History should be embedded in the prompt text
        messages = captured_payload.get("messages", [])
        assert len(messages) > 0
        prompt_text = str(messages)
        assert "Home" in prompt_text or "Search" in prompt_text
