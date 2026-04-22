"""v5.8.16 G4/G5 Vision Gap Closure — unit tests.

Covers three requirements for each gap:
  G4 (UI parsing via Claude Vision fallback):
    1. Key missing  → typed degraded result (never fake success)
    2. Key present  → call made, parsed result returned
    3. BASIC mode   → Claude Vision skipped, degraded returned immediately

  G5 (vibe_check screenshot verification):
    4. BASIC mode   → vision step skipped, metadata says reason=basic_mode
    5. Key missing  → metadata says reason=api_key_missing (non-fatal)
    6. Key present + PNG present → analyses reach state.project_metadata

Mock strategy (unit tier):
  - conftest autouse sets AI_PROVIDER=mock — triggers early-return in
    claude_vision.call_claude_vision, so no SDK import needed.
  - Non-mock paths are tested by overriding AI_PROVIDER via patch.dict
    and mocking `anthropic.AsyncAnthropic` at the SDK boundary.
  - httpx is mocked at the class level for NIM vision paths.
  - factory.integrations.* is NOT patched (forbidden for integration/e2e
    tests per conftest.py:56; unit tests avoid this pattern to stay clean).
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.mode_router import MasterMode
from factory.core.state import PipelineState, AutonomyMode

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

_FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n"               # PNG signature
    b"\x00\x00\x00\rIHDR"              # IHDR chunk length + type
    b"\x00\x00\x00\x01\x00\x00\x00\x01"  # 1×1 pixels
    b"\x08\x02\x00\x00\x00\x90wS\xde"  # bit depth, colour type, crc
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_state(mode: MasterMode = MasterMode.BALANCED) -> PipelineState:
    state = PipelineState(project_id="test-g4g5", operator_id="test-op")
    state.master_mode = mode
    state.autonomy_mode = AutonomyMode.AUTOPILOT
    return state


def _mock_anthropic_response(text: str = "Button: Submit", input_tok: int = 800, output_tok: int = 200):
    """Build a minimal mock that mimics anthropic.AsyncAnthropic.messages.create."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text

    usage = MagicMock()
    usage.input_tokens = input_tok
    usage.output_tokens = output_tok

    message = MagicMock()
    message.content = [content_block]
    message.usage = usage

    mock_create = AsyncMock(return_value=message)
    mock_messages = MagicMock()
    mock_messages.create = mock_create

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls, mock_create


# ═══════════════════════════════════════════════════════════════════
# G4 — claude_vision.py
# ═══════════════════════════════════════════════════════════════════


class TestClaudeVision:
    """Unit tests for factory/integrations/claude_vision.py."""

    def test_mock_mode_returns_mock_tuple(self):
        """AI_PROVIDER=mock (set by conftest autouse) → early return, no SDK call."""
        from factory.integrations.claude_vision import call_claude_vision
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            call_claude_vision(_FAKE_PNG, "analyse this UI")
        )
        text, cost = result
        assert "[MOCK:claude_vision]" in text
        assert cost == 0.0001

    def test_is_available_mock_mode_true(self):
        """is_available() returns True in mock mode (key not required)."""
        from factory.integrations.claude_vision import is_available

        assert is_available() is True  # AI_PROVIDER=mock from conftest

    def test_key_missing_raises_value_error(self):
        """Non-mock + missing ANTHROPIC_API_KEY → ValueError."""
        from factory.integrations.claude_vision import call_claude_vision
        import asyncio

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""}):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                asyncio.get_event_loop().run_until_complete(
                    call_claude_vision(_FAKE_PNG, "analyse this UI")
                )

    def test_is_available_key_missing_false(self):
        """is_available() returns False when key is absent and not mock."""
        from factory.integrations.claude_vision import is_available

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""}):
            assert is_available() is False

    def test_is_available_key_present_true(self):
        """is_available() returns True when ANTHROPIC_API_KEY is set."""
        from factory.integrations.claude_vision import is_available

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-test"}):
            assert is_available() is True

    def test_key_present_calls_sdk_and_returns_parsed_result(self):
        """Non-mock + key present → Anthropic SDK called, (text, cost) returned."""
        from factory.integrations.claude_vision import call_claude_vision
        import asyncio

        mock_cls, mock_create = _mock_anthropic_response("Button: Submit\nInput: Email")

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch("anthropic.AsyncAnthropic", mock_cls):
                text, cost = asyncio.get_event_loop().run_until_complete(
                    call_claude_vision(_FAKE_PNG, "analyse UI elements")
                )

        assert "Button: Submit" in text
        assert "Input: Email" in text
        # cost = 800/1M * 0.80 + 200/1M * 4.00 = 0.00064 + 0.0008 = 0.00144
        assert 0.001 < cost < 0.003
        mock_create.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════
# G4 — omniparser.py vision fallback chain
# ═══════════════════════════════════════════════════════════════════


class TestOmniparserVisionFallback:
    """Unit tests for the vision fallback chain in factory/integrations/omniparser.py."""

    def test_mock_mode_returns_mock_elements(self):
        """AI_PROVIDER=mock → mock elements without any HTTP call."""
        from factory.integrations.omniparser import parse_screenshot
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            parse_screenshot(_FAKE_PNG, "find buttons")
        )
        assert result["source"] == "mock"
        assert result["elements"]

    def test_basic_mode_skips_claude_vision_when_nim_fails(self):
        """BASIC mode: NIM vision fails → degrade immediately, no Claude Vision call."""
        import asyncio

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-test"}):
            # Patch NIM vision to fail (simulates missing NVIDIA key)
            with patch(
                "factory.integrations.nvidia_nim_vision.analyze_ui_screenshot",
                new_callable=AsyncMock,
                side_effect=ValueError("No NVIDIA NIM vision API key configured"),
            ):
                # Claude Vision should NOT be called in BASIC mode
                with patch(
                    "factory.integrations.claude_vision.call_claude_vision",
                    new_callable=AsyncMock,
                ) as mock_cv:
                    from factory.integrations.omniparser import parse_screenshot
                    result = asyncio.get_event_loop().run_until_complete(
                        parse_screenshot(_FAKE_PNG, "find buttons", mode="basic")
                    )

        assert result["source"] == "degraded"
        assert result.get("degraded") is True
        assert "BASIC mode" in result.get("error", "")
        mock_cv.assert_not_awaited()

    def test_balanced_mode_tries_claude_vision_after_nim_fails(self):
        """BALANCED mode: NIM fails → Claude Vision called → result returned."""
        import asyncio

        mock_cls, _ = _mock_anthropic_response("Button: Login\nInput: Password")

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch(
                "factory.integrations.nvidia_nim_vision.analyze_ui_screenshot",
                new_callable=AsyncMock,
                side_effect=ValueError("No NVIDIA NIM vision API key configured"),
            ):
                with patch("anthropic.AsyncAnthropic", mock_cls):
                    from factory.integrations.omniparser import parse_screenshot
                    result = asyncio.get_event_loop().run_until_complete(
                        parse_screenshot(_FAKE_PNG, "find buttons", mode="balanced")
                    )

        assert result["source"] == "claude_vision_fallback"
        assert "Button: Login" in result["structured_text"]
        assert not result.get("degraded")

    def test_all_vision_providers_fail_returns_typed_degraded(self):
        """Both NIM and Claude Vision fail → typed degraded, never fake success."""
        import asyncio

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch(
                "factory.integrations.nvidia_nim_vision.analyze_ui_screenshot",
                new_callable=AsyncMock,
                side_effect=RuntimeError("NIM network error"),
            ):
                with patch(
                    "factory.integrations.claude_vision.call_claude_vision",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("Claude API error"),
                ):
                    from factory.integrations.omniparser import parse_screenshot
                    result = asyncio.get_event_loop().run_until_complete(
                        parse_screenshot(_FAKE_PNG, "find buttons", mode="balanced")
                    )

        assert result["source"] == "degraded"
        assert result.get("degraded") is True
        assert result["structured_text"] == ""
        # Proves we never returned "UI analysis unavailable" as fake success
        assert "UI analysis unavailable" not in result.get("structured_text", "")

    def test_claude_vision_key_missing_returns_typed_degraded(self):
        """Key missing + balanced mode → degraded with informative error, not halt."""
        import asyncio

        with patch.dict(os.environ, {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""}):
            with patch(
                "factory.integrations.nvidia_nim_vision.analyze_ui_screenshot",
                new_callable=AsyncMock,
                side_effect=ValueError("No NVIDIA NIM vision API key configured"),
            ):
                from factory.integrations.omniparser import parse_screenshot
                result = asyncio.get_event_loop().run_until_complete(
                    parse_screenshot(_FAKE_PNG, "find buttons", mode="balanced")
                )

        assert result["source"] == "degraded"
        assert result.get("degraded") is True
        assert "ANTHROPIC_API_KEY" in result.get("error", "")


# ═══════════════════════════════════════════════════════════════════
# G5 — vibe_check.py vision verification step
# ═══════════════════════════════════════════════════════════════════


class TestVibeCheckVisionVerify:
    """Unit tests for _vision_verify_mockup() inside factory/design/vibe_check.py."""

    def _design(self) -> dict:
        return {
            "color_palette": {"primary": "#2563EB"},
            "visual_style": "minimal",
            "layout_patterns": ["cards", "bottom_nav"],
        }

    def test_basic_mode_skips_vision_step(self):
        """BASIC mode → vision step skipped, metadata reason=basic_mode."""
        import asyncio
        from factory.design.vibe_check import _vision_verify_mockup

        state = _make_state(MasterMode.BASIC)
        asyncio.get_event_loop().run_until_complete(
            _vision_verify_mockup(state, self._design(), "food delivery app")
        )

        va = state.project_metadata.get("vision_analysis", {})
        assert va.get("skipped") is True
        assert va.get("reason") == "basic_mode"

    def test_no_screenshots_dir_skips_gracefully(self, tmp_path):
        """Empty / missing screenshots dir → skipped, reason=no_screenshots."""
        import asyncio
        from factory.design.vibe_check import _vision_verify_mockup

        state = _make_state(MasterMode.BALANCED)
        # Override project_id so the screenshots path points into tmp_path (no PNGs there)
        state.project_id = "nonexistent-proj-xyz"

        with patch("factory.design.vibe_check.Path", wraps=Path) as mock_path_cls:
            asyncio.get_event_loop().run_until_complete(
                _vision_verify_mockup(state, self._design(), "food delivery app")
            )

        va = state.project_metadata.get("vision_analysis", {})
        assert va.get("skipped") is True
        assert va.get("reason") == "no_screenshots"

    def test_key_missing_returns_degraded_metadata(self, tmp_path, monkeypatch):
        """ANTHROPIC_API_KEY missing → degraded metadata, stage not halted.

        Uses monkeypatch.chdir so that Path("artifacts")/project_id/... resolves
        to the tmp dir without needing to mock Path itself.
        is_available() is patched at its definition site (local import).
        """
        import asyncio
        from factory.design.vibe_check import _vision_verify_mockup

        monkeypatch.chdir(tmp_path)
        screenshots_dir = tmp_path / "artifacts" / "t-proj" / "design" / "screenshots"
        screenshots_dir.mkdir(parents=True)
        (screenshots_dir / "screen1.png").write_bytes(_FAKE_PNG)

        state = _make_state(MasterMode.BALANCED)
        state.project_id = "t-proj"

        with patch("factory.integrations.claude_vision.is_available", return_value=False):
            asyncio.get_event_loop().run_until_complete(
                _vision_verify_mockup(state, self._design(), "food delivery app")
            )

        va = state.project_metadata.get("vision_analysis", {})
        assert va.get("degraded") is True
        assert va.get("reason") == "api_key_missing"

    def test_screenshots_analysed_on_success(self, tmp_path, monkeypatch):
        """Key present + PNGs present → analyses stored in state.project_metadata."""
        import asyncio
        from factory.design.vibe_check import _vision_verify_mockup

        monkeypatch.chdir(tmp_path)
        screenshots_dir = tmp_path / "artifacts" / "s-proj" / "design" / "screenshots"
        screenshots_dir.mkdir(parents=True)
        for i in range(2):
            (screenshots_dir / f"screen{i}.png").write_bytes(_FAKE_PNG)

        state = _make_state(MasterMode.BALANCED)
        state.project_id = "s-proj"

        analysis_json = json.dumps({
            "match": True, "issues": [], "score": 9, "summary": "Design matches DNA",
        })

        with patch("factory.integrations.claude_vision.is_available", return_value=True):
            with patch(
                "factory.integrations.claude_vision.call_claude_vision",
                new_callable=AsyncMock,
                return_value=(analysis_json, 0.0015),
            ):
                with patch(
                    "factory.core.quota_tracker.QuotaTracker.record_usage",
                    new_callable=AsyncMock,
                ):
                    asyncio.get_event_loop().run_until_complete(
                        _vision_verify_mockup(
                            state, self._design(), "food delivery app"
                        )
                    )

        va = state.project_metadata.get("vision_analysis", {})
        assert va.get("source") == "claude_vision"
        assert va.get("screenshots_checked") == 2
        assert len(va.get("analyses", [])) == 2
        assert va.get("total_cost_usd") > 0
        assert va["analyses"][0]["source"] == "claude_vision"
        assert "Design matches DNA" in va["analyses"][0]["analysis"]
