"""
AI Factory Pipeline v5.8.16 — UI Agent Chain (UI-TARS-like, 4 Free Providers)

GUI understanding and action-planning chain. Given a screenshot + instruction,
returns a structured action dict (click / type / scroll / done / fail) with
reasoning. Providers are tried in priority order; all are free-tier.

Provider roster:
  1. Qwen2.5-VL-72B via OpenRouter  — best open-source GUI agent (~UI-TARS class)
     Key: OPENROUTER_API_KEY
     Register: https://openrouter.ai

  2. UI-TARS (self-hosted / ByteDance)  — specialised GUI agent, if endpoint set
     Keys: UI_TARS_ENDPOINT + (optional) UI_TARS_API_KEY
     Docs: https://github.com/bytedance/ui-tars

  3. Google Gemini Vision             — strong zero-shot UI reasoning (free)
     Key: GEMINI_API_KEY
     Register: https://aistudio.google.com

  4. NVIDIA NIM Llama 3.2 Vision      — reliable fallback (free with NIM key)
     Key: NVIDIA_NIM_VISION_API_KEY | NVIDIA_NIM_API_KEY
     Register: https://build.nvidia.com

BASIC-mode note: all 4 providers are free — every mode gets real results.
Failed providers set source="degraded" and action="fail"; the stage is not
halted so the pipeline can degrade gracefully during development.

Spec Authority: v5.8.16 §G4 (UI-agent gap closure)
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.ui_agent_chain")

# Configurable via env var (comma-separated provider names)
_AGENT_CHAIN: list[str] = [
    p.strip()
    for p in os.getenv(
        "UI_AGENT_PROVIDER_CHAIN",
        "qwen_vl,ui_tars,gemini_vision,nvidia_nim_vision",
    ).split(",")
    if p.strip()
]


# ── Public API ───────────────────────────────────────────────────────────────


async def plan_ui_action(
    screenshot_bytes: bytes,
    instruction: str,
    history: Optional[list[dict]] = None,
    mode: str = "balanced",
) -> dict:
    """Plan the next GUI action from a screenshot + instruction.

    Tries providers in priority order; returns first success.
    On all-fail returns a typed degraded result (action="fail").

    Args:
        screenshot_bytes: Current screen state as PNG/JPEG bytes.
        instruction:      Goal the agent should accomplish.
        history:          Prior action list (for multi-step context).
        mode:             "basic" | "balanced" | "custom" | "turbo".

    Returns:
        {
          "action":      "click" | "type" | "scroll" | "done" | "fail",
          "target":      element description or None,
          "coordinates": [x, y] normalised 0–1, or None,
          "value":       text to type / scroll amount, or None,
          "reasoning":   model's chain-of-thought,
          "source":      provider name,
          "degraded":    True only when all providers failed,
        }
    """
    if is_mock_provider():
        return {
            "action": "done",
            "target": None,
            "coordinates": None,
            "value": None,
            "reasoning": "[MOCK] UI action planned",
            "source": "mock",
            "degraded": False,
        }

    hist = history or []
    errors: list[str] = []

    for provider in _AGENT_CHAIN:
        try:
            result = await _call_agent_provider(
                provider, screenshot_bytes, instruction, hist
            )
            result.setdefault("coordinates", None)
            result["degraded"] = False
            logger.info("[ui_agent_chain] %s succeeded → action=%s", provider, result.get("action"))
            _track_cost(provider)
            return result
        except Exception as e:
            err = f"{provider}: {e}"
            errors.append(err)
            logger.warning("[ui_agent_chain] %s", err)

    logger.error("[ui_agent_chain] All providers failed: %s", "; ".join(errors))
    return {
        "action": "fail",
        "target": None,
        "coordinates": None,
        "value": None,
        "reasoning": "All UI agent providers failed: " + "; ".join(errors),
        "source": "degraded",
        "degraded": True,
    }


async def parse_screen_elements(
    screenshot_bytes: bytes,
    mode: str = "balanced",
) -> list[dict]:
    """Extract all visible UI elements from a screenshot.

    Returns list of dicts: {"label", "type", "bbox", "text"}.
    Uses Qwen2.5-VL (best at element grounding) then falls back to OmniParser.
    """
    if is_mock_provider():
        return [{"label": "button", "type": "button", "bbox": [0, 0, 1, 1], "text": "Submit"}]

    for provider in _AGENT_CHAIN:
        try:
            if provider == "qwen_vl":
                from factory.integrations.qwen_vl_agent import parse_ui_elements
                return await parse_ui_elements(screenshot_bytes)
            if provider in ("ui_tars", "omniparser"):
                from factory.integrations.omniparser import parse_screenshot
                result = await parse_screenshot(screenshot_bytes)
                return result.get("elements", [])
            # Other providers: use vision chain for a description, return empty elements
            continue
        except Exception as e:
            logger.warning("[ui_agent_chain] parse_screen_elements %s failed: %s", provider, e)

    return []


# ── Provider dispatch ────────────────────────────────────────────────────────


async def _call_agent_provider(
    provider: str,
    screenshot_bytes: bytes,
    instruction: str,
    history: list[dict],
) -> dict:
    if provider == "qwen_vl":
        from factory.integrations.qwen_vl_agent import plan_ui_action
        return await plan_ui_action(screenshot_bytes, instruction, history)

    if provider == "ui_tars":
        from factory.integrations.ui_tars import _call_ui_tars, is_available
        if not is_available():
            raise ValueError("UI-TARS endpoint not configured (UI_TARS_ENABLED + UI_TARS_ENDPOINT)")
        return await _call_ui_tars(screenshot_bytes, instruction, history)

    if provider == "gemini_vision":
        from factory.integrations.gemini_vision import plan_ui_action
        return await plan_ui_action(screenshot_bytes, instruction, history)

    if provider == "nvidia_nim_vision":
        # NIM vision returns description; wrap as structured action
        from factory.integrations.nvidia_nim_vision import describe_image
        import json, re
        prompt = (
            f"Task: {instruction}\n\n"
            "What is the next single UI action? "
            'JSON only: {"action":"click|type|scroll|done|fail",'
            '"target":"element","value":null,"reasoning":"brief"}'
        )
        raw = await describe_image(screenshot_bytes, prompt)
        match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            parsed["source"] = "nvidia_nim_vision"
            return parsed
        raise ValueError(f"NIM vision parse failed: {raw[:100]}")

    if provider == "groq_vision":
        from factory.integrations.groq_vision import plan_ui_action
        return await plan_ui_action(screenshot_bytes, instruction, history)

    if provider == "cloudflare_vision":
        from factory.integrations.cloudflare_vision import plan_ui_action
        return await plan_ui_action(screenshot_bytes, instruction, history)

    raise ValueError(f"Unknown UI agent provider: {provider}")


# ── Cost tracking ────────────────────────────────────────────────────────────

_PROVIDER_COST: dict[str, float] = {
    "qwen_vl":           0.0,
    "ui_tars":           0.0,
    "gemini_vision":     0.0001,
    "nvidia_nim_vision": 0.0001,
    "groq_vision":       0.0001,
    "cloudflare_vision": 0.0,
}


def _track_cost(provider: str) -> None:
    try:
        from factory.core.quota_tracker import get_quota_tracker
        import asyncio
        qt = get_quota_tracker()
        asyncio.create_task(
            qt.record_usage(provider, tokens=0, calls=1,
                            cost_usd=_PROVIDER_COST.get(provider, 0.0))
        )
    except Exception:
        pass
