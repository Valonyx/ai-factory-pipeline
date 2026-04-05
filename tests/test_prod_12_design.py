"""
PROD-12 Validation: Design Engine

Tests cover:
  Contrast Utilities (6 tests):
    1.  hex_to_rgb parses 3 and 6 digit hex
    2.  relative_luminance white=~1.0, black=~0.0
    3.  contrast_ratio black/white ≈ 21:1
    4.  check_wcag_aa passes black-on-white, fails grey-on-white
    5.  darken_until_contrast fixes light grey
    6.  ensure_contrast auto-selects darken/lighten

  Grid Enforcer (5 tests):
    7.  4px grid snaps 15→16, 13→12, 9→8
    8.  WCAG contrast auto-fixes light text
    9.  Font minimum 10→12, odd 15→16
    10. create_default_design returns validated dict
    11. Category presets (e-commerce, fintech) have correct primaries

  Vibe Check (3 tests):
    12. quick_vibe_check returns validated design
    13. _parse_design_json extracts from markdown
    14. vibe_check with mocked call_ai returns validated

  Mocks (4 tests):
    15. MOCK_VARIATIONS has 3 entries
    16. _placeholder_html generates valid HTML
    17. get_variation_name returns correct names
    18. select_mock Autopilot auto-selects first

Run:
  pytest tests/test_prod_12_design.py -v
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock
import json

from factory.design.contrast import (
    hex_to_rgb,
    rgb_to_hex,
    relative_luminance,
    contrast_ratio,
    darken_until_contrast,
    lighten_until_contrast,
    ensure_contrast,
    check_wcag_aa,
    check_wcag_aa_large,
    WCAG_AA_NORMAL,
)
from factory.design.grid_enforcer import (
    DesignSpec,
    grid_enforcer_validate,
    create_default_design,
    CATEGORY_PALETTES,
    DEFAULT_PALETTE,
)
from factory.design.vibe_check import (
    vibe_check,
    quick_vibe_check,
    _parse_design_json,
    DESIGN_DNA_SCHEMA,
)
from factory.design.mocks import (
    MOCK_VARIATIONS,
    generate_visual_mocks,
    select_mock,
    get_variation_name,
    get_variation_count,
    _placeholder_html,
)
from factory.core.state import (
    AutonomyMode,
    PipelineState,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    s = PipelineState(
        project_id="test_design_001",
        operator_id="op_design",
    )
    s.s0_output = {"app_category": "e-commerce"}
    return s


@pytest.fixture
def sample_design():
    return {
        "color_palette": {
            "primary": "#1a73e8", "secondary": "#5f6368",
            "accent": "#fbbc04", "background": "#ffffff",
            "surface": "#f8f9fa", "text_primary": "#202124",
            "text_secondary": "#5f6368", "error": "#d93025",
        },
        "typography": {
            "heading_font": "Inter", "body_font": "Inter",
            "size_base": 16, "scale_ratio": 1.25,
        },
        "spacing": {
            "unit": 4, "page_padding": 16,
            "card_padding": 12, "element_gap": 8,
        },
        "layout_patterns": ["cards", "bottom_nav"],
        "visual_style": "minimal",
    }


# ═══════════════════════════════════════════════════════════════════
# Tests 1-6: Contrast Utilities
# ═══════════════════════════════════════════════════════════════════

class TestContrast:
    def test_hex_to_rgb(self):
        """hex_to_rgb parses 3 and 6 digit hex."""
        assert hex_to_rgb("#FF0000") == (255, 0, 0)
        assert hex_to_rgb("#00ff00") == (0, 255, 0)
        assert hex_to_rgb("0000FF") == (0, 0, 255)
        assert hex_to_rgb("#fff") == (255, 255, 255)

    def test_relative_luminance(self):
        """relative_luminance: white≈1.0, black≈0.0."""
        assert relative_luminance((255, 255, 255)) > 0.99
        assert relative_luminance((0, 0, 0)) < 0.01

    def test_contrast_ratio_bw(self):
        """contrast_ratio: black/white ≈ 21:1."""
        bw = contrast_ratio("#000000", "#ffffff")
        assert 20.5 < bw < 21.5
        same = contrast_ratio("#888888", "#888888")
        assert 0.99 < same < 1.01

    def test_wcag_checks(self):
        """check_wcag_aa passes/fails correctly."""
        assert check_wcag_aa("#ffffff", "#000000") is True
        assert check_wcag_aa("#ffffff", "#cccccc") is False
        assert check_wcag_aa_large(
            "#ffffff", "#767676",
        ) is True

    def test_darken_until_contrast(self):
        """darken_until_contrast fixes light grey."""
        result = darken_until_contrast(
            "#ffffff", "#cccccc", 4.5,
        )
        assert contrast_ratio("#ffffff", result) >= 4.5
        assert result != "#cccccc"

    def test_ensure_contrast_auto(self):
        """ensure_contrast auto-selects darken/lighten."""
        # Light bg → should darken
        light_result = ensure_contrast(
            "#ffffff", "#cccccc", 4.5,
        )
        assert contrast_ratio("#ffffff", light_result) >= 4.5

        # Dark bg → should lighten
        dark_result = ensure_contrast(
            "#1a1a1a", "#333333", 4.5,
        )
        assert contrast_ratio("#1a1a1a", dark_result) >= 4.5


# ═══════════════════════════════════════════════════════════════════
# Tests 7-11: Grid Enforcer
# ═══════════════════════════════════════════════════════════════════

class TestGridEnforcer:
    def test_4px_snap(self):
        """4px grid snaps 15→16, 13→12, 9→8."""
        design = {
            "color_palette": DEFAULT_PALETTE.copy(),
            "typography": {
                "heading_font": "Inter",
                "body_font": "Inter",
                "size_base": 16, "scale_ratio": 1.25,
            },
            "spacing": {
                "unit": 4, "page_padding": 15,
                "card_padding": 13, "element_gap": 9,
            },
        }
        v = grid_enforcer_validate(design)
        assert v["spacing"]["page_padding"] == 16
        assert v["spacing"]["card_padding"] == 12
        assert v["spacing"]["element_gap"] == 8

    def test_wcag_auto_fix(self):
        """WCAG contrast auto-fixes light text."""
        design = {
            "color_palette": {
                **DEFAULT_PALETTE,
                "text_primary": "#cccccc",
                "text_secondary": "#dddddd",
            },
            "typography": {
                "heading_font": "Inter",
                "body_font": "Inter",
                "size_base": 16, "scale_ratio": 1.25,
            },
            "spacing": {
                "unit": 4, "page_padding": 16,
                "card_padding": 12, "element_gap": 8,
            },
        }
        v = grid_enforcer_validate(design)
        bg = v["color_palette"]["background"]
        tp = v["color_palette"]["text_primary"]
        assert contrast_ratio(bg, tp) >= 4.5

    def test_font_minimum(self):
        """Font minimum 10→12, odd 15→16."""
        design = {
            "color_palette": DEFAULT_PALETTE.copy(),
            "typography": {
                "heading_font": "Inter",
                "body_font": "Inter",
                "size_base": 10, "scale_ratio": 1.25,
            },
            "spacing": {
                "unit": 4, "page_padding": 16,
                "card_padding": 12, "element_gap": 8,
            },
        }
        v = grid_enforcer_validate(design)
        assert v["typography"]["size_base"] == 12

        design2 = {**design, "typography": {
            **design["typography"], "size_base": 15,
        }}
        v2 = grid_enforcer_validate(design2)
        assert v2["typography"]["size_base"] == 16

    def test_default_design(self):
        """create_default_design returns validated dict."""
        d = create_default_design("e-commerce")
        assert "color_palette" in d
        assert "spacing" in d
        assert d["spacing"]["page_padding"] % 4 == 0

    def test_category_presets(self):
        """Category presets have correct primaries."""
        assert CATEGORY_PALETTES["e-commerce"][
            "primary"
        ] == "#ff6b35"
        assert CATEGORY_PALETTES["fintech"][
            "primary"
        ] == "#1565c0"
        assert len(CATEGORY_PALETTES) >= 4


# ═══════════════════════════════════════════════════════════════════
# Tests 12-14: Vibe Check
# ═══════════════════════════════════════════════════════════════════

class TestVibeCheck:
    @pytest.mark.asyncio
    async def test_quick_vibe(self, state):
        """quick_vibe_check returns validated design."""
        result = await quick_vibe_check(
            state, {"app_category": "fintech"},
        )
        assert "color_palette" in result
        assert result["spacing"]["page_padding"] % 4 == 0

    def test_parse_design_json_markdown(self):
        """_parse_design_json extracts from markdown block."""
        raw = (
            "Here's the design:\n```json\n"
            '{"color_palette":{"primary":"#ff0000"},'
            '"typography":{"size_base":16},'
            '"spacing":{"unit":4}}\n```\nDone.'
        )
        result = _parse_design_json(raw)
        assert result["color_palette"]["primary"] == "#ff0000"

    @pytest.mark.asyncio
    async def test_vibe_check_mocked(self, state):
        """vibe_check with mocked call_ai returns validated."""
        design_json = json.dumps({
            "color_palette": DEFAULT_PALETTE,
            "typography": {
                "heading_font": "Inter",
                "body_font": "Inter",
                "size_base": 16, "scale_ratio": 1.25,
            },
            "spacing": {
                "unit": 4, "page_padding": 16,
                "card_padding": 12, "element_gap": 8,
            },
            "layout_patterns": ["cards"],
            "visual_style": "minimal",
        })

        with patch(
            "factory.design.vibe_check.call_ai",
            new_callable=AsyncMock,
            return_value=design_json,
        ):
            result = await vibe_check(
                state, {"app_category": "e-commerce"},
            )
            assert "color_palette" in result


# ═══════════════════════════════════════════════════════════════════
# Tests 15-18: Mocks
# ═══════════════════════════════════════════════════════════════════

class TestMocks:
    def test_3_variations(self):
        """MOCK_VARIATIONS has 3 entries."""
        assert len(MOCK_VARIATIONS) == 3
        names = [v["name"] for v in MOCK_VARIATIONS]
        assert "Clean Minimal" in names
        assert "Card-Heavy" in names
        assert "Dashboard" in names

    def test_placeholder_html(self, sample_design):
        """_placeholder_html generates valid HTML."""
        html = _placeholder_html(
            sample_design,
            MOCK_VARIATIONS[0],
            ["Home", "Profile"],
        )
        assert "<div" in html
        assert "Home" in html
        assert "375px" in html

    def test_variation_names(self):
        """get_variation_name returns correct names."""
        assert get_variation_name(0) == "Clean Minimal"
        assert get_variation_name(1) == "Card-Heavy"
        assert get_variation_name(2) == "Dashboard"
        assert get_variation_name(99) == "Custom"
        assert get_variation_count() == 3

    @pytest.mark.asyncio
    async def test_select_mock_autopilot(self, state):
        """select_mock Autopilot auto-selects first."""
        state.autonomy_mode = AutonomyMode.AUTOPILOT
        mocks = [
            {"name": "A", "html": "<div>A</div>"},
            {"name": "B", "html": "<div>B</div>"},
        ]
        result = await select_mock(state, mocks)
        assert result["name"] == "A"
