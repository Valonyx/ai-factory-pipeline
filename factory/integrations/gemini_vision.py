"""
AI Factory Pipeline v5.8.16 — Google Gemini Vision Provider

Gemini 2.0 Flash supports multimodal input (text + images) on the free tier.

Free-tier limits (2026):
  gemini-2.0-flash: 1 500 RPD, 1 M TPM — free at aistudio.google.com
  gemini-2.5-flash: 500 RPD — higher quality, same free tier
  No credit card required.

Required env var:
  GEMINI_API_KEY — get at https://aistudio.google.com

Endpoint (REST, no extra SDK needed):
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}

Cost: $0.00 within free-tier limits.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.gemini_vision")

_GEMINI_VISION_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Prefer 2.0-flash (higher RPD) for vision; fall back to 2.5-flash for quality
_DEFAULT_VISION_MODEL = "gemini-2.0-flash"
_FALLBACK_VISION_MODEL = "gemini-2.5-flash-lite-preview-06-17"

GEMINI_VISION_COST: float = 0.0001  # nominal — within free tier


def _api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def is_available() -> bool:
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return True
    return bool(_api_key())


async def describe_image(
    image_bytes: bytes,
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Describe or analyse an image using Gemini Vision.

    Args:
        image_bytes: Raw PNG or JPEG bytes.
        prompt:      Analysis instruction.
        model:       Gemini model id (None → use default).
        max_tokens:  Maximum output tokens.

    Returns:
        Model response text.

    Raises:
        ValueError: GEMINI_API_KEY not configured.
        Exception:  HTTP/API errors (caller should catch and cascade).
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return f"[MOCK:gemini_vision] {prompt[:60]}"

    api_key = _api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    media_type = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": media_type, "data": b64_data}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2},
    }

    chosen = model or _DEFAULT_VISION_MODEL
    url = f"{_GEMINI_VISION_ENDPOINT.format(model=chosen)}?key={api_key}"

    import httpx
    for attempt_model in [chosen, _FALLBACK_VISION_MODEL]:
        try:
            u = f"{_GEMINI_VISION_ENDPOINT.format(model=attempt_model)}?key={api_key}"
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(u, json=payload)
            if resp.status_code == 429:
                raise Exception(f"429 rate-limited — {attempt_model}")
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            logger.info("[gemini_vision] %s: %d chars", attempt_model, len(text))
            return text
        except Exception as e:
            logger.warning("[gemini_vision] %s failed: %s", attempt_model, e)
            if attempt_model == _FALLBACK_VISION_MODEL:
                raise

    raise Exception("All Gemini vision models failed")


async def analyze_ui_screenshot(screenshot_bytes: bytes, task: str = "") -> str:
    """Specialised prompt for UI/UX screen analysis."""
    prompt = (
        f"Task: {task}\n\n" if task else ""
    ) + (
        "Analyse this UI screenshot. Identify: layout structure, navigation elements, "
        "interactive components (buttons, inputs, links), color scheme, typography, "
        "spacing, and any UX issues. Be specific and concise."
    )
    return await describe_image(screenshot_bytes, prompt)


async def plan_ui_action(
    screenshot_bytes: bytes,
    instruction: str,
    history: list[dict] | None = None,
) -> dict:
    """Suggest the next UI action to accomplish an instruction.

    Returns dict: {"action", "target", "value", "reasoning"}.
    """
    history_text = ""
    if history:
        history_text = "Previous actions:\n" + "\n".join(
            f"  {i+1}. {h.get('action','?')} on {h.get('target','?')}"
            for i, h in enumerate(history[-5:])
        ) + "\n\n"

    prompt = (
        f"{history_text}"
        f"Task: {instruction}\n\n"
        "Looking at this UI screenshot, what is the SINGLE best next action? "
        'Reply with JSON only: {"action":"click|type|scroll|done|fail",'
        '"target":"element description","value":null,"reasoning":"brief reason"}'
    )
    import json, re
    raw = await describe_image(screenshot_bytes, prompt)
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            parsed["source"] = "gemini_vision"
            return parsed
        except json.JSONDecodeError:
            pass
    return {
        "action": "fail",
        "target": None,
        "value": None,
        "reasoning": f"Gemini response parse failed: {raw[:200]}",
        "source": "gemini_vision",
    }
