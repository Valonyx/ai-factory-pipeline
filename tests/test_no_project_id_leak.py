"""
Issue 15 guard — no raw proj_<hex> ids in user-facing Telegram strings.

Two checks:
  1. A regex-lint over factory/telegram/**/*.py rejects f-strings passed
     to user-facing APIs (reply_text, send_message, edit_message_text,
     answer_callback_query, InlineKeyboardButton) that interpolate a
     project_id variable into the rendered text.
  2. An integration check builds fake state + fake active_project dict
     and asserts the formatters in messages.py return the app_name and
     NOT the raw project id.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from factory.core.state import PipelineState
from factory.telegram.messages import (
    format_cost_message,
    format_project_started,
    format_status_message,
    project_display_name,
)


TELEGRAM_ROOT = Path(__file__).resolve().parent.parent / "factory" / "telegram"

# User-facing call sinks — any f-string passed to these that interpolates
# `{project_id}` / `{proj_id}` / `{state.project_id}` is a leak.
_USER_FACING_CALLS = (
    "reply_text",
    "send_telegram_message",
    "send_message",
    "answer_callback_query",
    "edit_message_text",
    "InlineKeyboardButton",
)

# Files exempt from the lint — debug / airlock / log-oriented.
_ALLOWLIST: set[str] = {
    "airlock.py",      # binary delivery filenames include project_id (non-user-facing captions only)
    "notifications.py",# internal log formatting; caller-side rendering is already audited
}

# Matches a user-facing call whose first argument (or subsequent string
# arg) contains a Python f-string interpolating project_id-like variables.
_LEAK_RE = re.compile(
    r"(?:" + "|".join(_USER_FACING_CALLS) + r")\s*\([^)]*"
    r"f[\"'][^\"']*\{(?:proj_id|project_id|state\.project_id|active\[['\"]project_id['\"]\])",
    re.DOTALL,
)


def test_no_project_id_interpolated_into_user_facing_calls():
    offenders: list[tuple[str, int, str]] = []
    for py in TELEGRAM_ROOT.rglob("*.py"):
        if py.name in _ALLOWLIST:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Walk line-by-line so the matcher doesn't chew across large regions;
        # the call + f-string usually appear on the same or adjacent lines.
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            # Join up to 3 lines to catch wrapped calls.
            window = "\n".join(lines[i - 1 : min(len(lines), i + 2)])
            if _LEAK_RE.search(window):
                offenders.append((py.name, i, line.strip()[:120]))

    # De-duplicate by file+line — the 3-line window causes repeats.
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int, str]] = []
    for f, ln, t in offenders:
        if (f, ln) in seen:
            continue
        seen.add((f, ln))
        unique.append((f, ln, t))

    assert not unique, (
        "User-facing Telegram calls must render the app name, not proj_<hex>:\n  "
        + "\n  ".join(f"{f}:{ln}: {t}" for f, ln, t in unique)
    )


# ── project_display_name helper ───────────────────────────────────────

def test_display_name_prefers_intake_app_name():
    s = PipelineState(project_id="proj_58856403", operator_id="op")
    s.intake = {"app_name": "Pulsey AI"}
    assert project_display_name(s) == "Pulsey AI"


def test_display_name_prefers_metadata_app_name():
    s = PipelineState(project_id="proj_58856403", operator_id="op")
    s.project_metadata["app_name"] = "Acme Todo"
    assert project_display_name(s) == "Acme Todo"


def test_display_name_falls_back_to_idea_name():
    s = PipelineState(project_id="proj_58856403", operator_id="op")
    s.idea_name = "Fallback App"
    assert project_display_name(s) == "Fallback App"


def test_display_name_humanizes_id_only_as_last_resort():
    # v5.8.15 Issue 56 — pre-name projects must fall back to the literal
    # "your new project" string; never leak a "Project <hex>" form either.
    s = PipelineState(project_id="proj_58856403", operator_id="op")
    out = project_display_name(s)
    assert "proj_" not in out
    assert "58856403" not in out
    assert out == "your new project"


def test_display_name_on_dict_row():
    row = {"project_id": "proj_58856403", "app_name": "Pulsey AI"}
    assert project_display_name(row) == "Pulsey AI"


def test_display_name_on_empty_dict_never_emits_raw_id():
    row = {"project_id": "proj_abcdef01"}
    out = project_display_name(row)
    assert "proj_" not in out


# ── Integration: message formatters render app_name, not id ───────────

def _state_with_name(name: str = "Pulsey AI", pid: str = "proj_58856403") -> PipelineState:
    s = PipelineState(project_id=pid, operator_id="op")
    s.intake = {"app_name": name}
    s.project_metadata["app_name"] = name
    return s


def test_format_status_message_uses_app_name():
    s = _state_with_name()
    out = format_status_message(s)
    assert "Pulsey AI" in out
    assert "proj_58856403" not in out


def test_format_cost_message_uses_app_name():
    s = _state_with_name()
    out = format_cost_message(s)
    assert "Pulsey AI" in out
    assert "proj_58856403" not in out


def test_format_project_started_uses_app_name():
    s = _state_with_name()
    out = format_project_started(s.project_id, s)
    assert "Pulsey AI" in out
    assert "proj_58856403" not in out
