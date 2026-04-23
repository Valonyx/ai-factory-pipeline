"""
Issue 28 — S0 Conversational Onboarding Flow

Tests verify:
  1. _onboarding_ask_platforms helper exists and is callable
  2. _onboarding_ask_market helper exists and is callable
  3. _onboarding_ask_logo helper exists and is callable
  4. _onboarding_show_summary helper exists and is callable
  5. _start_project accepts pre_selected_* kwargs
  6. pre_selected_platforms bypasses interactive step in s0_intake_node
  7. pre_selected_market bypasses interactive step in s0_intake_node
  8. pre_selected_logo="skip" skips logo flow in s0_intake_node
  9. pre_selected_logo="auto" triggers auto-gen in s0_intake_node
 10. onboarding platform presets cover mobile, web, mobile+web, custom
 11. onboarding market options include ksa, gcc, global, custom
 12. _parse_platform_reply works for text replies in awaiting_platforms_custom
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from factory.core.state import PipelineState, AutonomyMode


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_state(**kwargs) -> PipelineState:
    return PipelineState(
        project_id="test_onboard_001",
        operator_id="op_test",
        **kwargs,
    )


def _fake_update(reply_text_mock=None):
    upd = MagicMock()
    upd.message = MagicMock()
    upd.message.reply_text = reply_text_mock or AsyncMock()
    upd.effective_user = MagicMock()
    upd.effective_user.id = 12345
    return upd


# ═══════════════════════════════════════════════════════════════════
# Test 1-4: helpers exist
# ═══════════════════════════════════════════════════════════════════

def test_onboarding_helpers_importable():
    """All four onboarding helper functions are importable from bot."""
    from factory.telegram.bot import (
        _onboarding_ask_platforms,
        _onboarding_ask_market,
        _onboarding_ask_logo,
        _onboarding_show_summary,
    )
    assert callable(_onboarding_ask_platforms)
    assert callable(_onboarding_ask_market)
    assert callable(_onboarding_ask_logo)
    assert callable(_onboarding_show_summary)


# ═══════════════════════════════════════════════════════════════════
# Test 5: _start_project accepts pre_selected_* kwargs
# ═══════════════════════════════════════════════════════════════════

def test_start_project_accepts_pre_selected_kwargs():
    """_start_project signature includes pre_selected_platforms/market/logo."""
    import inspect
    from factory.telegram.bot import _start_project
    sig = inspect.signature(_start_project)
    params = sig.parameters
    assert "pre_selected_platforms" in params
    assert "pre_selected_market" in params
    assert "pre_selected_logo" in params


# ═══════════════════════════════════════════════════════════════════
# Tests 6-9: s0_intake_node uses pre-selected data
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pre_selected_platforms_bypasses_interactive():
    """s0_intake_node uses pre_selected_platforms instead of calling _select_platforms."""
    from factory.pipeline import s0_intake

    state = _make_state()
    state.project_metadata = {
        "raw_input": "A food delivery app called FoodDash",
        "app_name": "FoodDash",
        "pre_selected_platforms": ["ios", "web"],
        "pre_selected_market": "ksa",
        "pre_selected_logo": "skip",
    }

    _select_platforms_called = []

    async def _mock_select_platforms(s, reqs):
        _select_platforms_called.append(True)
        return ["android"]

    async def _mock_extract(raw, att, s):
        return {
            "app_name": "FoodDash",
            "app_description": "food delivery app",
            "app_category": "delivery",
            "features_must": [],
            "features_nice": [],
            "target_platforms": ["android"],
            "has_payments": True,
            "has_user_accounts": True,
            "has_location": True,
            "has_notifications": True,
            "has_realtime": False,
            "estimated_complexity": "medium",
        }

    with patch.object(s0_intake, "_extract_requirements", _mock_extract), \
         patch.object(s0_intake, "_select_platforms", _mock_select_platforms), \
         patch.object(s0_intake, "_select_market", AsyncMock(return_value="gcc")), \
         patch.object(s0_intake, "_scout_scan", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_scope_confirmation", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_logo_flow", AsyncMock(return_value=None)), \
         patch.object(s0_intake, "_logo_flow_auto", AsyncMock(return_value=None)), \
         patch.object(s0_intake, "_mode_selection", AsyncMock(side_effect=lambda s, r: r)), \
         patch("factory.core.stage_enrichment.store_stage_insight", AsyncMock()):

        result = await s0_intake.s0_intake_node(state)

    assert not _select_platforms_called, "_select_platforms should NOT be called when pre-selected"
    assert result.s0_output["target_platforms"] == ["ios", "web"]


@pytest.mark.asyncio
async def test_pre_selected_market_bypasses_interactive():
    """s0_intake_node uses pre_selected_market instead of calling _select_market."""
    from factory.pipeline import s0_intake

    state = _make_state()
    state.project_metadata = {
        "raw_input": "A fitness app called FitNow",
        "app_name": "FitNow",
        "pre_selected_platforms": ["android"],
        "pre_selected_market": "gcc",
        "pre_selected_logo": "skip",
    }

    _select_market_called = []

    async def _mock_select_market(s):
        _select_market_called.append(True)
        return "ksa"

    async def _mock_extract(raw, att, s):
        return {
            "app_name": "FitNow",
            "app_description": "fitness app",
            "app_category": "fitness",
            "features_must": [],
            "features_nice": [],
            "target_platforms": ["android"],
            "has_payments": False,
            "has_user_accounts": True,
            "has_location": False,
            "has_notifications": True,
            "has_realtime": False,
            "estimated_complexity": "simple",
        }

    with patch.object(s0_intake, "_extract_requirements", _mock_extract), \
         patch.object(s0_intake, "_select_platforms", AsyncMock(return_value=["android"])), \
         patch.object(s0_intake, "_select_market", _mock_select_market), \
         patch.object(s0_intake, "_scout_scan", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_scope_confirmation", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_logo_flow", AsyncMock(return_value=None)), \
         patch.object(s0_intake, "_logo_flow_auto", AsyncMock(return_value=None)), \
         patch.object(s0_intake, "_mode_selection", AsyncMock(side_effect=lambda s, r: r)), \
         patch("factory.core.stage_enrichment.store_stage_insight", AsyncMock()):

        result = await s0_intake.s0_intake_node(state)

    assert not _select_market_called, "_select_market should NOT be called when pre-selected"
    assert result.s0_output["target_market"] == "gcc"


@pytest.mark.asyncio
async def test_pre_selected_logo_skip():
    """s0_intake_node skips logo flow when pre_selected_logo='skip'."""
    from factory.pipeline import s0_intake

    state = _make_state()
    state.project_metadata = {
        "raw_input": "A shopping app called ShopNow",
        "app_name": "ShopNow",
        "pre_selected_platforms": ["ios"],
        "pre_selected_market": "ksa",
        "pre_selected_logo": "skip",
    }

    logo_flow_called = []

    async def _mock_extract(raw, att, s):
        return {
            "app_name": "ShopNow",
            "app_description": "shopping app",
            "app_category": "e-commerce",
            "features_must": [],
            "features_nice": [],
            "target_platforms": ["ios"],
            "has_payments": True,
            "has_user_accounts": True,
            "has_location": False,
            "has_notifications": True,
            "has_realtime": False,
            "estimated_complexity": "medium",
        }

    async def _mock_logo(*args):
        logo_flow_called.append(True)
        return {"logo_path": "/tmp/logo.png"}

    with patch.object(s0_intake, "_extract_requirements", _mock_extract), \
         patch.object(s0_intake, "_select_platforms", AsyncMock(return_value=["ios"])), \
         patch.object(s0_intake, "_select_market", AsyncMock(return_value="ksa")), \
         patch.object(s0_intake, "_scout_scan", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_scope_confirmation", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_logo_flow", _mock_logo), \
         patch.object(s0_intake, "_logo_flow_auto", _mock_logo), \
         patch.object(s0_intake, "_mode_selection", AsyncMock(side_effect=lambda s, r: r)), \
         patch("factory.core.stage_enrichment.store_stage_insight", AsyncMock()):

        await s0_intake.s0_intake_node(state)

    assert not logo_flow_called, "_logo_flow / _logo_flow_auto should NOT be called when logo=skip"


@pytest.mark.asyncio
async def test_pre_selected_logo_auto():
    """pre_selected_logo='auto' now routes through _logo_flow (3-variant picker).

    v5.8.16 Phase 6: The 'auto' shortcut no longer bypasses the interactive
    3-variant selection.  'auto' means 'AI picks the style prompts', but the
    operator still gets to pick from the 3 generated variants.  Only the
    explicit logo_autopilot=True flag routes to _logo_flow_auto (silent).
    """
    from factory.pipeline import s0_intake

    state = _make_state()
    state.project_metadata = {
        "raw_input": "A social app called SocialMe",
        "app_name": "SocialMe",
        "pre_selected_platforms": ["ios", "android"],
        "pre_selected_market": "global",
        "pre_selected_logo": "auto",   # <-- triggers _logo_flow (interactive)
    }

    logo_auto_called = []
    logo_flow_called = []

    async def _mock_extract(raw, att, s):
        return {
            "app_name": "SocialMe",
            "app_description": "social app",
            "app_category": "social",
            "features_must": [],
            "features_nice": [],
            "target_platforms": ["ios", "android"],
            "has_payments": False,
            "has_user_accounts": True,
            "has_location": False,
            "has_notifications": True,
            "has_realtime": True,
            "estimated_complexity": "medium",
        }

    async def _mock_logo_auto(*args):
        logo_auto_called.append(True)
        return {"logo_path": "/tmp/auto_logo.png", "asset_type": "logo"}

    async def _mock_logo_flow(*args):
        logo_flow_called.append(True)
        return {"logo_path": "/tmp/picked_logo.png", "asset_type": "logo"}

    with patch.object(s0_intake, "_extract_requirements", _mock_extract), \
         patch.object(s0_intake, "_select_platforms", AsyncMock(return_value=["ios", "android"])), \
         patch.object(s0_intake, "_select_market", AsyncMock(return_value="global")), \
         patch.object(s0_intake, "_scout_scan", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_scope_confirmation", AsyncMock(side_effect=lambda s, r, _: r)), \
         patch.object(s0_intake, "_logo_flow", _mock_logo_flow), \
         patch.object(s0_intake, "_logo_flow_auto", _mock_logo_auto), \
         patch.object(s0_intake, "_mode_selection", AsyncMock(side_effect=lambda s, r: r)), \
         patch("factory.core.stage_enrichment.store_stage_insight", AsyncMock()):

        result = await s0_intake.s0_intake_node(state)

    # Since logo_autopilot is not True, _logo_flow (3-variant) should be called
    assert logo_flow_called, (
        "_logo_flow (3-variant picker) should be called for pre_selected_logo='auto'. "
        "Use project_metadata['logo_autopilot']=True for silent single-logo generation."
    )
    assert not logo_auto_called, "_logo_flow_auto should NOT be called without logo_autopilot=True"


# ═══════════════════════════════════════════════════════════════════
# Tests 10-12: onboarding data structures
# ═══════════════════════════════════════════════════════════════════

def test_onboard_platform_presets_coverage():
    """Platform presets include mobile, web, mobile+web, custom."""
    from factory.telegram.bot import _ONBOARD_PLATFORM_PRESETS
    values = {opt["value"] for opt in _ONBOARD_PLATFORM_PRESETS}
    assert "ios,android" in values
    assert "web" in values
    assert "ios,android,web" in values
    assert "custom" in values


def test_onboard_market_options_coverage():
    """Market options include all four required values."""
    from factory.telegram.bot import _ONBOARD_MARKET_OPTIONS
    values = {opt["value"] for opt in _ONBOARD_MARKET_OPTIONS}
    assert "ksa" in values
    assert "gcc" in values
    assert "global" in values
    assert "custom" in values


def test_parse_platform_reply_for_custom_text():
    """_parse_platform_reply handles text input for awaiting_platforms_custom."""
    from factory.telegram.decisions import _parse_platform_reply
    result = _parse_platform_reply("ios,android,web", [])
    assert "ios" in result
    assert "android" in result
    assert "web" in result

    result2 = _parse_platform_reply("mobile", [])
    assert "ios" in result2
    assert "android" in result2
