"""
AI Factory Pipeline v5.8.12 — NVIDIA NIM Vision Provider

Multimodal vision-language models for UI analysis, screenshot parsing,
design review, and visual QA tasks.

Models (quality order):
  meta/llama-3.2-90b-vision-instruct   — highest accuracy, slower
  nvidia/nemotron-nano-12b-v2-vl       — good balance, faster
  microsoft/phi-4-multimodal-instruct  — efficient, broad modality support

Endpoint: https://integrate.api.nvidia.com/v1/chat/completions (OpenAI-compatible)

Required env var:
  NVIDIA_NIM_VISION_API_KEY — covers all vision models
  NVIDIA_NIM_MULTI_API_KEY  — fallback

Pipeline uses:
  - S3 Design: review generated UI screenshots
  - S6 Test: visual regression descriptions
  - Legal: parse images from legal documents
  - OmniParser bridge: pre-process screenshots before UI element extraction
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.nvidia_nim_vision")

NVIDIA_VISION_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"

_VISION_MODELS = [
    "meta/llama-3.2-90b-vision-instruct",
    "nvidia/nemotron-nano-12b-v2-vl",
    "microsoft/phi-4-multimodal-instruct",
]


def _get_api_key() -> str:
    return (
        os.getenv("NVIDIA_NIM_VISION_API_KEY", "")
        or os.getenv("NVIDIA_NIM_MULTI_API_KEY", "")
        or os.getenv("NVIDIA_NIM_API_KEY", "")
    )


async def describe_image(
    image_bytes: bytes,
    prompt: str = "Describe this UI screenshot in detail.",
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Describe or analyze an image using a vision-language model.

    Args:
        image_bytes: Raw PNG/JPEG image bytes.
        prompt: Instruction for the model.
        model: Specific model to use (None = try chain in order).
        max_tokens: Maximum response length.

    Returns:
        Model's description/analysis text.
    """
    if is_mock_provider():
        return f"[MOCK:vision] {prompt[:60]}"

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("No NVIDIA NIM vision API key configured")

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    # Detect format from bytes header
    img_type = "jpeg" if image_bytes[:2] == b"\xff\xd8" else "png"

    models_to_try = [model] if model else _VISION_MODELS
    last_error = ""

    for model_id in models_to_try:
        try:
            result = await _call_vision(b64_image, img_type, prompt, model_id, api_key, max_tokens)
            return result
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[nvidia_nim_vision] {model_id} failed: {e}")

    raise Exception(f"All vision models failed. Last error: {last_error}")


async def _call_vision(
    b64_image: str,
    img_type: str,
    prompt: str,
    model: str,
    api_key: str,
    max_tokens: int,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{img_type};base64,{b64_image}",
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
    }

    logger.debug(f"[nvidia_nim_vision] calling {model}")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(NVIDIA_VISION_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception(f"429 Rate Limited — {model}")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check NVIDIA_NIM_VISION_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.debug(f"[nvidia_nim_vision] {model}: {len(text)} chars")
    return text


async def analyze_ui_screenshot(screenshot_bytes: bytes, app_name: str = "") -> str:
    """Specialized prompt for UI/UX analysis of app screenshots."""
    prompt = (
        f"Analyze this {'app ' if app_name else ''}UI screenshot"
        f"{' for ' + app_name if app_name else ''}. "
        "Identify: layout structure, navigation elements, key interactive components, "
        "color scheme, accessibility concerns, and UX quality. "
        "Be specific and actionable."
    )
    return await describe_image(screenshot_bytes, prompt=prompt)
