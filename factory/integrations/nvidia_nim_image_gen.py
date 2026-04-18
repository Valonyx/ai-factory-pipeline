"""
AI Factory Pipeline v5.8.12 — NVIDIA NIM FLUX Image Generation

Black Forest Labs FLUX models via NVIDIA's GenAI API.
These models use a different endpoint than the chat/completion NIM models.

Models (speed/quality tradeoffs):
  flux.2-klein-4b    — fastest, lowest resource, good for icons/mockups
  flux.1-schnell     — fast, good quality, ideal for UI screens
  flux.1-dev         — best quality, slower, for hero images and logos
  flux.1-kontext-dev — image editing/context-aware generation

Endpoint: https://ai.api.nvidia.com/v1/genai/black-forest-labs/<model>

Required env var:
  NVIDIA_NIM_MULTI_API_KEY — shared key covering all FLUX models

Returns raw bytes (PNG).
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.nvidia_nim_image_gen")

NVIDIA_GENAI_BASE = "https://ai.api.nvidia.com/v1/genai/black-forest-labs"

_FLUX_MODELS = {
    "fast":    "flux.2-klein-4b",
    "schnell": "flux.1-schnell",
    "quality": "flux.1-dev",
    "edit":    "flux.1-kontext-dev",
}


def _get_api_key() -> str:
    return os.getenv("NVIDIA_NIM_MULTI_API_KEY", "") or os.getenv("NVIDIA_NIM_API_KEY", "")


async def generate_image_flux(
    prompt: str,
    quality: str = "schnell",
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    num_inference_steps: int = 20,
) -> Optional[bytes]:
    """Generate an image using FLUX via NVIDIA NIM GenAI.

    Args:
        prompt: Text description.
        quality: "fast" | "schnell" | "quality" | "edit"
        width: Image width (must be multiple of 64).
        height: Image height (must be multiple of 64).
        seed: Optional reproducibility seed.
        num_inference_steps: Steps (higher = better quality, slower).

    Returns:
        PNG bytes, or None if generation fails.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        logger.debug("[nvidia_nim_image_gen] mock mode")
        return None

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("NVIDIA_NIM_MULTI_API_KEY not configured — cannot use FLUX")

    model_name = _FLUX_MODELS.get(quality, _FLUX_MODELS["schnell"])
    endpoint = f"{NVIDIA_GENAI_BASE}/{model_name}"

    # Snap dimensions to multiples of 64
    width = max(64, (width // 64) * 64)
    height = max(64, (height // 64) * 64)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": 3.5,
    }
    if seed is not None:
        payload["seed"] = seed

    logger.debug(f"[nvidia_nim_image_gen] calling {model_name} — {width}×{height}")

    import httpx
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(endpoint, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception(f"429 Rate Limited — FLUX {model_name}")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check NVIDIA_NIM_MULTI_API_KEY")
    response.raise_for_status()

    data = response.json()
    # Response may be base64 or URL depending on model
    artifacts = data.get("artifacts") or data.get("images") or []
    if artifacts:
        b64 = artifacts[0].get("base64") or artifacts[0].get("b64_json") or ""
        if b64:
            return base64.b64decode(b64)

    # Some FLUX models return image_url
    image_url = (data.get("data") or [{}])[0].get("url", "")
    if image_url:
        async with httpx.AsyncClient(timeout=30) as client:
            img_response = await client.get(image_url)
        img_response.raise_for_status()
        return img_response.content

    logger.warning(f"[nvidia_nim_image_gen] unexpected response structure: {list(data.keys())}")
    return None
