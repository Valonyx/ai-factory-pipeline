"""v5.8.15 Phase 5 (Issues 53 / 55 / 56) — rendering, cost honesty, ID leak.

Issue 53 — iOS tofu box: /quota used U+2593 (▓) for the empty-segment glyph,
which renders as a "tofu" (unknown glyph) on iOS Telegram. Switched to
U+2588 (█) for filled and U+2591 (░) for empty, matching /cost.

Issue 55 — /cost in BASIC showed paid phase ceilings (e.g. codegen_engineer
$25) even though BASIC is free-chain only. /cost must be mode-aware so the
ceiling is honestly reported as $0 in BASIC.

Issue 56 — Pre-name project display: early onboarding messages leaked the
internal `Project <hex>` id to the user. project_display_name must always
fall back to the literal string "your new project".
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ── Issue 53 — iOS glyph ────────────────────────────────────────────────

def test_quota_usage_summary_uses_safe_glyphs():
    """/quota bars must use U+2588/U+2591, not U+2593."""
    from factory.core.quota_tracker import QuotaTracker

    tracker = QuotaTracker()
    # Drive usage up to ~50% for one provider so we get mixed bar glyphs.
    s = tracker._get_state("gemini")
    s.calls = (s.quota_calls // 2) if s.quota_calls else 50
    lines = tracker.usage_summary()
    blob = "\n".join(lines)
    assert "\u2593" not in blob, "Tofu glyph U+2593 leaked into /quota output"
    # At least one line must use the safe glyphs.
    assert "\u2588" in blob or "\u2591" in blob


# ── Issue 56 — Pre-name project display ─────────────────────────────────

def test_project_display_name_never_leaks_hex_id():
    from factory.telegram.messages import project_display_name

    # Bare dict with only a hex id — must NOT appear in the output.
    d = {"project_id": "proj_deadbeefcafe0123"}
    out = project_display_name(d)
    assert "deadbeef" not in out
    assert "proj_" not in out
    assert out == "your new project"


def test_project_display_name_none_returns_fallback():
    from factory.telegram.messages import project_display_name

    assert project_display_name(None) == "your new project"


def test_project_display_name_prefers_intake_app_name():
    from factory.telegram.messages import project_display_name

    d = {"intake": {"app_name": "Pulsey"}, "project_id": "proj_abc"}
    assert project_display_name(d) == "Pulsey"


# ── Issue 55 — /cost mode-aware ─────────────────────────────────────────

def _make_state():
    from factory.core.state import PipelineState
    return PipelineState(project_id="p1", operator_id="op1")


def test_format_cost_message_basic_hides_paid_ceilings():
    from factory.telegram.messages import format_cost_message

    state = _make_state()
    msg = format_cost_message(state, master_mode="BASIC")
    # Header must announce BASIC and explain paid ceilings don't apply.
    assert "BASIC" in msg
    assert "free-chain only" in msg or "free-only" in msg.lower()
    # No $25.00 / $10.00 / $8.00 ceilings in BASIC.
    assert "$25.00" not in msg
    assert "$10.00" not in msg
    assert "$8.00" not in msg
    # Every phase row should carry the BASIC free-only annotation.
    assert msg.count("BASIC free-only") >= 5


def test_format_cost_message_balanced_shows_paid_ceilings():
    from factory.telegram.messages import format_cost_message

    state = _make_state()
    msg = format_cost_message(state, master_mode="BALANCED")
    # Paid ceilings must be shown in BALANCED.
    assert "$25.00" in msg  # codegen_engineer
    assert "$10.00" in msg  # design_engine
    assert "BASIC free-only" not in msg


def test_format_cost_message_no_mode_preserves_legacy_behavior():
    from factory.telegram.messages import format_cost_message

    state = _make_state()
    msg = format_cost_message(state)
    # Ceilings still present; no mode annotation.
    assert "$25.00" in msg
    assert "BASIC free-only" not in msg
    assert "mode:" not in msg


# ── Markdown safety — phase names must not get italicised ───────────────

def test_format_cost_message_phase_names_wrapped_in_backticks():
    """Underscore phase names (scout_research, strategist_planning, etc.)
    must be wrapped in backticks so parse_mode='Markdown' doesn't render
    them as italics and mangle the /cost output."""
    from factory.telegram.messages import format_cost_message

    state = _make_state()
    msg = format_cost_message(state, master_mode="BALANCED")
    assert "`scout_research`" in msg
    assert "`strategist_planning`" in msg
    assert "`codegen_engineer`" in msg
