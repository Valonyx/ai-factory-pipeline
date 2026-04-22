"""
AI Factory Pipeline v5.8.16 — Qwen2.5-VL UI Agent Provider (via OpenRouter)

Qwen2.5-VL-72B is one of the strongest open-source vision-language models
for GUI understanding, UI element grounding, and action prediction tasks.
It is available for FREE on OpenRouter with the `:free` suffix.

Free tier:
  qwen/qwen2.5-vl-72b-instruct:free — $0 per token (rate-limited)
  qwen/qwen2.5-vl-7b-instruct:free  — smaller, faster fallback

Required env var:
  OPENROUTER_API_KEY — get at https://openrouter.ai (free sign-up)

API: OpenAI-compatible with image_url content blocks.
Docs: https://openrouter.ai/docs/multimodal-requests

Capabilities:
  - UI element detection and labelling
  - Bounding box estimation (coordinate normalised 0–1)
  - Action prediction (click, type, scroll, swipe)
  - Multi-turn GUI agent conversation

Cost: $0.00 within free-tier limits.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger("factory.integrations.qwen_vl_agent")

_OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Model priority: 72B for quality, 7B as fast fallback
_VL_MODELS = [
    "qwen/qwen2.5-vl-72b-instruct:free",
    "qwen/qwen2.5-vl-7b-instruct:free",
]

QWEN_VL_COST: float = 0.0  # free tier


def _api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


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
    """Analyse an image using Qwen2.5-VL via OpenRouter.

    Returns model response text.
    Raises ValueError if OPENROUTER_API_KEY is missing.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return f"[MOCK:qwen_vl] {prompt[:60]}"

    api_key = _api_key()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    img_type = "jpeg" if image_bytes[:2] == b"\xff\xd8" else "png"
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ai-factory-pipeline",
        "X-Title": "AI Factory Pipeline",
    }

    models = [model] if model else _VL_MODELS
    last_error = ""

    import httpx
    for mdl in models:
        payload = {
            "model": mdl,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{img_type};base64,{b64_data}"
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    _OPENROUTER_ENDPOINT, headers=headers, json=payload
                )
            if resp.status_code == 429:
                raise Exception(f"429 rate-limited — {mdl}")
            if resp.status_code in (401, 403):
                raise ValueError(
                    f"{resp.status_code} Unauthorized — check OPENROUTER_API_KEY"
                )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            logger.info("[qwen_vl] %s: %d chars", mdl, len(text))
            return text
        except Exception as e:
            last_error = str(e)
            logger.warning("[qwen_vl] %s failed: %s", mdl, e)

    raise Exception(f"All Qwen VL models failed. Last: {last_error}")


async def parse_ui_elements(screenshot_bytes: bytes) -> list[dict]:
    """Extract all visible UI elements from a screenshot.

    Returns list of dicts: {"label", "type", "bbox": [x1,y1,x2,y2], "text"}.
    Coordinates are normalised 0–1.
    """
    prompt = (
        "Analyse this UI screenshot. List EVERY interactive element you see.\n"
        "For each element output one JSON object per line:\n"
        '{"label":"element name","type":"button|input|link|icon|tab|menu|text","'
        'bbox":[x1,y1,x2,y2],"text":"visible text or empty"}\n'
        "Coordinates must be normalised 0.0–1.0 relative to image dimensions.\n"
        "Only output JSON lines, no other text."
    )
    raw = await describe_image(screenshot_bytes, prompt)
    elements: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            elements.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return elements


async def plan_ui_action(
    screenshot_bytes: bytes,
    instruction: str,
    history: Optional[list[dict]] = None,
) -> dict:
    """Plan the next GUI action to accomplish an instruction.

    Returns:
        {
          "action":    "click" | "type" | "scroll" | "done" | "fail",
          "target":    element description,
          "coordinates": [x, y] normalised 0–1 (if available),
          "value":     text to type or scroll direction (if applicable),
          "reasoning": model's chain-of-thought,
          "source":    "qwen_vl",
        }
    """
    history_text = ""
    if history:
        history_text = "Completed steps:\n" + "\n".join(
            f"  {i+1}. {h.get('action','?')} → {h.get('target','?')}"
            for i, h in enumerate(history[-6:])
        ) + "\n\n"

    prompt = (
        f"{history_text}"
        f"Goal: {instruction}\n\n"
        "Look at the current UI screenshot.\n"
        "What is the SINGLE most effective next action?\n"
        "Reply with JSON only:\n"
        '{"action":"click|type|scroll|done|fail",'
        '"target":"element description",'
        '"coordinates":[x,y],'
        '"value":null,"reasoning":"brief explanation"}'
        "\n(coordinates normalised 0–1, null if unknown)"
    )
    raw = await describe_image(screenshot_bytes, prompt, max_tokens=512)

    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            parsed["source"] = "qwen_vl"
            return parsed
        except json.JSONDecodeError:
            pass

    return {
        "action": "fail",
        "target": None,
        "coordinates": None,
        "value": None,
        "reasoning": f"Qwen VL response parse failed: {raw[:200]}",
        "source": "qwen_vl",
    }
