"""
AI Factory Pipeline v5.6 — Grid Enforcer (Pydantic Validators)

Implements:
  - §3.4.2 DesignSpec model with validators
  - 4px grid enforcement
  - WCAG AA contrast enforcement (4.5:1)
  - Font size minimum (12px) and even-number enforcement

Spec Authority: v5.6 §3.4.2
"No Ugly Apps."
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, model_validator

from factory.design.contrast import (
    contrast_ratio,
    darken_until_contrast,
    ensure_contrast,
    WCAG_AA_NORMAL,
)

logger = logging.getLogger("factory.design.grid_enforcer")


# ═══════════════════════════════════════════════════════════════════
# §3.4.2 DesignSpec Model
# ═══════════════════════════════════════════════════════════════════


class ColorPalette(BaseModel):
    """Validated color palette with required keys."""
    primary: str = "#1a73e8"
    secondary: str = "#5f6368"
    accent: str = "#fbbc04"
    background: str = "#ffffff"
    surface: str = "#f8f9fa"
    text_primary: str = "#202124"
    text_secondary: str = "#5f6368"
    error: str = "#d93025"


class Typography(BaseModel):
    """Validated typography settings."""
    heading_font: str = "Inter"
    body_font: str = "Inter"
    size_base: int = 16
    scale_ratio: float = 1.25


class Spacing(BaseModel):
    """Validated spacing with 4px grid enforcement."""
    unit: int = 4
    page_padding: int = 16
    card_padding: int = 12
    element_gap: int = 8


class DesignSpec(BaseModel):
    """Validated design specification.

    Spec: §3.4.2
    Enforces:
      1. 4px grid — all spacing values snapped to multiples of 4
      2. WCAG AA contrast — text colors darkened until 4.5:1 ratio
      3. Font sizes — minimum 12px, even numbers only

    'No Ugly Apps.'
    """
    color_palette: dict
    typography: dict
    spacing: dict
    layout_patterns: list[str] = ["cards", "bottom_nav"]
    visual_style: str = "minimal"

    @model_validator(mode="after")
    def enforce_4px_grid(self) -> "DesignSpec":
        """Snap all spacing values to 4px grid.

        Spec: §3.4.2 — 'All spacing multiples of 4px'
        """
        corrections = 0
        for key, value in self.spacing.items():
            if isinstance(value, (int, float)) and key != "unit":
                if value % 4 != 0:
                    original = value
                    self.spacing[key] = max(4, round(value / 4) * 4)
                    corrections += 1
                    logger.debug(
                        f"Grid Enforcer: {key} {original} → {self.spacing[key]}"
                    )
        if corrections:
            logger.info(f"Grid Enforcer: corrected {corrections} spacing values")
        return self

    @model_validator(mode="after")
    def enforce_wcag_contrast(self) -> "DesignSpec":
        """Ensure text colors meet WCAG AA (4.5:1) against background.

        Spec: §3.4.2 — 'WCAG AA contrast (4.5:1)'
        """
        bg = self.color_palette.get("background", "#FFFFFF")
        corrections = 0

        for text_key in ("text_primary", "text_secondary"):
            text_color = self.color_palette.get(text_key, "#000000")
            ratio = contrast_ratio(bg, text_color)
            if ratio < WCAG_AA_NORMAL:
                original = text_color
                self.color_palette[text_key] = ensure_contrast(
                    bg, text_color, WCAG_AA_NORMAL,
                )
                new_ratio = contrast_ratio(
                    bg, self.color_palette[text_key]
                )
                corrections += 1
                logger.debug(
                    f"Grid Enforcer: {text_key} {original} → "
                    f"{self.color_palette[text_key]} "
                    f"(ratio {ratio:.1f} → {new_ratio:.1f})"
                )

        if corrections:
            logger.info(
                f"Grid Enforcer: fixed {corrections} contrast violations"
            )
        return self

    @model_validator(mode="after")
    def enforce_font_sizes(self) -> "DesignSpec":
        """Enforce minimum 12px and even font sizes.

        Spec: §3.4.2
        """
        base = self.typography.get("size_base", 16)
        if base < 12:
            self.typography["size_base"] = 12
            logger.debug(f"Grid Enforcer: size_base {base} → 12 (minimum)")
        elif base % 2 != 0:
            self.typography["size_base"] = base + 1
            logger.debug(
                f"Grid Enforcer: size_base {base} → {base + 1} (even)"
            )
        return self


# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════


def grid_enforcer_validate(design: dict) -> dict:
    """Validate and auto-correct a design spec.

    Spec: §3.4.2

    Args:
        design: Raw design dict from AI or operator.

    Returns:
        Validated and corrected design dict.
    """
    validated = DesignSpec.model_validate(design)
    return validated.model_dump()


def create_default_design(
    category: str = "general",
    visual_style: str = "minimal",
) -> dict:
    """Create a validated default design for a category.

    Used when Vibe Check is skipped (Autopilot fast-track).
    """
    # Category-specific defaults
    palette_presets = {
        "e-commerce": {
            "primary": "#ff6b35", "secondary": "#004e89",
            "accent": "#ffc107", "background": "#ffffff",
            "surface": "#f5f5f5", "text_primary": "#1a1a1a",
            "text_secondary": "#666666", "error": "#d32f2f",
        },
        "food-delivery": {
            "primary": "#e53935", "secondary": "#ff8a65",
            "accent": "#4caf50", "background": "#ffffff",
            "surface": "#fafafa", "text_primary": "#212121",
            "text_secondary": "#757575", "error": "#c62828",
        },
        "fintech": {
            "primary": "#1565c0", "secondary": "#0d47a1",
            "accent": "#00c853", "background": "#fafafa",
            "surface": "#ffffff", "text_primary": "#263238",
            "text_secondary": "#546e7a", "error": "#b71c1c",
        },
    }

    palette = palette_presets.get(category, {
        "primary": "#1a73e8", "secondary": "#5f6368",
        "accent": "#fbbc04", "background": "#ffffff",
        "surface": "#f8f9fa", "text_primary": "#202124",
        "text_secondary": "#5f6368", "error": "#d93025",
    })

    design = {
        "color_palette": palette,
        "typography": {
            "heading_font": "Inter",
            "body_font": "Inter",
            "size_base": 16,
            "scale_ratio": 1.25,
        },
        "spacing": {
            "unit": 4,
            "page_padding": 16,
            "card_padding": 12,
            "element_gap": 8,
        },
        "layout_patterns": ["cards", "bottom_nav"],
        "visual_style": visual_style,
    }

    return grid_enforcer_validate(design)