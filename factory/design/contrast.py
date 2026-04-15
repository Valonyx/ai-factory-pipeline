"""
AI Factory Pipeline v5.8 — WCAG Contrast Utilities

Implements:
  - §3.4.2 Contrast utility functions
  - hex_to_rgb, relative_luminance, contrast_ratio
  - darken_until_contrast (auto-fix for WCAG AA 4.5:1)

Spec Authority: v5.6 §3.4.2
"""

from __future__ import annotations


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple.

    Spec: §3.4.2

    Args:
        h: Hex color string (with or without '#' prefix).

    Returns:
        Tuple of (red, green, blue) integers 0-255.
    """
    h = h.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB to hex color string."""
    return f"#{r:02x}{g:02x}{b:02x}"


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Calculate relative luminance per WCAG 2.1.

    Spec: §3.4.2

    Uses sRGB linearization formula:
      - If C <= 0.03928: C_lin = C / 12.92
      - Else: C_lin = ((C + 0.055) / 1.055) ^ 2.4

    Returns luminance in range [0.0, 1.0].
    """
    def linearize(c: int) -> float:
        c_norm = c / 255.0
        if c_norm <= 0.03928:
            return c_norm / 12.92
        return ((c_norm + 0.055) / 1.055) ** 2.4

    r, g, b = [linearize(c) for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color1: str, color2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors.

    Spec: §3.4.2

    WCAG AA requires:
      - Normal text: >= 4.5:1
      - Large text (18pt+ or 14pt bold): >= 3.0:1

    Returns ratio in range [1.0, 21.0].
    """
    l1 = relative_luminance(hex_to_rgb(color1))
    l2 = relative_luminance(hex_to_rgb(color2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def darken_until_contrast(
    bg: str, text: str, target: float = 4.5,
) -> str:
    """Progressively darken text color until WCAG contrast target is met.

    Spec: §3.4.2

    Iteratively reduces RGB values by 5% per step (up to 50 steps).
    Returns "#000000" as fallback if target cannot be reached.

    Args:
        bg: Background hex color.
        text: Starting text hex color.
        target: Target contrast ratio (default: WCAG AA 4.5:1).

    Returns:
        Adjusted hex color meeting the contrast target.
    """
    r, g, b = hex_to_rgb(text)

    for _ in range(50):
        current_hex = rgb_to_hex(r, g, b)
        if contrast_ratio(bg, current_hex) >= target:
            return current_hex
        # Darken by 5%
        r = max(0, int(r * 0.95))
        g = max(0, int(g * 0.95))
        b = max(0, int(b * 0.95))

    return "#000000"


def lighten_until_contrast(
    bg: str, text: str, target: float = 4.5,
) -> str:
    """Progressively lighten text color until WCAG contrast target is met.

    For dark backgrounds where darkening text would reduce contrast.
    """
    r, g, b = hex_to_rgb(text)

    for _ in range(50):
        current_hex = rgb_to_hex(r, g, b)
        if contrast_ratio(bg, current_hex) >= target:
            return current_hex
        # Lighten by 5%
        r = min(255, int(r + (255 - r) * 0.05))
        g = min(255, int(g + (255 - g) * 0.05))
        b = min(255, int(b + (255 - b) * 0.05))

    return "#ffffff"


def ensure_contrast(
    bg: str, text: str, target: float = 4.5,
) -> str:
    """Auto-fix text color to meet WCAG contrast against background.

    Determines whether to darken or lighten based on background luminance.
    """
    bg_lum = relative_luminance(hex_to_rgb(bg))
    if bg_lum > 0.5:
        # Light background → darken text
        return darken_until_contrast(bg, text, target)
    else:
        # Dark background → lighten text
        return lighten_until_contrast(bg, text, target)


# ═══════════════════════════════════════════════════════════════════
# WCAG Compliance Checks
# ═══════════════════════════════════════════════════════════════════

WCAG_AA_NORMAL = 4.5
WCAG_AA_LARGE = 3.0
WCAG_AAA_NORMAL = 7.0


def check_wcag_aa(bg: str, text: str) -> bool:
    """Check if color pair meets WCAG AA for normal text."""
    return contrast_ratio(bg, text) >= WCAG_AA_NORMAL


def check_wcag_aa_large(bg: str, text: str) -> bool:
    """Check if color pair meets WCAG AA for large text."""
    return contrast_ratio(bg, text) >= WCAG_AA_LARGE


def check_wcag_aaa(bg: str, text: str) -> bool:
    """Check if color pair meets WCAG AAA for normal text."""
    return contrast_ratio(bg, text) >= WCAG_AAA_NORMAL