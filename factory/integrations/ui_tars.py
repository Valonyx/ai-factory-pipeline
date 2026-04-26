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

from factory.core.dry_run import is_mock_provider

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
    if is_mock_provider():
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
    """Call the UI-TARS server via OpenAI-compatible chat completions API.

    UI-TARS is deployed as a TGI (Text Generation Inference) server on
    HuggingFace Inference Endpoints. The model ID for TGI is always "tgi".

    The response is parsed by the action_parser from vendor/ui-tars.
    """
    endpoint = os.getenv("UI_TARS_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("UI_TARS_API_KEY", "")
    img_height = int(os.getenv("UI_TARS_IMG_HEIGHT", "1080"))
    img_width = int(os.getenv("UI_TARS_IMG_WIDTH", "1920"))

    b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
    img_type = "jpeg" if screenshot_bytes[:2] == b"\xff\xd8" else "png"

    # Build system prompt using UI-TARS prompt templates
    system_prompt = _get_uitars_system_prompt()

    # Build history-aware user content
    history_lines = ""
    if history:
        history_lines = "Previous actions:\n" + "\n".join(
            f"  {i+1}. {h.get('action','?')} → {h.get('target','?')}"
            for i, h in enumerate(history[-6:])
        ) + "\n\n"

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"{history_lines}Task: {instruction}"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{img_type};base64,{b64_image}"},
                },
            ],
        },
    ]

    import httpx
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{endpoint}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json",
            },
            json={
                "model": "tgi",
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 400,
                "stream": False,
            },
        )

    response.raise_for_status()
    raw_text = response.json()["choices"][0]["message"]["content"]

    # Parse UI-TARS action output using vendor action_parser
    parsed_actions = _parse_uitars_response(raw_text, img_height, img_width)
    if not parsed_actions:
        return {
            "action": "fail",
            "target": None,
            "coordinates": None,
            "value": None,
            "reasoning": f"UI-TARS parse failed: {raw_text[:200]}",
            "source": "ui_tars",
        }

    act = parsed_actions[0]
    action_type = act.get("action_type", "fail").lower()
    inputs = act.get("action_inputs", {})

    # Normalise to pipeline action dict
    coordinates = None
    if "start_box" in inputs:
        try:
            raw_box = inputs["start_box"].strip("[]()").split(",")
            cx = float(raw_box[0].strip())
            cy = float(raw_box[1].strip())
            # UI-TARS outputs 0-1 normalised coords
            coordinates = [cx, cy]
        except (ValueError, IndexError):
            pass

    return {
        "action": action_type if action_type in ("click", "type", "scroll", "finished", "fail") else "click",
        "target": inputs.get("element", inputs.get("text", "")),
        "coordinates": coordinates,
        "value": inputs.get("text", inputs.get("content", None)),
        "reasoning": act.get("thought", raw_text[:300]),
        "source": "ui_tars",
    }


def _get_uitars_system_prompt() -> str:
    """Load UI-TARS system prompt from vendor package, fallback to compact version."""
    try:
        import sys
        import os as _os
        _script_dir = _os.path.dirname(_os.path.abspath(__file__))
        _project_root = _os.path.dirname(_os.path.dirname(_script_dir))
        _vendor = _os.path.join(_project_root, "vendor", "ui-tars", "codes")
        if _vendor not in sys.path:
            sys.path.insert(0, _vendor)
        from ui_tars.prompt import COMPUTER_USE_DOUBAO  # type: ignore[import]
        return COMPUTER_USE_DOUBAO
    except Exception:
        return (
            "You are a GUI agent. Given a screenshot, determine the next action.\n"
            "Think step by step. Output: Thought: <reasoning>\nAction: <action_call>"
        )


def _parse_uitars_response(raw_text: str, img_height: int, img_width: int) -> list[dict]:
    """Parse UI-TARS model output using vendor action_parser."""
    try:
        import sys
        import os as _os
        _script_dir = _os.path.dirname(_os.path.abspath(__file__))
        _project_root = _os.path.dirname(_os.path.dirname(_script_dir))
        _vendor = _os.path.join(_project_root, "vendor", "ui-tars", "codes")
        if _vendor not in sys.path:
            sys.path.insert(0, _vendor)
        from ui_tars.action_parser import parse_action_to_structure_output  # type: ignore[import]
        return parse_action_to_structure_output(
            raw_text,
            factor=1000,
            origin_resized_height=img_height,
            origin_resized_width=img_width,
        )
    except Exception as e:
        logger.warning("[ui_tars] action_parser import failed: %s", e)
        # Minimal fallback parser: extract action type from raw text
        import re
        match = re.search(r"Action:\s*(\w+)\(", raw_text)
        if match:
            return [{"action_type": match.group(1), "action_inputs": {}, "thought": raw_text[:300]}]
        return []


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
