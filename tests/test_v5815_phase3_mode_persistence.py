"""v5.8.15 Phase 3 (Issue 51) — mode write-path integrity.

Live evidence: `/execution_mode local` reported "OK" but every subsequent
read showed CLOUD. Root cause: Supabase writes failed silently (logged
warning, swallowed exception) and there was no local fallback.

These tests verify:
  1. set_operator_preference writes to SQLite even when Supabase is down.
  2. load_operator_preferences reads from SQLite when Supabase is
     unavailable AND memory cache is cold.
  3. ModeStore.get_effective_execution_mode honors scope precedence
     (project state > operator pref > default).
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def isolated_prefs(tmp_path, monkeypatch):
    """Redirect the SQLite prefs file to a tmp path and reset memory cache."""
    from factory.telegram import decisions as dmod

    sqlite_file = tmp_path / ".ops_prefs.sqlite3"
    monkeypatch.setattr(
        dmod, "_prefs_sqlite_path", lambda: sqlite_file, raising=True,
    )
    # Drop cache and any existing SQLite state
    dmod._operator_prefs.clear()
    if sqlite_file.exists():
        sqlite_file.unlink()
    yield dmod
    dmod._operator_prefs.clear()


@pytest.mark.asyncio
async def test_pref_survives_supabase_outage(isolated_prefs, monkeypatch):
    """set_operator_preference must write to SQLite when Supabase fails."""
    dmod = isolated_prefs

    async def _boom(*a, **kw):
        raise RuntimeError("supabase is down")

    # Force the Supabase write to explode — SQLite must catch the write.
    monkeypatch.setattr(
        "factory.integrations.supabase.set_operator_state_db",
        _boom,
        raising=False,
    )

    await dmod.set_operator_preference("op77", "execution_mode", "local")

    # Now simulate process restart: clear in-memory cache.
    dmod._operator_prefs.clear()

    # Make Supabase read also fail, so load has to reach SQLite.
    async def _boom_read(*a, **kw):
        raise RuntimeError("supabase still down")

    monkeypatch.setattr(
        "factory.integrations.supabase.get_operator_state_db",
        _boom_read,
        raising=False,
    )

    prefs = await dmod.load_operator_preferences("op77")
    assert prefs["execution_mode"] == "local", (
        "SQLite fallback did not restore the execution_mode preference "
        "after a Supabase outage — this is the Issue 51 ghost."
    )


@pytest.mark.asyncio
async def test_get_effective_execution_mode_scope_precedence(
    isolated_prefs, monkeypatch,
):
    """Scope order: PipelineState > operator pref > default."""
    from factory.core.state import PipelineState, ExecutionMode
    from factory.telegram.mode_store import ModeStore

    # No Supabase available for this test; let it fall through silently.
    async def _none(*a, **kw):
        return None

    monkeypatch.setattr(
        "factory.integrations.supabase.get_operator_state_db",
        _none,
        raising=False,
    )
    async def _ok(*a, **kw):
        return None
    monkeypatch.setattr(
        "factory.integrations.supabase.set_operator_state_db",
        _ok,
        raising=False,
    )

    # Case 1: no state, no pref → CLOUD default
    em = await ModeStore.get_effective_execution_mode("op88", None)
    assert em == ExecutionMode.CLOUD

    # Case 2: operator pref set, no state → pref wins
    dmod = isolated_prefs
    await dmod.set_operator_preference("op88", "execution_mode", "local")
    dmod._operator_prefs.clear()  # force reload
    em = await ModeStore.get_effective_execution_mode("op88", None)
    assert em == ExecutionMode.LOCAL, em

    # Case 3: state present → state wins even if pref differs
    state = PipelineState(project_id="p1", operator_id="op88")
    state.execution_mode = ExecutionMode.HYBRID
    em = await ModeStore.get_effective_execution_mode("op88", state)
    assert em == ExecutionMode.HYBRID


@pytest.mark.asyncio
async def test_pref_write_logs_structured_line(
    isolated_prefs, monkeypatch, caplog,
):
    """Every pref write emits a [pref-write] forensic line."""
    import logging

    dmod = isolated_prefs

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(
        "factory.integrations.supabase.set_operator_state_db",
        _noop,
        raising=False,
    )

    caplog.set_level(logging.INFO, logger="factory.telegram.decisions")
    await dmod.set_operator_preference("op99", "execution_mode", "hybrid")

    write_logs = [r for r in caplog.records if "[pref-write]" in r.message]
    assert write_logs, "expected a structured [pref-write] log line"
    assert "execution_mode" in write_logs[-1].message
    assert "hybrid" in write_logs[-1].message
