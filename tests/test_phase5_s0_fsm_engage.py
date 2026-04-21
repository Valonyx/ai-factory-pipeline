"""
v5.8.14 Phase 5 — S0 FSM Always-Engage Tests (Issue 39)

Issue 39: /new <description> (inline) previously bypassed the multi-turn onboarding
FSM and called _start_project directly. Fix: route through _ask_app_name so name,
platform, market, and logo prompts always appear.

Tests:
  1.  /new <description> calls _ask_app_name (FSM engaged, not _start_project directly)
  2.  /new <description> does NOT call _start_project directly
  3.  /new (no args) still sets awaiting_project_description state
  4.  /new with active project blocks and doesn't start FSM
  5.  _ask_app_name with inline name extracts and skips to platform step
  6.  _ask_app_name without inline name sets awaiting_app_name state
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_update(uid: int = 88001, text: str = "test", update_id: int = 1):
    fake = MagicMock()
    fake.effective_user.id = uid
    fake.update_id = update_id
    fake.message = MagicMock()
    fake.message.text = text
    fake.message.photo = None
    replied = []
    fake.message.reply_text = AsyncMock(side_effect=lambda t, **kw: replied.append(t))
    fake._replied = replied
    return fake


def _make_ctx(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


# ═══════════════════════════════════════════════════════════════════
# Test 1: /new <description> routes through _ask_app_name
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_new_inline_desc_calls_ask_app_name():
    """Issue 39: /new <description> must call _ask_app_name (FSM), not _start_project."""
    from factory.telegram.bot import cmd_new_project

    update = _make_update(88001, update_id=39001)
    ctx = _make_ctx(args=["Build", "a", "task", "management", "app"])

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot._ask_app_name", AsyncMock()) as mock_ask_name, \
         patch("factory.telegram.bot._start_project", AsyncMock()) as mock_start:
        await cmd_new_project(update, ctx)

    mock_ask_name.assert_called_once()
    call_args = mock_ask_name.call_args
    # First positional arg is update, second is user_id, third is description
    assert call_args[0][2] == "Build a task management app", (
        f"_ask_app_name called with wrong description: {call_args}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 2: /new <description> does NOT call _start_project directly
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_new_inline_desc_does_not_call_start_project():
    """Issue 39: /new <description> must not call _start_project directly."""
    from factory.telegram.bot import cmd_new_project

    update = _make_update(88002, update_id=39002)
    ctx = _make_ctx(args=["Make", "a", "food", "delivery", "app"])

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot._ask_app_name", AsyncMock()) as mock_ask_name, \
         patch("factory.telegram.bot._start_project", AsyncMock()) as mock_start:
        await cmd_new_project(update, ctx)

    mock_start.assert_not_called()
    mock_ask_name.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Test 3: /new (no args) still sets awaiting_project_description
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_new_no_args_sets_awaiting_state():
    """/new with no args must set awaiting_project_description state (unchanged behavior)."""
    from factory.telegram.bot import cmd_new_project

    update = _make_update(88003, update_id=39003)
    ctx = _make_ctx(args=[])

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot.set_operator_state", AsyncMock()) as mock_set_state, \
         patch("factory.telegram.bot._ask_app_name", AsyncMock()) as mock_ask_name, \
         patch("factory.telegram.bot._start_project", AsyncMock()) as mock_start:
        await cmd_new_project(update, ctx)

    mock_ask_name.assert_not_called()
    mock_start.assert_not_called()
    mock_set_state.assert_called_once_with(88003 and str(88003) or "88003",
                                           "awaiting_project_description")
    # Also check the reply
    full_text = " ".join(update._replied).lower()
    assert "describe" in full_text or "idea" in full_text, (
        f"Expected description prompt; got: {update._replied}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 4: /new with active project blocks (no FSM)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_new_with_active_project_blocks():
    """/new when a project is active must reply with block message, not start FSM."""
    from factory.telegram.bot import cmd_new_project

    update = _make_update(88004, update_id=39004)
    ctx = _make_ctx(args=["Another", "app"])

    active = {"project_id": "proj_old", "current_stage": "S2_BLUEPRINT"}

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=active)), \
         patch("factory.telegram.messages.project_display_name", return_value="OldApp"), \
         patch("factory.telegram.bot._ask_app_name", AsyncMock()) as mock_ask_name, \
         patch("factory.telegram.bot._start_project", AsyncMock()) as mock_start:
        await cmd_new_project(update, ctx)

    mock_ask_name.assert_not_called()
    mock_start.assert_not_called()
    # Should have replied with a block message
    assert update._replied, "Expected a reply when project is active"
    full_text = " ".join(update._replied).lower()
    assert "cancel" in full_text or "active" in full_text, (
        f"Expected block message, got: {update._replied}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 5: _ask_app_name extracts inline name and goes to platforms
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ask_app_name_extracts_explicit_name():
    """_ask_app_name with 'app name: Pulsey AI' extracts name and calls _onboarding_ask_platforms."""
    from factory.telegram.bot import _ask_app_name

    update = _make_update(88005, update_id=39005)
    description = 'Build a fitness app. App name: "Pulsey AI". Target iOS and Android.'

    with patch("factory.telegram.bot._onboarding_ask_platforms", AsyncMock()) as mock_platforms, \
         patch("factory.telegram.bot.set_operator_state", AsyncMock()):
        await _ask_app_name(update, "88005", description)

    mock_platforms.assert_called_once()
    # The extracted name should be "Pulsey AI"
    call_args = mock_platforms.call_args[0]
    assert "Pulsey AI" in call_args, (
        f"Expected 'Pulsey AI' in platform call args: {call_args}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 6: _ask_app_name without explicit name sets awaiting state
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ask_app_name_no_name_sets_awaiting_state():
    """_ask_app_name without an extractable name must set awaiting_app_name state."""
    from factory.telegram.bot import _ask_app_name

    update = _make_update(88006, update_id=39006)
    description = "Build a general task management tool for teams."

    with patch("factory.telegram.bot.set_operator_state", AsyncMock()) as mock_set_state, \
         patch("factory.telegram.bot._onboarding_ask_platforms", AsyncMock()) as mock_platforms:
        await _ask_app_name(update, "88006", description)

    mock_platforms.assert_not_called()
    mock_set_state.assert_called_once()
    call_args = mock_set_state.call_args[0]
    assert "awaiting_app_name" in call_args, (
        f"Expected awaiting_app_name state, got: {call_args}"
    )
    # Should show prompt asking for the name
    full_text = " ".join(update._replied).lower()
    assert "called" in full_text or "name" in full_text, (
        f"Expected name prompt in reply: {update._replied}"
    )
