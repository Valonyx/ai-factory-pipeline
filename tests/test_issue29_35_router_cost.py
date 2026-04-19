"""
Issues 29 + 35 — AI Conversational Router + BASIC $0 Cost Honesty

Tests:
  Issue 35 — Cost estimate:
    1. classify_intent accepts master_mode parameter
    2. ai_respond accepts master_mode parameter
    3. _call_ai_for_bot accepts master_mode parameter
    4. _FREE_BOT_PROVIDERS contains expected free providers
    5. BASIC mode filters out anthropic from bot AI calls
    6. BASIC mode falls back to full chain when no free provider is available
    7. _handle_start_project_intent: cost string varies by mode

  Issue 35 — Cost estimate:
    8. BASIC mode → $0.00 estimate
    9. BALANCED mode → $0.05–$2.00 estimate
   10. TURBO mode → $2.00+ estimate
   11. CUSTOM mode → Variable estimate
"""

from __future__ import annotations

import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════════
# Tests 1-4: function signatures
# ═══════════════════════════════════════════════════════════════════

def test_classify_intent_accepts_master_mode():
    """classify_intent has a master_mode parameter."""
    from factory.telegram.ai_handler import classify_intent
    sig = inspect.signature(classify_intent)
    assert "master_mode" in sig.parameters


def test_ai_respond_accepts_master_mode():
    """ai_respond has a master_mode parameter."""
    from factory.telegram.ai_handler import ai_respond
    sig = inspect.signature(ai_respond)
    assert "master_mode" in sig.parameters


def test_call_ai_for_bot_accepts_master_mode():
    """_call_ai_for_bot has a master_mode parameter."""
    from factory.telegram.ai_handler import _call_ai_for_bot
    sig = inspect.signature(_call_ai_for_bot)
    assert "master_mode" in sig.parameters


def test_free_bot_providers_contains_expected():
    """_FREE_BOT_PROVIDERS includes gemini, groq, and mock."""
    from factory.telegram.ai_handler import _FREE_BOT_PROVIDERS
    assert "gemini" in _FREE_BOT_PROVIDERS
    assert "groq" in _FREE_BOT_PROVIDERS
    assert "mock" in _FREE_BOT_PROVIDERS
    assert "anthropic" not in _FREE_BOT_PROVIDERS


# ═══════════════════════════════════════════════════════════════════
# Test 5: BASIC mode skips anthropic
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_basic_mode_skips_anthropic():
    """In BASIC mode, _call_ai_for_bot never calls anthropic."""
    from factory.telegram.ai_handler import _call_ai_for_bot

    called_providers = []

    async def _mock_call_bot_provider(provider, prompt, max_tokens, temperature):
        called_providers.append(provider)
        if provider == "anthropic":
            raise AssertionError("anthropic should NOT be called in BASIC mode")
        return f"response from {provider}"

    with patch("factory.telegram.ai_handler._call_bot_provider", _mock_call_bot_provider), \
         patch("factory.integrations.provider_chain.ai_chain") as mock_chain:
        mock_chain.chain = ["anthropic", "gemini", "groq", "mock"]
        mock_status_available = MagicMock()
        mock_status_available.available = True
        mock_chain.statuses = {
            "anthropic": mock_status_available,
            "gemini": mock_status_available,
            "groq": mock_status_available,
            "mock": mock_status_available,
        }
        mock_chain.mark_success = MagicMock()

        result = await _call_ai_for_bot("test prompt", master_mode="BASIC")

    assert result in ("response from gemini", "response from groq", "response from mock")
    assert "anthropic" not in called_providers


# ═══════════════════════════════════════════════════════════════════
# Test 6: BASIC mode falls back when no free provider available
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_basic_mode_fallback_when_no_free_provider():
    """BASIC mode falls back to paid if no free provider is available."""
    from factory.telegram.ai_handler import _call_ai_for_bot

    called_providers = []

    async def _mock_call_bot_provider(provider, prompt, max_tokens, temperature):
        called_providers.append(provider)
        return f"response from {provider}"

    with patch("factory.telegram.ai_handler._call_bot_provider", _mock_call_bot_provider), \
         patch("factory.integrations.provider_chain.ai_chain") as mock_chain:
        mock_status_available = MagicMock()
        mock_status_available.available = True
        mock_status_unavailable = MagicMock()
        mock_status_unavailable.available = False
        mock_chain.chain = ["anthropic", "openrouter"]  # no free providers
        mock_chain.statuses = {
            "anthropic": mock_status_available,
            "openrouter": mock_status_available,
        }
        mock_chain.mark_success = MagicMock()

        result = await _call_ai_for_bot("test prompt", master_mode="BASIC")

    # Should fall back and use anthropic since no free provider available
    assert len(called_providers) > 0
    assert result.startswith("response from")


# ═══════════════════════════════════════════════════════════════════
# Test 7: BALANCED mode allows anthropic
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_balanced_mode_allows_anthropic():
    """In BALANCED mode, anthropic can be called normally."""
    from factory.telegram.ai_handler import _call_ai_for_bot

    called_providers = []

    async def _mock_call_bot_provider(provider, prompt, max_tokens, temperature):
        called_providers.append(provider)
        return f"response from {provider}"

    with patch("factory.telegram.ai_handler._call_bot_provider", _mock_call_bot_provider), \
         patch("factory.integrations.provider_chain.ai_chain") as mock_chain:
        mock_status = MagicMock()
        mock_status.available = True
        mock_chain.chain = ["anthropic", "gemini"]
        mock_chain.statuses = {"anthropic": mock_status, "gemini": mock_status}
        mock_chain.mark_success = MagicMock()

        result = await _call_ai_for_bot("test prompt", master_mode="BALANCED")

    assert "anthropic" in called_providers
    assert result == "response from anthropic"


# ═══════════════════════════════════════════════════════════════════
# Tests 8-11: cost estimate per mode (Issue 35)
# ═══════════════════════════════════════════════════════════════════

_COST_MODE_CASES = [
    ("BASIC",    "$0.00"),
    ("BALANCED", "$0.05"),
    ("TURBO",    "$2.00"),
    ("CUSTOM",   "Variable"),
]


@pytest.mark.parametrize("mode,expected_fragment", _COST_MODE_CASES)
@pytest.mark.asyncio
async def test_cost_estimate_by_mode(mode, expected_fragment):
    """_handle_start_project_intent shows correct cost estimate per master mode."""
    from factory.telegram.bot import _handle_start_project_intent

    captured_text = []

    fake_update = MagicMock()
    fake_update.message = MagicMock()
    async def _capture_reply(text, **kwargs):
        captured_text.append(text)
    fake_update.message.reply_text = _capture_reply

    with patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": mode.lower()})), \
         patch("factory.telegram.ai_handler.request_confirmation"), \
         patch("factory.telegram.ai_handler._add_to_history"):

        await _handle_start_project_intent(fake_update, "user_123", "a test app")

    assert captured_text, "No message was sent"
    full_text = " ".join(captured_text)
    assert expected_fragment in full_text, (
        f"Expected '{expected_fragment}' in cost estimate for {mode} mode. Got: {full_text}"
    )
