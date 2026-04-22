"""
AI Factory Pipeline v5.8.16 — Cloudflare Workers AI Vision Provider

Cloudflare Workers AI hosts Llama 3.2 11B Vision Instruct on their global
edge network. The free tier offers 10 000 neurons/day at $0 cost.

Free tier: https://dash.cloudflare.com — no credit card required.

Required env vars:
  CLOUDFLARE_ACCOUNT_ID  — your account ID (dash.cloudflare.com → right sidebar)
  CLOUDFLARE_API_TOKEN   — Workers AI token (Dashboard → API Tokens)

Model: @cf/meta/llama-3.2-11b-vision-instruct
  — Llama 3.2 11B with multimodal vision support
  — Fast inference on Cloudflare's edge network worldwide

Endpoint: POST https://api.cloudflare.com/client/v4/accounts/{id}/ai/run/{model}
Docs: https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/

Cost: $0.00 within free-tier limits.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.cloudflare_vision")

_CF_BASE = "https://api.cloudflare.com/client/v4/accounts"
_CF_VISION_MODEL = "@cf/meta/llama-3.2-11b-vision-instruct"

CF_VISION_COST: float = 0.0  # free tier


def _credentials() -> tuple[str, str]:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    return account_id, api_token


def is_available() -> bool:
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return True
    account_id, api_token = _credentials()
    return bool(account_id and api_token)


async def describe_image(
    image_bytes: bytes,
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Describe or analyse an image using Cloudflare Workers AI Vision.

    Args:
        image_bytes: Raw PNG or JPEG bytes.
        prompt:      Analysis instruction.
        model:       CF model id (None → use default Llama 3.2 vision).
        max_tokens:  Maximum output tokens.

    Returns:
        Model response text.

    Raises:
        ValueError: Credentials not configured.
        Exception:  HTTP/API errors.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return f"[MOCK:cloudflare_vision] {prompt[:60]}"

    account_id, api_token = _credentials()
    if not account_id or not api_token:
        raise ValueError(
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN required"
        )

    img_type = "jpeg" if image_bytes[:2] == b"\xff\xd8" else "png"
    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    chosen_model = model or _CF_VISION_MODEL

    # Cloudflare uses OpenAI-compatible messages format for vision models
    payload = {
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
    }

    url = f"{_CF_BASE}/{account_id}/ai/run/{chosen_model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    import httpx
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code == 429:
        raise Exception("429 rate-limited — Cloudflare Workers AI")
    if resp.status_code in (401, 403):
        raise ValueError(
            f"{resp.status_code} Unauthorized — check CLOUDFLARE_API_TOKEN"
        )
    resp.raise_for_status()

    data = resp.json()
    # Response can be {"result": {"response": "..."}} or OpenAI-style choices
    if "result" in data and "response" in data.get("result", {}):
        text = data["result"]["response"]
    elif "choices" in data:
        text = data["choices"][0]["message"]["content"]
    else:
        raise Exception(f"Unexpected Cloudflare response shape: {list(data.keys())}")

    logger.info("[cloudflare_vision] %s: %d chars", chosen_model, len(text))
    return text


async def analyze_ui_screenshot(screenshot_bytes: bytes, task: str = "") -> str:
    """Specialised UI/UX analysis prompt for Cloudflare Workers AI."""
    prompt = (
        (f"Task: {task}\n\n" if task else "") +
        "Analyse this UI screenshot. Identify all interactive elements, describe "
        "the layout, navigation, color palette, and any accessibility concerns."
    )
    return await describe_image(screenshot_bytes, prompt)


async def plan_ui_action(
    screenshot_bytes: bytes,
    instruction: str,
    history: list[dict] | None = None,
) -> dict:
    """Plan the next UI interaction from a screenshot."""
    history_text = ""
    if history:
        history_text = "Previous actions:\n" + "\n".join(
            f"  {i+1}. {h.get('action','?')} → {h.get('target','?')}"
            for i, h in enumerate(history[-5:])
        ) + "\n\n"

    prompt = (
        f"{history_text}"
        f"Task: {instruction}\n\n"
        "Next single UI action? "
        'JSON only: {"action":"click|type|scroll|done|fail",'
        '"target":"element","value":null,"reasoning":"brief"}'
    )
    import json, re
    raw = await describe_image(screenshot_bytes, prompt)
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            parsed["source"] = "cloudflare_vision"
            return parsed
        except json.JSONDecodeError:
            pass
    return {
        "action": "fail", "target": None, "value": None,
        "reasoning": f"Parse failed: {raw[:200]}",
        "source": "cloudflare_vision",
    }
