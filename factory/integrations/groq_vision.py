"""
AI Factory Pipeline v5.8.16 — Groq Vision Provider

Groq hosts Llama 4 Scout / Maverick which support multimodal (image + text)
input. Combined with Groq's extremely low-latency inference this gives the
fastest free vision analysis in the chain.

Free-tier limits (2026):
  14 400 requests/day — no credit card required
  Llama 4 Scout 17B: fast, good at UI analysis
  Llama 4 Maverick 17B: higher quality (more context tokens used)

Required env var:
  GROQ_API_KEY — get at https://console.groq.com

API: OpenAI-compatible, image_url content blocks.
Docs: https://console.groq.com/docs/vision

Cost: $0.00 within free tier.
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.groq_vision")

_GROQ_VISION_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

# Preferred vision models (in quality order)
_VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]

GROQ_VISION_COST: float = 0.0001  # nominal — free tier


def _api_key() -> str:
    return os.getenv("GROQ_API_KEY", "")


def is_available() -> bool:
    if is_mock_provider():
        return True
    return bool(_api_key())


async def describe_image(
    image_bytes: bytes,
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Describe or analyse an image using Groq's vision-enabled Llama 4.

    Args:
        image_bytes: Raw PNG or JPEG bytes.
        prompt:      Analysis instruction.
        model:       Model id (None → use Scout by default).
        max_tokens:  Maximum output tokens.

    Returns:
        Model response text.

    Raises:
        ValueError: GROQ_API_KEY not configured.
        Exception:  HTTP/API errors.
    """
    if is_mock_provider():
        return f"[MOCK:groq_vision] {prompt[:60]}"

    api_key = _api_key()
    if not api_key:
        raise ValueError("GROQ_API_KEY not configured")

    img_type = "jpeg" if image_bytes[:2] == b"\xff\xd8" else "png"
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    models_to_try = [model] if model else _VISION_MODELS
    last_error = ""

    import httpx
    for mdl in models_to_try:
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
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    _GROQ_VISION_ENDPOINT, headers=headers, json=payload
                )
            if resp.status_code == 429:
                raise Exception(f"429 rate-limited — {mdl}")
            if resp.status_code in (401, 403):
                raise ValueError(f"{resp.status_code} Unauthorized — check GROQ_API_KEY")
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            logger.info("[groq_vision] %s: %d chars", mdl, len(text))
            return text
        except Exception as e:
            last_error = str(e)
            logger.warning("[groq_vision] %s failed: %s", mdl, e)

    raise Exception(f"All Groq vision models failed. Last: {last_error}")


async def analyze_ui_screenshot(screenshot_bytes: bytes, task: str = "") -> str:
    """Specialised UI/UX screen analysis prompt."""
    prompt = (
        (f"Task: {task}\n\n" if task else "") +
        "Analyse this UI screenshot. List all interactive elements (buttons, "
        "inputs, menus, links), describe the layout, navigation structure, "
        "color scheme, and any UX issues. One element per line."
    )
    return await describe_image(screenshot_bytes, prompt)


async def plan_ui_action(
    screenshot_bytes: bytes,
    instruction: str,
    history: list[dict] | None = None,
) -> dict:
    """Plan the next UI interaction action from a screenshot."""
    history_text = ""
    if history:
        history_text = "Previous actions:\n" + "\n".join(
            f"  {i+1}. {h.get('action','?')} on {h.get('target','?')}"
            for i, h in enumerate(history[-5:])
        ) + "\n\n"

    prompt = (
        f"{history_text}"
        f"Task: {instruction}\n\n"
        "What is the SINGLE best next UI action? "
        'JSON only: {"action":"click|type|scroll|done|fail",'
        '"target":"element description","value":null,"reasoning":"brief"}'
    )
    import json, re
    raw = await describe_image(screenshot_bytes, prompt)
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            parsed["source"] = "groq_vision"
            return parsed
        except json.JSONDecodeError:
            pass
    return {
        "action": "fail", "target": None, "value": None,
        "reasoning": f"Parse failed: {raw[:200]}",
        "source": "groq_vision",
    }
