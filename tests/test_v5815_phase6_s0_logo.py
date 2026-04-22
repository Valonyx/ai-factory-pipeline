"""v5.8.15 Phase 6 (Issues 57 / 58) — S0 FSM engagement + logo engine.

Live evidence (per PHASE_0_REALITY_REPORT_V15 §11):
  - `/new` appeared to fall through to a single-paste flow, bypassing the
    multi-turn FSM (name → platforms → market → logo → summary).
  - `🎨 Logo: auto` rendered as a 3-word line; no 3-variant media album was
    received; only a single `logo.png` landed on disk.

These tests pin the contract so regressions are loud in CI:

Issue 57:
  - cmd_new_project with inlined description routes through _ask_app_name
    (always engages the FSM; never skips straight to _start_project).
  - _ask_app_name with no extractable name sets awaiting_app_name state.

Issue 58:
  - _save_logo_to_disk honours variant_index (logo_01.png, logo_02.png, ...).
  - _logo_flow_auto saves ALL variant bytes to disk plus the primary
    logo.png, and returns logo_variant_paths in the asset dict.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


# ─── Issue 57: S0 FSM engagement ───────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_new_with_inline_description_routes_to_ask_app_name():
    """/new <description> must engage the FSM via _ask_app_name, never skip
    straight into _start_project (which would trigger a single-paste run)."""
    from factory.telegram import bot as _bot

    update = MagicMock()
    update.effective_user.id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = ["a", "fitness", "app", "for", "runners"]

    with patch.object(_bot, "get_active_project", new=AsyncMock(return_value=None)), \
         patch.object(_bot, "_ask_app_name", new=AsyncMock()) as ask_mock, \
         patch.object(_bot, "_start_project", new=AsyncMock()) as start_mock, \
         patch.object(_bot, "require_auth", lambda f: f):
        # cmd_new_project is already decorated, call the unwrapped handler
        await _bot.cmd_new_project.__wrapped__(update, context) \
            if hasattr(_bot.cmd_new_project, "__wrapped__") \
            else await _bot.cmd_new_project(update, context)

    assert ask_mock.await_count == 1, "FSM must engage via _ask_app_name"
    assert start_mock.await_count == 0, (
        "cmd_new_project must NOT skip past the FSM into _start_project"
    )


@pytest.mark.asyncio
async def test_ask_app_name_without_extractable_name_sets_awaiting_state():
    from factory.telegram import bot as _bot

    update = MagicMock()
    update.message.reply_text = AsyncMock()

    with patch.object(_bot, "set_operator_state", new=AsyncMock()) as set_state, \
         patch.object(_bot, "_onboarding_ask_platforms", new=AsyncMock()) as ask_platforms:
        await _bot._ask_app_name(update, "42", "a generic todo list application")

    # No auto-extraction → must set awaiting_app_name and NOT jump to platforms.
    assert set_state.await_count == 1
    args, kwargs = set_state.call_args
    assert args[1] == "awaiting_app_name"
    assert ask_platforms.await_count == 0


@pytest.mark.asyncio
async def test_ask_app_name_with_explicit_name_skips_prompt():
    """If description contains `called "Pulsey"`, we auto-extract and go to
    platforms — no awaiting_app_name state."""
    from factory.telegram import bot as _bot

    update = MagicMock()
    update.message.reply_text = AsyncMock()

    with patch.object(_bot, "set_operator_state", new=AsyncMock()) as set_state, \
         patch.object(_bot, "_onboarding_ask_platforms", new=AsyncMock()) as ask_platforms:
        await _bot._ask_app_name(update, "42", 'A fitness app called "Pulsey" for runners.')

    assert ask_platforms.await_count == 1
    # Extracted name must be passed through
    args, _ = ask_platforms.call_args
    assert "Pulsey" in args, f"Expected 'Pulsey' in {args}"
    assert set_state.await_count == 0


# ─── Issue 58: Logo engine — 3 variants to disk ────────────────────────

def test_save_logo_to_disk_with_variant_index_writes_numbered_file(tmp_path, monkeypatch):
    """variant_index=1 → logo_01.png; variant_index=None → logo.png."""
    from factory.pipeline import s0_intake

    monkeypatch.setattr(
        "factory.core.execution._get_project_workspace",
        lambda project_id, app_name: str(tmp_path),
    )

    # Primary (no index) → logo.png
    p0 = s0_intake._save_logo_to_disk(b"\x89PNG\r\n" + b"a" * 100, "proj_x", "Test")
    assert p0 and p0.endswith("logo.png")
    assert os.path.exists(p0)

    # Numbered variant → logo_02.png
    p2 = s0_intake._save_logo_to_disk(
        b"\x89PNG\r\n" + b"b" * 100, "proj_x", "Test", variant_index=2,
    )
    assert p2 and p2.endswith("logo_02.png")
    assert os.path.exists(p2)
    # Files must be distinct
    assert p0 != p2


@pytest.mark.asyncio
async def test_logo_flow_auto_saves_all_variants_to_disk(tmp_path, monkeypatch):
    """All 3 successful variants must land on disk as logo_01/02/03.png plus
    the primary logo.png, and the returned asset dict must include
    logo_variant_paths for observability."""
    from factory.pipeline import s0_intake
    from factory.core.state import PipelineState

    state = PipelineState(project_id="proj_logo_disk", operator_id="12345")
    state.idea_name = "DiskApp"
    requirements = {"app_name": "DiskApp", "app_description": "write to disk"}

    # Patch workspace so variants write into tmp_path.
    monkeypatch.setattr(
        "factory.core.execution._get_project_workspace",
        lambda project_id, app_name: str(tmp_path),
    )

    fake_png = b"\x89PNG\r\n" + b"z" * 200

    with patch.object(s0_intake, "generate_image",
                      new=AsyncMock(return_value=fake_png)), \
         patch.object(s0_intake, "build_logo_prompt", return_value="DiskApp logo"), \
         patch.object(s0_intake, "get_bot", return_value=None):
        asset = await s0_intake._logo_flow_auto(state, requirements)

    assert asset is not None
    assert asset["logo_variant_count"] == 3
    variant_paths = asset.get("logo_variant_paths") or []
    assert len(variant_paths) == 3, (
        f"Expected 3 variant paths, got {variant_paths}"
    )
    # Primary logo.png must exist
    assert (tmp_path / "brand" / "logo.png").exists()
    # Numbered variants must exist
    assert (tmp_path / "brand" / "logo_01.png").exists()
    assert (tmp_path / "brand" / "logo_02.png").exists()
    assert (tmp_path / "brand" / "logo_03.png").exists()
