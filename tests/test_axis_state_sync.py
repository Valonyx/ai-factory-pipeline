"""Phase 1 FIX-MODE-05 — axis state sync invariants.

Verifies the post-fix invariants behind Issues #1, #2, #9:

  1. set_<axis>_mode → load_operator_preferences returns the new value
     (round-trip consistency for master / execution / transport axes).
  2. /start welcome message renders the live three-axis state from
     stored prefs, not a hardcoded "Defaults: ..." line.
  3. Two operators do not leak state into each other's preferences.
  4. The Telegram reply path awaits persistence before replying — the
     handler does NOT call reply_text before set_operator_preference
     resolves.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_prefs(tmp_path, monkeypatch):
    """Redirect the SQLite prefs file to a tmp path and reset memory cache.

    Also stub the Supabase fan-out so tests don't hit the network and
    don't pollute global cache between tests.
    """
    from factory.telegram import decisions as dmod

    sqlite_file = tmp_path / ".ops_prefs.sqlite3"
    monkeypatch.setattr(
        dmod, "_prefs_sqlite_path", lambda: sqlite_file, raising=True,
    )
    dmod._operator_prefs.clear()
    if sqlite_file.exists():
        sqlite_file.unlink()

    # Stub Supabase calls — tests own their persistence boundary.
    async def _no_supabase_get(*a, **kw):
        return None

    async def _no_supabase_set(*a, **kw):
        return True

    import factory.integrations.supabase as sb_mod
    monkeypatch.setattr(sb_mod, "get_operator_state_db", _no_supabase_get, raising=False)
    monkeypatch.setattr(sb_mod, "set_operator_state_db", _no_supabase_set, raising=False)

    yield dmod
    dmod._operator_prefs.clear()


# ──────────────────────────────────────────────────────────────────────
# 1–3: set → read round-trip per axis
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_master_mode_then_read_returns_new_value(isolated_prefs):
    dmod = isolated_prefs
    user_id = "111"

    await dmod.set_operator_preference(user_id, "master_mode", "balanced")

    # Drop cache so the read goes through the migration path —
    # this is the path that previously reverted "balanced" → "basic".
    dmod._operator_prefs.clear()

    prefs = await dmod.load_operator_preferences(user_id)
    assert prefs["master_mode"] == "balanced", (
        "Saved master_mode must survive cache eviction + reload "
        "(FIX-MODE-01 regression guard)."
    )


@pytest.mark.asyncio
async def test_set_execution_mode_then_read_returns_new_value(isolated_prefs):
    dmod = isolated_prefs
    user_id = "222"

    await dmod.set_operator_preference(user_id, "execution_mode", "cloud")
    dmod._operator_prefs.clear()

    prefs = await dmod.load_operator_preferences(user_id)
    assert prefs["execution_mode"] == "cloud", (
        "Saved execution_mode must survive reload (no silent revert)."
    )


@pytest.mark.asyncio
async def test_set_transport_mode_then_read_returns_new_value(isolated_prefs):
    dmod = isolated_prefs
    user_id = "333"

    await dmod.set_operator_preference(user_id, "transport_mode", "webhook")
    dmod._operator_prefs.clear()

    prefs = await dmod.load_operator_preferences(user_id)
    assert prefs["transport_mode"] == "webhook"


# ──────────────────────────────────────────────────────────────────────
# 4–5: /start welcome message renders live state
# ──────────────────────────────────────────────────────────────────────


def test_start_greeting_renders_active_project_state():
    """When prefs and an active project are passed, render their values."""
    from factory.telegram.messages import format_welcome_message

    prefs = {
        "master_mode": "turbo",
        "execution_mode": "cloud",
        "transport_mode": "webhook",
    }
    msg = format_welcome_message("Alex", prefs=prefs, has_active_project=True)

    assert "active project" in msg
    assert "Turbo" in msg
    assert "Cloud" in msg
    assert "Webhook" in msg
    # Must NOT show stale defaults.
    assert "Basic (free only, $0)" not in msg
    assert "Polling" not in msg


def test_start_greeting_with_no_active_project_renders_defaults_with_label():
    """When prefs is None, label the line as defaults rather than lying."""
    from factory.telegram.messages import format_welcome_message

    msg = format_welcome_message("Alex")
    assert "defaults — no saved preferences" in msg
    # Default labels still render so the user knows the starting state.
    assert "Basic (free only, $0)" in msg


# ──────────────────────────────────────────────────────────────────────
# 6: cross-operator isolation
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_then_read_across_two_projects_does_not_leak(isolated_prefs):
    """Two operators must not see each other's mode preferences."""
    dmod = isolated_prefs

    await dmod.set_operator_preference("op-A", "master_mode", "turbo")
    await dmod.set_operator_preference("op-B", "master_mode", "balanced")

    dmod._operator_prefs.clear()  # force reload from SQLite

    a = await dmod.load_operator_preferences("op-A")
    b = await dmod.load_operator_preferences("op-B")

    assert a["master_mode"] == "turbo"
    assert b["master_mode"] == "balanced"


# ──────────────────────────────────────────────────────────────────────
# 7: write-through-await — handler awaits persistence before replying
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_writer_awaits_persistence_before_replying(isolated_prefs):
    """_set_master_mode must call set_operator_preference BEFORE reply_text.

    Regression guard against the pre-fix pattern where reply_text fired
    first, masking failed saves with a "Saving..." ghost confirmation.
    """
    from factory.telegram import bot as bot_mod

    call_order: list[str] = []

    async def _record_set(user_id, key, value):
        call_order.append(f"set:{key}={value}")

    async def _record_load(user_id):
        call_order.append("load")
        return {
            "master_mode": "balanced",
            "execution_mode": "local",
            "transport_mode": "polling",
            "autonomy_mode": "autopilot",
        }

    update = MagicMock()
    update.message = MagicMock()
    reply_mock = AsyncMock(side_effect=lambda *a, **kw: call_order.append("reply"))
    update.message.reply_text = reply_mock

    with patch.object(bot_mod, "set_operator_preference", _record_set), \
         patch.object(bot_mod, "load_operator_preferences", _record_load):
        await bot_mod._set_master_mode(update, "999", "balanced")

    # set must precede reply — read-back load is also expected before reply.
    assert call_order[0] == "set:master_mode=balanced", (
        f"set_operator_preference must run first; got {call_order!r}"
    )
    assert call_order[-1] == "reply", (
        f"reply_text must be the last step; got {call_order!r}"
    )
    assert "load" in call_order, (
        f"load_operator_preferences must run between save and reply; got {call_order!r}"
    )
    reply_mock.assert_awaited_once()
    body = reply_mock.await_args.args[0]
    assert "confirmed" in body.lower(), f"Reply body must surface confirmed state: {body!r}"
