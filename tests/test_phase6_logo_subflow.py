"""
v5.8.14 Phase 6 — Real Logo Sub-Flow Tests (Issue 40)

Issue 40: _logo_flow_auto must generate 3 logo variants and deliver them via
Telegram InputMediaPhoto album instead of a single photo.

Tests:
  1.  generate_image called 3 times (once per variant)
  2.  With ≥2 variants, send_media_group (album) is called, not send_photo
  3.  Album media list has length equal to number of successful variants
  4.  With only 1 variant (2 fail), falls back to send_photo
  5.  With 0 variants (all fail), returns None without sending anything
  6.  Return value includes logo_variant_count field
  7.  Return value includes logo_path field (primary variant saved to disk)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from factory.core.state import PipelineState, AutonomyMode


# ─── helper ───────────────────────────────────────────────────────────────────

def _make_state(project_id: str = "proj_logo_test") -> PipelineState:
    state = PipelineState(project_id=project_id, operator_id="12345")
    state.idea_name = "TestApp"
    return state


_FAKE_LOGO_BYTES = b"\x89PNG\r\n" + b"x" * 4096  # fake but > 1 KB


# ═══════════════════════════════════════════════════════════════════
# Test 1: generate_image called 3 times (one per variant)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logo_flow_auto_calls_generate_three_times():
    """_logo_flow_auto must call generate_image 3 times for the 3 style variants."""
    from factory.pipeline.s0_intake import _logo_flow_auto

    state = _make_state("proj_logo_t1")
    requirements = {"app_name": "TestApp", "app_description": "A test app"}

    with patch("factory.pipeline.s0_intake.generate_image",
               new_callable=AsyncMock, return_value=_FAKE_LOGO_BYTES) as mock_gen, \
         patch("factory.pipeline.s0_intake.build_logo_prompt", return_value="TestApp logo"), \
         patch("factory.pipeline.s0_intake.get_bot", return_value=None), \
         patch("factory.pipeline.s0_intake._save_logo_to_disk", return_value="/tmp/logo.png"):
        # Rewrite the import path used inside the function
        with patch("factory.integrations.image_gen.generate_image",
                   new_callable=AsyncMock, return_value=_FAKE_LOGO_BYTES):
            result = await _logo_flow_auto(state, requirements)

    # 3 concurrent gather calls
    assert mock_gen.call_count == 3, (
        f"Expected 3 generate_image calls, got {mock_gen.call_count}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 2: With ≥2 variants, send_media_group is called
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logo_flow_auto_sends_album_for_multiple_variants():
    """With ≥2 successful variants, must call send_media_group (album), not send_photo."""
    from factory.pipeline.s0_intake import _logo_flow_auto

    state = _make_state("proj_logo_t2")
    requirements = {"app_name": "TestApp2", "app_description": "Fitness tracker"}

    mock_bot = MagicMock()
    mock_bot.send_media_group = AsyncMock(return_value=None)
    mock_bot.send_photo = AsyncMock(return_value=None)

    with patch("factory.pipeline.s0_intake.generate_image",
               new_callable=AsyncMock, return_value=_FAKE_LOGO_BYTES) as mock_gen, \
         patch("factory.pipeline.s0_intake.build_logo_prompt", return_value="TestApp2 logo"), \
         patch("factory.pipeline.s0_intake.get_bot", return_value=mock_bot), \
         patch("factory.pipeline.s0_intake._save_logo_to_disk", return_value="/tmp/logo2.png"):
        result = await _logo_flow_auto(state, requirements)

    mock_bot.send_media_group.assert_called_once()
    mock_bot.send_photo.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Test 3: Album media list length equals number of successful variants
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logo_flow_auto_album_has_correct_length():
    """Album sent to Telegram must have an entry for each successful variant."""
    from factory.pipeline.s0_intake import _logo_flow_auto

    state = _make_state("proj_logo_t3")
    requirements = {"app_name": "AlbumApp", "app_description": "E-commerce"}

    mock_bot = MagicMock()
    captured_media = []

    async def _capture_send_media_group(chat_id, media, **kw):
        captured_media.extend(media)

    mock_bot.send_media_group = _capture_send_media_group
    mock_bot.send_photo = AsyncMock(return_value=None)

    with patch("factory.pipeline.s0_intake.generate_image",
               new_callable=AsyncMock, return_value=_FAKE_LOGO_BYTES), \
         patch("factory.pipeline.s0_intake.build_logo_prompt", return_value="AlbumApp logo"), \
         patch("factory.pipeline.s0_intake.get_bot", return_value=mock_bot), \
         patch("factory.pipeline.s0_intake._save_logo_to_disk", return_value="/tmp/logo3.png"):
        result = await _logo_flow_auto(state, requirements)

    # All 3 variants should succeed → 3 items in album
    assert len(captured_media) == 3, (
        f"Expected 3 media items in album, got {len(captured_media)}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 4: With only 1 variant, falls back to send_photo
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logo_flow_auto_single_variant_falls_back_to_send_photo():
    """With only 1 successful variant, must use send_photo fallback."""
    from factory.pipeline.s0_intake import _logo_flow_auto

    state = _make_state("proj_logo_t4")
    requirements = {"app_name": "SingleApp", "app_description": ""}

    call_count = {"n": 0}

    async def _partial_gen(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FAKE_LOGO_BYTES  # only first succeeds
        return None  # rest fail

    mock_bot = MagicMock()
    mock_bot.send_photo = AsyncMock(return_value=None)
    mock_bot.send_media_group = AsyncMock(return_value=None)

    with patch("factory.pipeline.s0_intake.generate_image", side_effect=_partial_gen), \
         patch("factory.pipeline.s0_intake.build_logo_prompt", return_value="SingleApp logo"), \
         patch("factory.pipeline.s0_intake.get_bot", return_value=mock_bot), \
         patch("factory.pipeline.s0_intake._save_logo_to_disk", return_value="/tmp/logo4.png"):
        result = await _logo_flow_auto(state, requirements)

    mock_bot.send_photo.assert_called_once()
    mock_bot.send_media_group.assert_not_called()
    assert result is not None


# ═══════════════════════════════════════════════════════════════════
# Test 5: With 0 variants, returns None and sends nothing
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logo_flow_auto_no_variants_returns_none():
    """When all variants fail, _logo_flow_auto must return None and not call send_photo/group."""
    from factory.pipeline.s0_intake import _logo_flow_auto

    state = _make_state("proj_logo_t5")
    requirements = {"app_name": "FailApp", "app_description": ""}

    mock_bot = MagicMock()
    mock_bot.send_photo = AsyncMock(return_value=None)
    mock_bot.send_media_group = AsyncMock(return_value=None)

    with patch("factory.pipeline.s0_intake.generate_image",
               new_callable=AsyncMock, return_value=None), \
         patch("factory.pipeline.s0_intake.build_logo_prompt", return_value="FailApp logo"), \
         patch("factory.pipeline.s0_intake.get_bot", return_value=mock_bot):
        result = await _logo_flow_auto(state, requirements)

    assert result is None, f"Expected None when all variants fail, got: {result}"
    mock_bot.send_photo.assert_not_called()
    mock_bot.send_media_group.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Test 6: Return value includes logo_variant_count
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logo_flow_auto_result_has_variant_count():
    """Return dict must include logo_variant_count indicating how many variants were generated."""
    from factory.pipeline.s0_intake import _logo_flow_auto

    state = _make_state("proj_logo_t6")
    requirements = {"app_name": "CountApp", "app_description": "Finance"}

    mock_bot = MagicMock()
    mock_bot.send_media_group = AsyncMock(return_value=None)
    mock_bot.send_photo = AsyncMock(return_value=None)

    with patch("factory.pipeline.s0_intake.generate_image",
               new_callable=AsyncMock, return_value=_FAKE_LOGO_BYTES), \
         patch("factory.pipeline.s0_intake.build_logo_prompt", return_value="CountApp logo"), \
         patch("factory.pipeline.s0_intake.get_bot", return_value=mock_bot), \
         patch("factory.pipeline.s0_intake._save_logo_to_disk", return_value="/tmp/logo6.png"):
        result = await _logo_flow_auto(state, requirements)

    assert result is not None
    assert "logo_variant_count" in result, (
        f"Return dict missing 'logo_variant_count': {result}"
    )
    assert result["logo_variant_count"] == 3, (
        f"Expected 3 variants, got: {result['logo_variant_count']}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 7: Return value includes logo_path for downstream stages
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logo_flow_auto_result_has_logo_path():
    """Return dict must include logo_path (Issue 13: downstream stages need a real path)."""
    from factory.pipeline.s0_intake import _logo_flow_auto

    state = _make_state("proj_logo_t7")
    requirements = {"app_name": "PathApp", "app_description": ""}

    mock_bot = MagicMock()
    mock_bot.send_media_group = AsyncMock(return_value=None)
    mock_bot.send_photo = AsyncMock(return_value=None)

    with patch("factory.pipeline.s0_intake.generate_image",
               new_callable=AsyncMock, return_value=_FAKE_LOGO_BYTES), \
         patch("factory.pipeline.s0_intake.build_logo_prompt", return_value="PathApp logo"), \
         patch("factory.pipeline.s0_intake.get_bot", return_value=mock_bot), \
         patch("factory.pipeline.s0_intake._save_logo_to_disk",
               return_value="/tmp/pathapp_logo.png") as mock_save:
        result = await _logo_flow_auto(state, requirements)

    assert result is not None
    assert "logo_path" in result, f"Return dict missing 'logo_path': {result}"
    assert result["logo_path"] == "/tmp/pathapp_logo.png"
    mock_save.assert_called_once()
