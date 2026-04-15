"""
AI Factory Pipeline v5.8 — Design Engine Module

Hunter-Gatherer design system: Vibe Check, Grid Enforcer, Visual Mocks.
"""

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
    WCAG_AA_LARGE,
)

from factory.design.grid_enforcer import (
    DesignSpec,
    ColorPalette,
    Typography,
    Spacing,
    grid_enforcer_validate,
    create_default_design,
)

from factory.design.vibe_check import (
    vibe_check,
    quick_vibe_check,
    DESIGN_DNA_SCHEMA,
)

from factory.design.mocks import (
    generate_visual_mocks,
    MOCK_VARIATIONS,
    get_variation_name,
    get_variation_count,
)

__all__ = [
    # Contrast
    "hex_to_rgb", "rgb_to_hex", "relative_luminance",
    "contrast_ratio", "darken_until_contrast", "ensure_contrast",
    "check_wcag_aa", "check_wcag_aa_large",
    "WCAG_AA_NORMAL", "WCAG_AA_LARGE",
    # Grid Enforcer
    "DesignSpec", "grid_enforcer_validate", "create_default_design",
    # Vibe Check
    "vibe_check", "quick_vibe_check",
    # Mocks
    "generate_visual_mocks", "MOCK_VARIATIONS",
    "get_variation_name", "get_variation_count",
]