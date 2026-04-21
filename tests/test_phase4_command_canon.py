"""
v5.8.14 Phase 4 — Command Canon & AI Router Tests (Issues 42, 44)

Issue 44: /local is transport-only; /execution_mode local is for execution axis.
          /mode status panel shows current transport value.
Issue 42: Mid-pipeline conversational messages get AI response (not "start project" attempt).

Tests:
  1.  cmd_local reply contains 'transport' disambiguation word
  2.  cmd_local reply mentions /execution_mode local
  3.  cmd_online reply contains 'transport' disambiguation word
  4.  /mode status shows current transport mode value (not just setter)
  5.  /mode status shows 'Execution axis' label with /execution_mode command
  6.  handle_message with active pipeline + start_project intent → pipeline-running reply
  7.  handle_message with active pipeline + start_project intent → no _handle_start_project_intent call
  8.  handle_message with HALTED pipeline + start_project intent → _handle_start_project_intent called
  9.  handle_message with no pipeline + start_project intent → _handle_start_project_intent called
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from factory.core.state import PipelineState, Stage, ExecutionMode
from factory.core.mode_router import MasterMode


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_update(uid: int = 77001, text: str = "test", update_id: int = 1):
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


def _handle_message_patches(
    active=None,
    intent="start_project",
    confidence=0.85,
    ai_response="Pipeline is running!",
):
    """Return context managers for patching handle_message dependencies."""
    return (
        patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)),
        patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=active)),
        patch("factory.telegram.ai_handler._check_rate_limit", return_value=True),
        patch("factory.telegram.ai_handler._is_injection_attempt", return_value=False),
        patch("factory.telegram.ai_handler._sanitize", side_effect=lambda x: x),
        patch("factory.telegram.decisions.has_pending_reply", return_value=False),
        patch("factory.telegram.bot.get_operator_state", AsyncMock(return_value=None)),
        patch("factory.telegram.ai_handler.has_pending_confirmation", return_value=False),
        patch("factory.telegram.ai_handler.load_history_from_memory", AsyncMock()),
        patch("factory.telegram.bot.load_operator_preferences",
              AsyncMock(return_value={"master_mode": "balanced"})),
        patch("factory.telegram.ai_handler.classify_intent",
              AsyncMock(return_value=(intent, confidence))),
        patch("factory.telegram.ai_handler.ai_respond",
              AsyncMock(return_value=ai_response)),
    )


# ═══════════════════════════════════════════════════════════════════
# Test 1: cmd_local reply contains 'transport' disambiguation
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_local_mentions_transport():
    """cmd_local reply must mention 'transport' to disambiguate from execution axis."""
    from factory.telegram.bot import cmd_local

    update = _make_update(77001)
    ctx = MagicMock()
    ctx.args = []

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.decisions.set_operator_preference", AsyncMock()), \
         patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__ = lambda s: s
        mock_url.return_value.__exit__ = MagicMock(return_value=False)
        mock_url.return_value.read.return_value = b'{"ok": true}'
        await cmd_local(update, ctx)

    full_text = " ".join(update._replied).lower()
    assert "transport" in full_text, (
        f"'transport' missing from cmd_local reply — Issue 44 fix not applied.\nReply: {full_text[:300]}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 2: cmd_local mentions /execution_mode local
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_local_mentions_execution_mode():
    """cmd_local reply must mention /execution_mode local for disambiguation."""
    from factory.telegram.bot import cmd_local

    update = _make_update(77002)
    ctx = MagicMock()
    ctx.args = []

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.decisions.set_operator_preference", AsyncMock()), \
         patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__ = lambda s: s
        mock_url.return_value.__exit__ = MagicMock(return_value=False)
        mock_url.return_value.read.return_value = b'{"ok": true}'
        await cmd_local(update, ctx)

    full_text = " ".join(update._replied).lower()
    assert "execution_mode" in full_text or "execution mode" in full_text, (
        f"'/execution_mode local' mention missing from cmd_local reply.\nReply: {full_text[:300]}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 3: cmd_online reply contains 'transport' disambiguation
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_online_mentions_transport():
    """cmd_online reply must mention 'transport' to disambiguate from execution axis."""
    from factory.telegram.bot import cmd_online

    update = _make_update(77003)
    ctx = MagicMock()
    ctx.args = []

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.decisions.set_operator_preference", AsyncMock()), \
         patch("factory.telegram.bot._get_runner", return_value=None):
        await cmd_online(update, ctx)

    full_text = " ".join(update._replied).lower()
    assert "transport" in full_text, (
        f"'transport' missing from cmd_online reply — Issue 44 fix not applied.\nReply: {full_text[:300]}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 4: /mode status shows current transport mode value
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_mode_shows_current_transport():
    """cmd_mode status must show current transport mode (polling/webhook), not just setter."""
    from factory.telegram.bot import cmd_mode

    update = _make_update(77004, text="")
    ctx = MagicMock()
    ctx.args = []

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced", "execution_mode": "cloud",
                                       "autonomy_mode": "autopilot", "transport_mode": "webhook"})):
        await cmd_mode(update, ctx)

    full_text = " ".join(update._replied)
    assert "WEBHOOK" in full_text or "webhook" in full_text.lower(), (
        f"Current transport mode 'webhook' not shown in /mode status.\nReply: {full_text[:400]}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 5: /mode status shows Execution axis with /execution_mode command
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_mode_shows_execution_axis_command():
    """cmd_mode status must show /execution_mode command for the execution axis."""
    from factory.telegram.bot import cmd_mode

    update = _make_update(77005, text="")
    ctx = MagicMock()
    ctx.args = []

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced", "execution_mode": "cloud",
                                       "autonomy_mode": "autopilot", "transport_mode": "polling"})):
        await cmd_mode(update, ctx)

    full_text = " ".join(update._replied)
    assert "execution_mode" in full_text or "execution\\_mode" in full_text, (
        f"/execution_mode command not shown in /mode status.\nReply: {full_text[:400]}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 6: handle_message active pipeline + start_project → pipeline-running reply
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_handle_message_active_pipeline_start_project_gives_running_reply():
    """When pipeline is running, 'start_project' intent → pipeline-running message (Issue 42)."""
    from factory.telegram.bot import handle_message

    running_state = PipelineState(project_id="p42-run", operator_id="op-42",
                                  project_metadata={"raw_input": "test"})
    running_state.current_stage = Stage.S2_BLUEPRINT

    update = _make_update(77006, text="I want to build a food delivery app", update_id=42001)

    active = {"project_id": "p42-run", "state_json": running_state.model_dump(),
              "current_stage": "S2_BLUEPRINT"}

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=active)), \
         patch("factory.telegram.ai_handler._check_rate_limit", return_value=True), \
         patch("factory.telegram.ai_handler._is_injection_attempt", return_value=False), \
         patch("factory.telegram.ai_handler._sanitize", side_effect=lambda x: x), \
         patch("factory.telegram.decisions.has_pending_reply", return_value=False), \
         patch("factory.telegram.bot.get_operator_state", AsyncMock(return_value=None)), \
         patch("factory.telegram.ai_handler.has_pending_confirmation", return_value=False), \
         patch("factory.telegram.ai_handler.load_history_from_memory", AsyncMock()), \
         patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced"})), \
         patch("factory.telegram.ai_handler.classify_intent",
               AsyncMock(return_value=("start_project", 0.85))), \
         patch("factory.telegram.ai_handler.ai_respond",
               AsyncMock(return_value="Your pipeline is making progress.")), \
         patch("factory.telegram.bot._handle_start_project_intent") as mock_start:
        await handle_message(update, MagicMock())

    mock_start.assert_not_called()
    full_text = " ".join(update._replied).lower()
    assert "running" in full_text or "pipeline" in full_text, (
        f"Expected pipeline-running reply, got: {update._replied}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 7: active pipeline + start_project → no _handle_start_project_intent call
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_handle_message_active_pipeline_no_start():
    """With active running pipeline, start_project intent must NOT call _handle_start_project_intent."""
    from factory.telegram.bot import handle_message

    running_state = PipelineState(project_id="p42-run2", operator_id="op-42")
    running_state.current_stage = Stage.S4_CODEGEN

    update = _make_update(77007, text="Build me a task app", update_id=42002)
    active = {"project_id": "p42-run2", "state_json": running_state.model_dump(),
              "current_stage": "S4_CODEGEN"}

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=active)), \
         patch("factory.telegram.ai_handler._check_rate_limit", return_value=True), \
         patch("factory.telegram.ai_handler._is_injection_attempt", return_value=False), \
         patch("factory.telegram.ai_handler._sanitize", side_effect=lambda x: x), \
         patch("factory.telegram.decisions.has_pending_reply", return_value=False), \
         patch("factory.telegram.bot.get_operator_state", AsyncMock(return_value=None)), \
         patch("factory.telegram.ai_handler.has_pending_confirmation", return_value=False), \
         patch("factory.telegram.ai_handler.load_history_from_memory", AsyncMock()), \
         patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced"})), \
         patch("factory.telegram.ai_handler.classify_intent",
               AsyncMock(return_value=("start_project", 0.90))), \
         patch("factory.telegram.ai_handler.ai_respond", AsyncMock(return_value="Pipeline running!")), \
         patch("factory.telegram.bot._handle_start_project_intent") as mock_start:
        await handle_message(update, MagicMock())

    mock_start.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Test 8: HALTED pipeline + start_project → _handle_start_project_intent called
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_handle_message_halted_pipeline_allows_start():
    """With HALTED pipeline, start_project intent SHOULD call _handle_start_project_intent."""
    from factory.telegram.bot import handle_message

    halted_state = PipelineState(project_id="p42-halt", operator_id="op-42")
    halted_state.current_stage = Stage.HALTED

    update = _make_update(77008, text="Build me a task app", update_id=42003)
    active = {"project_id": "p42-halt", "state_json": halted_state.model_dump(),
              "current_stage": "HALTED"}

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=active)), \
         patch("factory.telegram.ai_handler._check_rate_limit", return_value=True), \
         patch("factory.telegram.ai_handler._is_injection_attempt", return_value=False), \
         patch("factory.telegram.ai_handler._sanitize", side_effect=lambda x: x), \
         patch("factory.telegram.decisions.has_pending_reply", return_value=False), \
         patch("factory.telegram.bot.get_operator_state", AsyncMock(return_value=None)), \
         patch("factory.telegram.ai_handler.has_pending_confirmation", return_value=False), \
         patch("factory.telegram.ai_handler.load_history_from_memory", AsyncMock()), \
         patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced"})), \
         patch("factory.telegram.ai_handler.classify_intent",
               AsyncMock(return_value=("start_project", 0.90))), \
         patch("factory.telegram.ai_handler.ai_respond", AsyncMock(return_value="OK")), \
         patch("factory.telegram.bot._handle_start_project_intent", AsyncMock()) as mock_start:
        await handle_message(update, MagicMock())

    mock_start.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Test 9: no pipeline + start_project → _handle_start_project_intent called
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_handle_message_no_pipeline_allows_start():
    """With no active pipeline, start_project intent SHOULD call _handle_start_project_intent."""
    from factory.telegram.bot import handle_message

    update = _make_update(77009, text="I want to build an app", update_id=42004)

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.ai_handler._check_rate_limit", return_value=True), \
         patch("factory.telegram.ai_handler._is_injection_attempt", return_value=False), \
         patch("factory.telegram.ai_handler._sanitize", side_effect=lambda x: x), \
         patch("factory.telegram.decisions.has_pending_reply", return_value=False), \
         patch("factory.telegram.bot.get_operator_state", AsyncMock(return_value=None)), \
         patch("factory.telegram.ai_handler.has_pending_confirmation", return_value=False), \
         patch("factory.telegram.ai_handler.load_history_from_memory", AsyncMock()), \
         patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced"})), \
         patch("factory.telegram.ai_handler.classify_intent",
               AsyncMock(return_value=("start_project", 0.90))), \
         patch("factory.telegram.ai_handler.ai_respond", AsyncMock(return_value="OK")), \
         patch("factory.telegram.bot._handle_start_project_intent", AsyncMock()) as mock_start:
        await handle_message(update, MagicMock())

    mock_start.assert_called_once()
