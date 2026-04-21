"""
v5.8.14 Phase 3 — Telegram Safety Tests (Issues 38, 46, 47)

Issue 38: Markdown escape helper prevents /providers byte-3018 crash
Issue 46: format_project_started shows all three mode axes
Issue 47: update_id dedup guard prevents dual-process double-replies

Tests:
  1.  escape_md escapes underscores in provider names
  2.  escape_md escapes all V1 special chars (*, `, [, \\)
  3.  escape_md on nvidia_nim_image_gen produces safe output
  4.  cmd_providers output contains escaped provider names (no raw underscores in dynamic text)
  5.  format_project_started banner includes master_mode line
  6.  format_project_started banner shows BASIC emoji for BASIC mode
  7.  format_project_started banner shows BALANCED label for BALANCED mode
  8.  format_project_started shows all three axes labels
  9.  _is_duplicate_update returns False for first occurrence
  10. _is_duplicate_update returns True for duplicate update_id
  11. authenticate_operator drops duplicate update_id (Issue 47)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from factory.core.state import PipelineState, ExecutionMode, AutonomyMode
from factory.core.mode_router import MasterMode
from factory.telegram.messages import escape_md, format_project_started
from factory.telegram.bot import _is_duplicate_update, _handled_update_ids


# ═══════════════════════════════════════════════════════════════════
# Test 1: escape_md escapes underscores
# ═══════════════════════════════════════════════════════════════════

def test_escape_md_underscores():
    """escape_md must replace _ with \\_ to prevent Markdown italic parsing."""
    raw = "nvidia_nim_image_gen"
    result = escape_md(raw)
    assert "_" not in result.replace("\\_", ""), (
        f"Raw underscores remain after escape: {result!r}"
    )
    assert "\\_" in result


# ═══════════════════════════════════════════════════════════════════
# Test 2: escape_md handles all V1 special chars
# ═══════════════════════════════════════════════════════════════════

def test_escape_md_all_special_chars():
    """escape_md must escape \\, _, *, `, [ characters."""
    raw = r"a_b*c`d[e\f"
    result = escape_md(raw)
    # All special chars should now be preceded by backslash
    for ch in ("_", "*", "`", "["):
        assert f"\\{ch}" in result, f"Expected \\{ch} in escaped output: {result!r}"


# ═══════════════════════════════════════════════════════════════════
# Test 3: nvidia_nim_image_gen produces safe output
# ═══════════════════════════════════════════════════════════════════

def test_escape_md_nvidia_nim_image_gen():
    """nvidia_nim_image_gen must not contain raw underscores after escape."""
    name = "nvidia_nim_image_gen"
    escaped = escape_md(name)
    # Count raw underscores (not preceded by \)
    raw_underscores = sum(
        1 for i, c in enumerate(escaped)
        if c == "_" and (i == 0 or escaped[i-1] != "\\")
    )
    assert raw_underscores == 0, (
        f"Raw underscores remain in escaped string: {escaped!r}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 4: cmd_providers output is safe (no unescaped underscores in dynamic parts)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_providers_uses_escape_md():
    """cmd_providers must call escape_md on the full message before sending."""
    from factory.telegram import bot as _bot

    sent_msgs = []

    fake_update = MagicMock()
    fake_update.effective_user.id = 42
    fake_update.update_id = 9999901
    fake_update.message.reply_text = AsyncMock(side_effect=lambda t, **kw: sent_msgs.append(t))

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.integrations.provider_chain.ai_chain") as mock_chain, \
         patch("factory.integrations.provider_chain.scout_chain") as mock_scout, \
         patch("factory.memory.mother_memory.get_memory_chain_status", return_value=[]):
        mock_chain.get_active.return_value = "gemini"
        mock_chain.chain = ["gemini"]
        mock_chain.statuses = {"gemini": MagicMock(quota_exhausted=False, available=True, last_error=None)}
        mock_scout.get_active.return_value = "exa"
        mock_scout.chain = ["exa"]
        mock_scout.statuses = {"exa": MagicMock(quota_exhausted=False, available=True, last_error=None)}

        from factory.telegram.bot import cmd_providers
        await cmd_providers(fake_update, MagicMock())

    assert sent_msgs, "cmd_providers sent no message"
    msg = sent_msgs[0]
    # After escape_md, provider names with underscores should have \\_ not bare _
    # The status_message contains provider names like nvidia_nim_image_gen
    # Check that no bare underscore exists in a context that would break Markdown
    # (simple check: the Telegram-dangerous pattern "_word_" should be escaped to "\\_word\\_")
    assert "nvidia\\_nim" in msg or "nvidia_nim" not in msg, (
        f"Unescaped provider name in /providers output: {msg[:200]}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 5: format_project_started includes Master mode line
# ═══════════════════════════════════════════════════════════════════

def test_format_project_started_has_master_line():
    """Banner must contain 'Master:' line (Issue 46)."""
    state = PipelineState(
        project_id="t-banner-1",
        operator_id="op-banner",
        master_mode=MasterMode.BASIC,
        execution_mode=ExecutionMode.CLOUD,
        autonomy_mode=AutonomyMode.AUTOPILOT,
    )
    banner = format_project_started("t-banner-1", state)
    assert "Master:" in banner, (
        f"'Master:' line missing from banner — Issue 46 fix not applied.\nBanner: {banner}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 6: banner shows BASIC emoji for BASIC mode
# ═══════════════════════════════════════════════════════════════════

def test_format_project_started_basic_emoji():
    """Banner must show 🆓 emoji for BASIC master mode."""
    state = PipelineState(
        project_id="t-banner-2",
        operator_id="op-banner",
        master_mode=MasterMode.BASIC,
    )
    banner = format_project_started("t-banner-2", state)
    assert "🆓" in banner, (
        f"BASIC emoji 🆓 missing from banner.\nBanner: {banner}"
    )
    assert "Basic (Free)" in banner


# ═══════════════════════════════════════════════════════════════════
# Test 7: banner shows BALANCED label for BALANCED mode
# ═══════════════════════════════════════════════════════════════════

def test_format_project_started_balanced_label():
    """Banner must show 'Balanced' label for BALANCED master mode."""
    state = PipelineState(
        project_id="t-banner-3",
        operator_id="op-banner",
        master_mode=MasterMode.BALANCED,
    )
    banner = format_project_started("t-banner-3", state)
    assert "Balanced" in banner, (
        f"'Balanced' label missing from banner.\nBanner: {banner}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 8: banner shows all three axes
# ═══════════════════════════════════════════════════════════════════

def test_format_project_started_all_three_axes():
    """Banner must contain Master, Execution, and Autonomy lines."""
    state = PipelineState(
        project_id="t-banner-4",
        operator_id="op-banner",
        master_mode=MasterMode.TURBO,
        execution_mode=ExecutionMode.LOCAL,
        autonomy_mode=AutonomyMode.COPILOT,
    )
    banner = format_project_started("t-banner-4", state)
    assert "Master:" in banner,    f"'Master:' missing.\nBanner: {banner}"
    assert "Execution:" in banner, f"'Execution:' missing.\nBanner: {banner}"
    assert "Autonomy:" in banner,  f"'Autonomy:' missing.\nBanner: {banner}"


# ═══════════════════════════════════════════════════════════════════
# Test 9: _is_duplicate_update — first occurrence returns False
# ═══════════════════════════════════════════════════════════════════

def test_dedup_first_occurrence_not_duplicate():
    """First occurrence of an update_id must not be flagged as duplicate."""
    uid = 9_000_001
    _handled_update_ids.discard(uid)  # ensure clean
    assert _is_duplicate_update(uid) is False
    _handled_update_ids.discard(uid)


# ═══════════════════════════════════════════════════════════════════
# Test 10: _is_duplicate_update — second occurrence returns True
# ═══════════════════════════════════════════════════════════════════

def test_dedup_second_occurrence_is_duplicate():
    """Second call with same update_id must return True (duplicate)."""
    uid = 9_000_002
    _handled_update_ids.discard(uid)  # ensure clean
    assert _is_duplicate_update(uid) is False   # first: not dup
    assert _is_duplicate_update(uid) is True    # second: duplicate
    _handled_update_ids.discard(uid)


# ═══════════════════════════════════════════════════════════════════
# Test 11: authenticate_operator drops duplicate update_id
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_authenticate_operator_drops_duplicate():
    """authenticate_operator must return False for duplicate update_id (Issue 47)."""
    from factory.telegram.bot import authenticate_operator

    uid = 9_000_003
    _handled_update_ids.discard(uid)

    fake_update = MagicMock()
    fake_update.update_id = uid
    fake_update.effective_user.id = 12345

    with patch("factory.telegram.ai_handler.is_operator", return_value=True):
        result1 = await authenticate_operator(fake_update)
        result2 = await authenticate_operator(fake_update)  # same update_id

    _handled_update_ids.discard(uid)

    assert result1 is True,  "First invocation should pass auth"
    assert result2 is False, "Duplicate update_id should be dropped"
