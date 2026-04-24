"""
v5.8.14 Phase 1 — Mode Persistence Tests (Issue 36)

Verifies that all three mode axes (master / execution / transport) are
correctly persisted, loaded, and applied to new PipelineState objects.

Tests:
  1.  _PREFS_DEFAULTS contains master_mode and transport_mode
  2.  ModeStore loads master_mode from prefs correctly
  3.  ModeStore loads transport_mode from prefs correctly
  4.  ModeStore.set_master persists and updates in-memory state
  5.  ModeStore.set_transport persists and updates in-memory state
  6.  ModeStore.apply_to_state stamps all three axes onto PipelineState
  7.  _start_project passes master_mode from prefs to PipelineState
  8.  _start_project BASIC → PipelineState.master_mode == BASIC
  9.  _detect_transport_default returns 'webhook' when TELEGRAM_WEBHOOK_URL is set
  10. _detect_transport_default returns 'polling' when no webhook URL
  11. load_operator_preferences merges _PREFS_DEFAULTS for missing keys
  12. set_transport rejects invalid values with ValueError
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from factory.core.mode_router import MasterMode
from factory.core.state import PipelineState, ExecutionMode, AutonomyMode
from factory.telegram.decisions import _PREFS_DEFAULTS
from factory.telegram.mode_store import ModeStore, _detect_transport_default, TRANSPORT_POLLING, TRANSPORT_WEBHOOK


# ═══════════════════════════════════════════════════════════════════
# Test 1: _PREFS_DEFAULTS has all required keys
# ═══════════════════════════════════════════════════════════════════

def test_prefs_defaults_has_master_mode():
    """_PREFS_DEFAULTS must include master_mode (Issue 36)."""
    assert "master_mode" in _PREFS_DEFAULTS, (
        "_PREFS_DEFAULTS is missing 'master_mode' — Issue 36 fix not applied"
    )
    assert _PREFS_DEFAULTS["master_mode"] == "basic"  # Phase 8: default changed to free tier


def test_prefs_defaults_has_transport_mode():
    """_PREFS_DEFAULTS must include transport_mode (Issue 36)."""
    assert "transport_mode" in _PREFS_DEFAULTS, (
        "_PREFS_DEFAULTS is missing 'transport_mode' — Issue 36 fix not applied"
    )
    assert _PREFS_DEFAULTS["transport_mode"] in (TRANSPORT_POLLING, TRANSPORT_WEBHOOK)


# ═══════════════════════════════════════════════════════════════════
# Test 2: ModeStore loads master_mode from prefs
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mode_store_loads_master_mode():
    """ModeStore.master_mode reflects the prefs value after load()."""
    store = ModeStore("op-test-1")
    with patch(
        "factory.telegram.mode_store.load_operator_preferences",
        AsyncMock(return_value={"master_mode": "basic", "execution_mode": "cloud",
                                "autonomy_mode": "autopilot", "transport_mode": "polling"}),
    ):
        await store.load()
    assert store.master_mode == MasterMode.BASIC, (
        f"Expected BASIC, got {store.master_mode}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 3: ModeStore loads transport_mode from prefs
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mode_store_loads_transport_mode():
    """ModeStore.transport_mode reflects the prefs value after load()."""
    store = ModeStore("op-test-2")
    with patch(
        "factory.telegram.mode_store.load_operator_preferences",
        AsyncMock(return_value={"master_mode": "balanced", "execution_mode": "cloud",
                                "autonomy_mode": "autopilot", "transport_mode": "webhook"}),
    ):
        await store.load()
    assert store.transport_mode == TRANSPORT_WEBHOOK


# ═══════════════════════════════════════════════════════════════════
# Test 4: ModeStore.set_master persists
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mode_store_set_master_persists():
    """set_master() updates in-memory value and calls set_operator_preference."""
    store = ModeStore("op-test-3")
    store._loaded = True
    store._prefs = {"master_mode": "balanced"}

    with patch(
        "factory.telegram.mode_store.set_operator_preference", new=AsyncMock()
    ) as mock_set:
        await store.set_master("turbo")
        mock_set.assert_awaited_once_with("op-test-3", "master_mode", "turbo")

    assert store.master_mode == MasterMode.TURBO


# ═══════════════════════════════════════════════════════════════════
# Test 5: ModeStore.set_transport persists
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mode_store_set_transport_persists():
    """set_transport() updates in-memory value and calls set_operator_preference."""
    store = ModeStore("op-test-4")
    store._loaded = True
    store._prefs = {"transport_mode": "polling"}

    with patch(
        "factory.telegram.mode_store.set_operator_preference", new=AsyncMock()
    ) as mock_set:
        await store.set_transport("webhook")
        mock_set.assert_awaited_once_with("op-test-4", "transport_mode", "webhook")

    assert store.transport_mode == TRANSPORT_WEBHOOK


# ═══════════════════════════════════════════════════════════════════
# Test 6: ModeStore.apply_to_state stamps all three axes
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mode_store_apply_to_state():
    """apply_to_state() stamps master, execution, and autonomy onto PipelineState."""
    store = ModeStore("op-test-5")
    store._loaded = True
    store._prefs = {
        "master_mode":    "basic",
        "execution_mode": "local",
        "autonomy_mode":  "copilot",
        "transport_mode": "polling",
    }

    state = PipelineState(project_id="t-apply", operator_id="op-test-5")
    # Before apply_to_state: default is BASIC (Phase 8: changed from BALANCED to free-tier safe default)
    assert state.master_mode == MasterMode.BASIC

    store.apply_to_state(state)

    assert state.master_mode    == MasterMode.BASIC
    assert state.execution_mode == ExecutionMode.LOCAL
    assert state.autonomy_mode  == AutonomyMode.COPILOT


# ═══════════════════════════════════════════════════════════════════
# Test 7: _start_project passes master_mode from prefs to PipelineState
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_start_project_applies_master_mode():
    """PipelineState created by _start_project must reflect master_mode from prefs."""
    from factory.telegram.bot import _start_project

    captured_states = []

    async def _fake_update_state(s):
        captured_states.append(s)

    fake_update = MagicMock()
    fake_update.effective_user.id = 999001
    fake_update.message = MagicMock()
    fake_update.message.reply_text = AsyncMock()

    with patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={
                   "master_mode": "basic",
                   "execution_mode": "cloud",
                   "autonomy_mode": "autopilot",
                   "transport_mode": "polling",
               })), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot.update_project_state", AsyncMock(side_effect=_fake_update_state)), \
         patch("factory.telegram.bot._bg", lambda coro: None), \
         patch("factory.telegram.bot.register_project_task"):
        await _start_project(
            fake_update, "999001", "A task app", "TestApp",
            pre_selected_platforms=None, pre_selected_market=None, pre_selected_logo=None,
        )

    assert captured_states, "update_project_state was never called"
    state = captured_states[0]
    assert state.master_mode == MasterMode.BASIC, (
        f"Expected BASIC master_mode, got {state.master_mode} — Issue 36 fix not effective"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 8: _start_project with BALANCED prefs → BALANCED PipelineState
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_start_project_balanced_master_mode():
    """Default prefs (balanced) → PipelineState.master_mode == BALANCED."""
    from factory.telegram.bot import _start_project

    captured_states = []

    async def _fake_update_state(s):
        captured_states.append(s)

    fake_update = MagicMock()
    fake_update.effective_user.id = 999002
    fake_update.message = MagicMock()
    fake_update.message.reply_text = AsyncMock()

    with patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={
                   "master_mode": "balanced",
                   "execution_mode": "cloud",
                   "autonomy_mode": "autopilot",
               })), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot.update_project_state", AsyncMock(side_effect=_fake_update_state)), \
         patch("factory.telegram.bot._bg", lambda coro: None), \
         patch("factory.telegram.bot.register_project_task"):
        await _start_project(
            fake_update, "999002", "Another app", "OtherApp",
            pre_selected_platforms=None, pre_selected_market=None, pre_selected_logo=None,
        )

    assert captured_states, "update_project_state was never called"
    assert captured_states[0].master_mode == MasterMode.BALANCED


# ═══════════════════════════════════════════════════════════════════
# Test 9: _detect_transport_default → webhook when URL is set
# ═══════════════════════════════════════════════════════════════════

def test_detect_transport_default_webhook(monkeypatch):
    """When TELEGRAM_WEBHOOK_URL is set, default transport is webhook."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.com/webhook")
    assert _detect_transport_default() == TRANSPORT_WEBHOOK


# ═══════════════════════════════════════════════════════════════════
# Test 10: _detect_transport_default → polling when no webhook URL
# ═══════════════════════════════════════════════════════════════════

def test_detect_transport_default_polling(monkeypatch):
    """When TELEGRAM_WEBHOOK_URL is not set, default transport is polling."""
    monkeypatch.delenv("TELEGRAM_WEBHOOK_URL", raising=False)
    assert _detect_transport_default() == TRANSPORT_POLLING


# ═══════════════════════════════════════════════════════════════════
# Test 11: load_operator_preferences merges defaults for missing keys
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_load_prefs_merges_defaults():
    """load_operator_preferences must include master_mode even for old rows missing it."""
    from factory.telegram.decisions import load_operator_preferences, _operator_prefs

    # Simulate a Supabase row that predates Issue 36 (only has autonomy_mode)
    old_row = {"context": {"autonomy_mode": "copilot"}}
    _operator_prefs.pop("op-legacy-36", None)   # ensure clean state

    # decisions.py does: from factory.integrations.supabase import get_operator_state_db
    # inside load_operator_preferences — patch at the supabase module level
    with patch(
        "factory.integrations.supabase.get_operator_state_db",
        AsyncMock(return_value=old_row),
    ):
        prefs = await load_operator_preferences("op-legacy-36")

    assert "master_mode" in prefs, "master_mode not merged from _PREFS_DEFAULTS"
    assert prefs["master_mode"] == "basic"  # Phase 8: default changed to free tier
    assert prefs["autonomy_mode"] == "copilot"   # row value preserved

    # Cleanup
    _operator_prefs.pop("op-legacy-36", None)


# ═══════════════════════════════════════════════════════════════════
# Test 12: set_transport rejects invalid values
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mode_store_set_transport_rejects_invalid():
    """set_transport with invalid value must raise ValueError."""
    store = ModeStore("op-test-6")
    store._loaded = True
    store._prefs = {}

    with pytest.raises(ValueError, match="transport_mode must be"):
        await store.set_transport("fax")
