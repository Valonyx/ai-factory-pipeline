"""v5.8.16 Phase 3 — run-stability regressions.

Pins four fixes that were false-cancelling live pipelines and
misrouting project defaults:

- Issue 61 — update_project_state must ALWAYS mirror into
  _active_projects_fallback (not only on Supabase failure), otherwise the
  orphan-task sweeper kills the live pipeline on any transient write
  failure.
- Issue 62 — master-mode default on /new falls back to "basic" (free
  tier), not "balanced".
- Issue 63 — handle_message must drop messages older than bot startup
  minus the grace window (stale queued-message replay guard).
- Issue 64 — /exec_local /exec_cloud /exec_hybrid shortcut commands are
  registered on the bot.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BOT_SRC = Path(__file__).resolve().parents[1] / "factory/telegram/bot.py"
MODE_STORE_SRC = Path(__file__).resolve().parents[1] / "factory/telegram/mode_store.py"
S0_SRC = Path(__file__).resolve().parents[1] / "factory/pipeline/s0_intake.py"


def test_issue_61_update_project_state_always_mirrors() -> None:
    text = BOT_SRC.read_text()
    # Find the update_project_state body (stop at next top-level def)
    m = re.search(
        r"async def update_project_state\(state: PipelineState\) -> None:(.*?)\nasync def ",
        text,
        re.S,
    )
    assert m, "update_project_state not found"
    body = m.group(1)
    # Mirror write must NOT be gated behind `if not success` / `else`
    assert "_active_projects_fallback[state.operator_id]" in body
    # Guard: the mirror assignment must appear BEFORE the success branch
    mirror_idx = body.find("_active_projects_fallback[state.operator_id]")
    success_idx = body.find("success = await _sb_upsert_active")
    assert mirror_idx < success_idx, (
        "Mirror must be populated before the Supabase call so transient "
        "write failures can't starve the sweeper of truth. "
        "See v5.8.16 Issue 61 / PIPELINE_CANCELLED bug."
    )


def test_issue_61_sweeper_requires_supabase_confirmation() -> None:
    text = BOT_SRC.read_text()
    # Sweeper must consult Supabase before cancelling
    assert "get_pipeline_state(project_id)" in text, (
        "Sweeper must double-check Supabase before killing — see Issue 61."
    )
    # Sweeper must require at least 2 consecutive misses
    assert "suspect_count" in text


def test_issue_62_master_mode_default_is_basic() -> None:
    text = BOT_SRC.read_text()
    # _start_project default must be basic, not balanced
    assert 'prefs.get("master_mode", "basic")' in text
    assert 'prefs.get("master_mode", "balanced")' not in text, (
        "v5.8.16 Issue 62: default master mode is BASIC (free tier), "
        "never BALANCED — the user may have zero budget."
    )
    mode_store = MODE_STORE_SRC.read_text()
    assert 'prefs.get("master_mode", "basic")' in mode_store
    assert "return MasterMode.BASIC" in mode_store


def test_issue_63_handle_message_drops_stale() -> None:
    text = BOT_SRC.read_text()
    assert "_BOT_STARTED_AT" in text
    assert "_STALE_MESSAGE_GRACE_SECONDS" in text
    assert "stale-drop" in text, "Stale-drop log breadcrumb is missing"


def test_issue_64_exec_shortcut_commands_registered() -> None:
    text = BOT_SRC.read_text()
    for cmd in ("exec_local", "exec_cloud", "exec_hybrid"):
        assert f'CommandHandler("{cmd}"' in text, f"/{cmd} not registered"
        assert f'BotCommand("{cmd}"' in text, f"/{cmd} missing from BotFather menu"


def test_issue_65_logo_flow_defaults_to_copilot() -> None:
    text = S0_SRC.read_text()
    # The routing function must send users through copilot UNLESS they
    # explicitly opt into autopilot via project_metadata.
    m = re.search(r"async def _logo_flow\(.*?\nasync def ", text, re.S)
    assert m, "_logo_flow not found"
    body = m.group(0)
    assert 'project_metadata.get("logo_autopilot")' in body
    assert "_logo_flow_copilot" in body
