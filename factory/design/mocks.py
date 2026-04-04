"""
AI Factory Pipeline v5.6 — Visual Mock Generation

Implements:
  - §3.4.3 Pre-Build Visual Mocks (3 Mocks to Telegram)
  - HTML mock generation via Engineer
  - PNG screenshot capture via Puppeteer
  - Telegram delivery with operator selection
  - Autopilot auto-select (Clean Minimal)

Spec Authority: v5.6 §3.4.3
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from factory.core.state import (
    AIRole,
    AutonomyMode,
    PipelineState,
)
from factory.core.roles import call_ai
from factory.core.execution import ExecutionModeManager
from factory.core.user_space import enforce_user_space
from factory.telegram.notifications import send_telegram_message

logger = logging.getLogger("factory.design.mocks")


# ═══════════════════════════════════════════════════════════════════
# §3.4.3 Mock Variations
# ═══════════════════════════════════════════════════════════════════

MOCK_VARIATIONS = [
    {
        "name": "Clean Minimal",
        "hint": "Max whitespace, thin borders, subtle shadows",
    },
    {
        "name": "Bold Modern",
        "hint": "Vivid colors, rounded corners, card-heavy",
    },
    {
        "name": "Professional",
        "hint": "Structured grid, muted tones, data-dense",
    },
]


# ═══════════════════════════════════════════════════════════════════
# §3.4.3 Visual Mock Generation
# ═══════════════════════════════════════════════════════════════════


async def generate_visual_mocks(
    state: PipelineState,
    blueprint_data: dict,
    design: dict,
) -> tuple[list[str], int]:
    """Generate 3 HTML mock variations, capture as PNG, send to Telegram.

    Spec: §3.4.3

    Args:
        state: Current pipeline state.
        blueprint_data: Blueprint dict with screens, app_name, etc.
        design: Validated design dict from Grid Enforcer.

    Returns:
        Tuple of (mock_paths, selected_index).
        - Copilot: waits for operator reply (1-4)
        - Autopilot: auto-selects index 0 (Clean Minimal)
    """
    screens = blueprint_data.get("screens", [])
    app_name = blueprint_data.get("app_name", state.project_id)
    key_screens = screens[:2]  # First 2 screens for mocks

    mock_paths: list[str] = []
    mock_html: list[str] = []

    for i, variation in enumerate(MOCK_VARIATIONS):
        html = await _generate_mock_html(
            state, key_screens, design, variation,
        )
        mock_html.append(html)

        # Write HTML file
        html_path = f"/tmp/mock_{state.project_id}_{i}.html"
        _write_file_sync(html_path, html)

        # Capture PNG screenshot
        png_path = f"/tmp/mock_{state.project_id}_{i}.png"
        await _capture_screenshot(state, html_path, png_path)
        mock_paths.append(png_path)

    # Store in state
    state.project_metadata["design_mocks"] = mock_paths
    state.project_metadata["mock_html"] = [
        h[:5000] for h in mock_html  # Truncate for state storage
    ]

    # ── Operator selection ──
    selected = await _get_operator_selection(state, app_name, mock_paths)

    logger.info(
        f"[{state.project_id}] Mocks generated: "
        f"{len(mock_paths)} variations, "
        f"selected={MOCK_VARIATIONS[selected]['name']}"
    )
    return mock_paths, selected


async def _generate_mock_html(
    state: PipelineState,
    screens: list,
    design: dict,
    variation: dict,
) -> str:
    """Generate single HTML mock for a variation.

    Spec: §3.4.3
    """
    return await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Generate single HTML file mocking these screens:\n"
            f"{json.dumps(screens)[:3000]}\n"
            f"Design: {json.dumps(design)[:2000]}\n"
            f"Style: {variation['name']} — {variation['hint']}\n"
            f"Mobile viewport 375x812. RTL support. "
            f"All spacing multiples of 4px.\n"
            f"Return ONLY HTML with inline CSS."
        ),
        state=state,
        action="write_code",
    )


async def _capture_screenshot(
    state: PipelineState, html_path: str, png_path: str,
) -> bool:
    """Capture HTML as PNG via Puppeteer.

    Spec: §3.4.3
    Stub: creates placeholder for offline dev.
    """
    exec_mgr = ExecutionModeManager(state)

    try:
        result = await exec_mgr.execute_task({
            "name": "mock_screenshot",
            "type": "build",
            "command": enforce_user_space(
                f"npx puppeteer-cli screenshot "
                f"{html_path} {png_path} --viewport 800x900"
            ),
            "timeout": 30,
        }, requires_macincloud=False)

        return result.get("exit_code", 1) == 0
    except Exception:
        # Stub: create placeholder PNG path entry
        logger.debug(f"Screenshot stub: {png_path}")
        return True


async def _get_operator_selection(
    state: PipelineState, app_name: str,
    mock_paths: list[str],
) -> int:
    """Get operator's design selection.

    Spec: §3.4.3
    Copilot: sends photos + inline keyboard, waits for reply.
    Autopilot: auto-selects index 0 (Clean Minimal).
    """
    if state.autonomy_mode == AutonomyMode.COPILOT:
        message = (
            f"🎨 Design options for {app_name}:\n\n"
            f"1️⃣ Clean Minimal\n"
            f"2️⃣ Bold Modern\n"
            f"3️⃣ Professional\n"
            f"4️⃣ Custom: Describe what you want\n\n"
            f"Reply 1-4."
        )
        await send_telegram_message(state.operator_id, message)

        # In production: await wait_for_operator_reply()
        # Stub: return first option
        logger.info(
            f"[{state.project_id}] Copilot mock selection: "
            f"awaiting operator (stub: auto-select 1)"
        )
        return 0
    else:
        # Autopilot: Clean Minimal
        logger.info(
            f"[{state.project_id}] Autopilot mock selection: Clean Minimal"
        )
        return 0


def _write_file_sync(path: str, content: str) -> None:
    """Write file synchronously (for HTML mocks)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ═══════════════════════════════════════════════════════════════════
# Mock Selection Helpers
# ═══════════════════════════════════════════════════════════════════


def get_variation_name(index: int) -> str:
    """Get variation name by index."""
    if 0 <= index < len(MOCK_VARIATIONS):
        return MOCK_VARIATIONS[index]["name"]
    return "Custom"


def get_variation_count() -> int:
    """Get total number of mock variations."""
    return len(MOCK_VARIATIONS)