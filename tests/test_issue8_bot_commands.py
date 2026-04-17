"""
AI Factory Pipeline v5.8.12 — Issue 8: Telegram Bot Command Smoke Tests

Covers the commands added / wired in Phases 1–6 that weren't yet tested:
  /rerun          — regression target prompt + confirm path
  /rerun_confirm  — execute regression
  /diff           — snapshot diff display
  /providers      — AI/memory chain status
  /switch_mode    — alias for /mode

Pattern: mock Telegram update + context objects; patch authenticate_operator
to always return True; verify reply_text is called with expected text snippets.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_update(user_id: int = 634992850, message_text: str = "") -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    update.message.text = message_text
    return update


def _make_context(*args: str) -> MagicMock:
    ctx = MagicMock()
    ctx.args = list(args)
    return ctx


def _patches():
    """Common patches: auth always passes, no active project by default."""
    return [
        patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)),
        patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=None)),
    ]


# ═══════════════════════════════════════════════════════════════════
# /rerun tests
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_rerun_no_active_project():
    """/rerun with no active project → 'No active project' reply."""
    from factory.telegram.bot import cmd_rerun

    update = _make_update()
    ctx = _make_context("s4")

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=None)):
        await cmd_rerun(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "No active project" in reply_text


@pytest.mark.asyncio
async def test_cmd_rerun_no_args():
    """/rerun with no args → usage message shown."""
    from factory.telegram.bot import cmd_rerun

    update = _make_update()
    ctx = _make_context()   # no args

    active_proj = {"project_id": "proj-123", "stage": "S6_TEST", "state_json": {
        "project_id": "proj-123", "operator_id": "634992850",
    }}

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=active_proj)):
        await cmd_rerun(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "Usage" in reply_text or "usage" in reply_text.lower()


@pytest.mark.asyncio
async def test_cmd_rerun_unknown_stage():
    """/rerun garbage_stage → 'Unknown stage' reply."""
    from factory.telegram.bot import cmd_rerun

    update = _make_update()
    ctx = _make_context("garbage_stage")

    active_proj = {"project_id": "proj-123", "stage": "S6_TEST", "state_json": {
        "project_id": "proj-123", "operator_id": "634992850",
    }}

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=active_proj)):
        await cmd_rerun(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "Unknown stage" in reply_text or "unknown" in reply_text.lower()


@pytest.mark.asyncio
async def test_cmd_rerun_valid_stage_shows_impact():
    """/rerun s4 with active project → shows regression impact warning."""
    from factory.telegram.bot import cmd_rerun

    update = _make_update()
    ctx = _make_context("s4")

    active_proj = {"project_id": "proj-123", "stage": "S6_TEST", "state_json": {
        "project_id": "proj-123", "operator_id": "634992850",
    }}

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=active_proj)):
        await cmd_rerun(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    # Should contain the confirmation command
    assert "rerun_confirm" in reply_text


# ═══════════════════════════════════════════════════════════════════
# /rerun_confirm tests
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_rerun_confirm_no_active_project():
    """/rerun_confirm with no active project → 'No active project' reply."""
    from factory.telegram.bot import cmd_rerun_confirm

    update = _make_update()
    ctx = _make_context("s4")

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=None)):
        await cmd_rerun_confirm(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "No active project" in reply_text


@pytest.mark.asyncio
async def test_cmd_rerun_confirm_no_args():
    """/rerun_confirm with no args → usage message."""
    from factory.telegram.bot import cmd_rerun_confirm

    update = _make_update()
    ctx = _make_context()   # no args

    active_proj = {"project_id": "proj-123", "stage": "S4_CODEGEN", "state_json": {
        "project_id": "proj-123", "operator_id": "634992850",
    }}

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=active_proj)):
        await cmd_rerun_confirm(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "Usage" in reply_text or "usage" in reply_text.lower()


# ═══════════════════════════════════════════════════════════════════
# /diff tests
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_diff_no_active_project():
    """/diff with no active project → 'No active project' reply."""
    from factory.telegram.bot import cmd_diff

    update = _make_update()
    ctx = _make_context("3", "5")

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=None)):
        await cmd_diff(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "No active project" in reply_text


@pytest.mark.asyncio
async def test_cmd_diff_missing_args():
    """/diff with < 2 args → usage message."""
    from factory.telegram.bot import cmd_diff

    update = _make_update()
    ctx = _make_context("3")   # only one arg

    active_proj = {"project_id": "proj-999", "stage": "S6_TEST", "state_json": {
        "project_id": "proj-999", "operator_id": "634992850",
    }}

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=active_proj)):
        await cmd_diff(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "Usage" in reply_text or "usage" in reply_text.lower()


@pytest.mark.asyncio
async def test_cmd_diff_non_numeric_ids():
    """/diff with non-numeric snapshot IDs → error message."""
    from factory.telegram.bot import cmd_diff

    update = _make_update()
    ctx = _make_context("abc", "xyz")

    active_proj = {"project_id": "proj-999", "stage": "S6_TEST", "state_json": {
        "project_id": "proj-999", "operator_id": "634992850",
    }}

    with patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=active_proj)):
        await cmd_diff(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "number" in reply_text.lower() or "invalid" in reply_text.lower()


@pytest.mark.asyncio
async def test_cmd_diff_valid_args_shows_result():
    """/diff 2 4 with active project → renders diff output."""
    from factory.telegram.bot import cmd_diff

    update = _make_update()
    ctx = _make_context("2", "4")

    active_proj = {"project_id": "proj-999", "stage": "S6_TEST", "state_json": {
        "project_id": "proj-999", "operator_id": "634992850",
    }}

    diff_result = {
        "stage_a": "S4_CODEGEN",
        "stage_b": "S6_TEST",
        "cost_delta": 0.12,
        "fields_changed": ["s4_output", "s5_output"],
    }

    with (
        patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)),
        patch("factory.telegram.bot.get_active_project", new=AsyncMock(return_value=active_proj)),
        patch("factory.integrations.supabase.diff_snapshots", new=AsyncMock(return_value=diff_result)),
    ):
        await cmd_diff(update, ctx)

    reply_text = update.message.reply_text.call_args[0][0]
    # Should show stage names and cost delta
    assert "S4_CODEGEN" in reply_text or "Diff" in reply_text


# ═══════════════════════════════════════════════════════════════════
# /providers tests
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_providers_returns_status_message():
    """/providers → sends a message containing AI chain and memory chain info."""
    from factory.telegram.bot import cmd_providers

    update = _make_update()
    ctx = _make_context()

    # Minimal mocks for the chain objects cmd_providers accesses
    mock_chain = MagicMock()
    mock_chain.chain = ["anthropic", "gemini"]
    mock_chain.statuses = {
        "anthropic": MagicMock(
            quota_exhausted=False, quota_reset_at=None,
            available=True, last_error=None,
        ),
        "gemini": MagicMock(
            quota_exhausted=False, quota_reset_at=None,
            available=True, last_error=None,
        ),
    }
    mock_chain.get_active.return_value = "anthropic"

    mock_mem_status = [
        {"name": "neo4j", "available": True, "pending_writes": 0},
    ]

    with (
        patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)),
        patch("factory.integrations.provider_chain.ai_chain", mock_chain),
        patch("factory.integrations.provider_chain.scout_chain", mock_chain),
        patch("factory.memory.mother_memory.get_memory_chain_status", return_value=mock_mem_status),
        patch(
            "factory.core.provider_intelligence.provider_intelligence.status_message",
            return_value="_ProviderIntelligence: all OK_",
        ),
    ):
        await cmd_providers(update, ctx)

    assert update.message.reply_text.called
    reply_text = update.message.reply_text.call_args[0][0]
    assert "AI Provider" in reply_text or "anthropic" in reply_text.lower()


# ═══════════════════════════════════════════════════════════════════
# /switch_mode alias
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_switch_mode_delegates_to_cmd_mode():
    """/switch_mode is an alias for /mode — cmd_mode must be called."""
    from factory.telegram import bot as bot_module

    update = _make_update()
    ctx = _make_context()

    called_with = []

    async def _fake_mode(u, c):
        called_with.append((u, c))

    with (
        patch("factory.telegram.bot.authenticate_operator", new=AsyncMock(return_value=True)),
        patch.object(bot_module, "cmd_mode", new=_fake_mode),
    ):
        await bot_module.cmd_switch_mode(update, ctx)

    assert len(called_with) == 1
    assert called_with[0][0] is update
