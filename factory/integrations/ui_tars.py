"""
AI Factory Pipeline v5.8.12 — UI-TARS v2 Integration

UI-TARS is a multi-modal LLM for GUI agents. It can perceive, reason about,
and interact with UI elements across web, mobile, and desktop apps.
Developed by ByteDance.

GitHub: https://github.com/bytedance/ui-tars

Setup (local, GPU required):
  1. git clone https://github.com/bytedance/ui-tars
  2. pip install -r requirements.txt
  3. Download weights (UI-TARS-7B or UI-TARS-72B) from HuggingFace
  4. Set UI_TARS_ENDPOINT=http://localhost:7860 (vLLM or gradio server)
     OR set UI_TARS_MODEL_PATH=/path/to/weights

Optional env vars:
  UI_TARS_ENABLED   — "true" to enable (default: false)
  UI_TARS_ENDPOINT  — HTTP endpoint of a running UI-TARS server
  UI_TARS_API_KEY   — API key if endpoint requires auth
  UI_TARS_MODEL     — model variant ("7b" | "72b", default: "7b")

When not available, falls back to OmniParser + NIM vision combination.

Pipeline uses:
  - S3 Design: verify generated app screens match requirements
  - S6 Test: automated UI interaction planning
  - S8 Verify: post-deploy screenshot validation
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.ui_tars")


def is_available() -> bool:
    """Check if UI-TARS is configured and reachable."""
    if os.getenv("UI_TARS_ENABLED", "").lower() not in ("true", "1", "yes"):
        return False
    endpoint = os.getenv("UI_TARS_ENDPOINT", "")
    return bool(endpoint)


async def plan_ui_action(
    screenshot_bytes: bytes,
    instruction: str,
    history: Optional[list[dict]] = None,
) -> dict:
    """Plan the next UI action to accomplish an instruction.

    Args:
        screenshot_bytes: Current screen state as PNG/JPEG bytes.
        instruction: What the agent should accomplish.
        history: Previous action history for context.

    Returns:
        Dict with:
          - "action": action type ("click" | "type" | "scroll" | "done" | "fail")
          - "target": element description or coordinates
          - "value": text to type (if action == "type")
          - "reasoning": model's chain-of-thought
          - "source": "ui_tars" | "vision_fallback"

    Falls back to NIM vision analysis if UI-TARS is not available.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return {
            "action": "done",
            "target": None,
            "value": None,
            "reasoning": "[MOCK] UI action planned",
            "source": "mock",
        }

    if is_available():
        try:
            return await _call_ui_tars(screenshot_bytes, instruction, history or [])
        except Exception as e:
            logger.warning(f"[ui_tars] UI-TARS failed ({e}), falling back to vision")

    return await _vision_fallback_action(screenshot_bytes, instruction)


async def _call_ui_tars(
    screenshot_bytes: bytes,
    instruction: str,
    history: list[dict],
) -> dict:
    """Call the UI-TARS server endpoint."""
    endpoint = os.getenv("UI_TARS_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("UI_TARS_API_KEY", "")
    model = os.getenv("UI_TARS_MODEL", "ui-tars-7b")

    b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "screenshot": b64_image,
        "instruction": instruction,
        "history": history,
    }

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{endpoint}/predict", headers=headers, json=payload)

    response.raise_for_status()
    data = response.json()

    return {
        "action": data.get("action", "done"),
        "target": data.get("target"),
        "value": data.get("value"),
        "reasoning": data.get("reasoning", ""),
        "source": "ui_tars",
    }


async def _vision_fallback_action(screenshot_bytes: bytes, instruction: str) -> dict:
    """Fallback: use NIM vision to suggest the next action."""
    prompt = (
        f"Task: {instruction}\n\n"
        "Looking at this screenshot, what is the single best next UI action? "
        "Reply with JSON: {\"action\": \"click|type|scroll|done\", \"target\": \"element description\", "
        "\"value\": null or \"text to type\", \"reasoning\": \"brief reason\"}"
    )
    try:
        from factory.integrations.nvidia_nim_vision import describe_image
        raw = await describe_image(screenshot_bytes, prompt=prompt)

        import json
        import re
        match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            parsed["source"] = "vision_fallback"
            return parsed
    except Exception as e:
        logger.warning(f"[ui_tars] vision fallback failed: {e}")

    return {
        "action": "fail",
        "target": None,
        "value": None,
        "reasoning": "UI-TARS unavailable and vision fallback failed",
        "source": "vision_fallback",
    }


async def describe_screen_elements(screenshot_bytes: bytes) -> list[dict]:
    """Extract and describe all visible UI elements from a screenshot.

    Combines OmniParser (structural) + UI-TARS (semantic) if both available.
    """
    try:
        from factory.integrations.omniparser import parse_screenshot
        result = await parse_screenshot(screenshot_bytes)
        return result.get("elements", [])
    except Exception as e:
        logger.warning(f"[ui_tars] OmniParser element extraction failed: {e}")
        return []
