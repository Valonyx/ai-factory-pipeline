"""
AI Factory Pipeline v5.8 — Free Image Generation Chain

Resilient chain of free/low-cost image generation providers:
  1. Pollinations.ai — completely free, no API key, no signup
  2. Hugging Face Inference API — free tier with key (FLUX.1-schnell)
  3. Together AI — uses existing TOGETHER_API_KEY for image generation

Used by: factory/design/logo_gen.py, factory/pipeline/s2_blueprint.py

Each provider returns raw image bytes (PNG).
On failure the chain automatically tries the next provider.
Returns None only if every provider fails.

Spec Authority: v5.8 §4.3.1 (Design Asset Generation)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger("factory.integrations.image_gen")


# ═══════════════════════════════════════════════════════════════════
# Provider Chain
# ═══════════════════════════════════════════════════════════════════

_IMAGE_PROVIDER_CHAIN: list[str] = [
    p.strip()
    for p in os.getenv("IMAGE_PROVIDER_CHAIN", "pollinations,huggingface,together").split(",")
    if p.strip()
]


async def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    style: str = "",
    seed: Optional[int] = None,
) -> Optional[bytes]:
    """Generate an image using the free provider chain.

    Tries each provider in order until one succeeds.

    Args:
        prompt: Text description of the desired image.
        width: Image width in pixels.
        height: Image height in pixels.
        style: Optional style suffix (e.g. "flat icon, minimal, vector").
        seed: Optional seed for reproducible output.

    Returns:
        Raw PNG/JPEG bytes, or None if all providers fail.
    """
    # ── Mock / CI short-circuit ──
    # When AI_PROVIDER=mock or DRY_RUN=true, skip real HTTPS calls entirely.
    # Tests and CI runs should never hit pollinations.ai / HuggingFace / Together.
    if (
        os.getenv("AI_PROVIDER", "").lower() == "mock"
        or os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
        or os.getenv("IMAGE_PROVIDER_CHAIN", "").lower() == "mock"
    ):
        logger.info("[image_gen] Mock/dry-run mode — skipping real image generation")
        return None

    full_prompt = f"{prompt}, {style}" if style else prompt
    _seed = seed or int(time.time()) % 999999

    tried: list[str] = []
    for provider in _IMAGE_PROVIDER_CHAIN:
        if provider in tried:
            continue
        tried.append(provider)
        try:
            result = await _call_provider(provider, full_prompt, width, height, _seed)
            if result:
                logger.info(f"[image_gen] {provider} succeeded ({len(result)} bytes)")
                return result
        except Exception as e:
            logger.warning(f"[image_gen] {provider} failed: {e}")

    logger.error("[image_gen] All image providers failed")
    return None


async def _call_provider(
    provider: str,
    prompt: str,
    width: int,
    height: int,
    seed: int,
) -> Optional[bytes]:
    """Dispatch to a specific image provider."""
    if provider == "nvidia_nim_flux":
        from factory.integrations.nvidia_nim_image_gen import generate_image_flux
        return await generate_image_flux(prompt, quality="schnell", width=width, height=height, seed=seed)
    if provider == "pollinations":
        return await _call_pollinations(prompt, width, height, seed)
    if provider == "huggingface":
        return await _call_huggingface(prompt, width, height)
    if provider == "together":
        return await _call_together_image(prompt, width, height)
    raise ValueError(f"Unknown image provider: {provider}")


# ═══════════════════════════════════════════════════════════════════
# Provider 1: Pollinations.ai (Free, no API key)
# ═══════════════════════════════════════════════════════════════════

async def _call_pollinations(
    prompt: str,
    width: int,
    height: int,
    seed: int,
) -> Optional[bytes]:
    """Call Pollinations.ai image API — free, no key required.

    Endpoint: https://image.pollinations.ai/prompt/{encoded_prompt}
    Models: flux (default), turbo, flux-realism
    """
    encoded = urllib.parse.quote(prompt[:500], safe="")
    model = "flux"
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&seed={seed}"
        f"&model={model}&nologo=true&enhance=false"
    )

    def _fetch() -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Factory/5.8"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()

    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _fetch)
    if len(data) < 1000:  # sanity check — real images are much larger
        raise ValueError(f"Pollinations returned suspiciously small response: {len(data)} bytes")
    return data


# ═══════════════════════════════════════════════════════════════════
# Provider 2: Hugging Face Inference API (Free tier with key)
# ═══════════════════════════════════════════════════════════════════

async def _call_huggingface(
    prompt: str,
    width: int,
    height: int,
) -> Optional[bytes]:
    """Call Hugging Face Inference API with FLUX.1-schnell (free tier).

    Requires: HUGGINGFACE_API_KEY environment variable.
    Model: black-forest-labs/FLUX.1-schnell
    """
    api_key = os.getenv("HUGGINGFACE_API_KEY", "")
    if not api_key:
        raise ValueError("HUGGINGFACE_API_KEY not configured")

    import json as _json

    model = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    url = f"https://api-inference.huggingface.co/models/{model}"
    payload = _json.dumps({
        "inputs": prompt[:500],
        "parameters": {
            "width": min(width, 1024),
            "height": min(height, 1024),
            "num_inference_steps": 4,
        },
    }).encode()

    def _fetch() -> bytes:
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "image/png",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.read()

    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _fetch)
    if len(data) < 1000:
        raise ValueError(f"HuggingFace returned small response: {len(data)} bytes")
    return data


# ═══════════════════════════════════════════════════════════════════
# Provider 3: Together AI Image Generation
# ═══════════════════════════════════════════════════════════════════

async def _call_together_image(
    prompt: str,
    width: int,
    height: int,
) -> Optional[bytes]:
    """Generate image via Together AI (FLUX.1-schnell model).

    Requires: TOGETHER_API_KEY environment variable.
    Returns image bytes fetched from the result URL.
    """
    api_key = os.getenv("TOGETHER_API_KEY", "")
    if not api_key:
        raise ValueError("TOGETHER_API_KEY not configured")

    import json as _json

    payload = _json.dumps({
        "model": "black-forest-labs/FLUX.1-schnell-Free",
        "prompt": prompt[:500],
        "width": min(width, 1024),
        "height": min(height, 1024),
        "steps": 4,
        "n": 1,
        "response_format": "url",
    }).encode()

    def _fetch_url() -> str:
        req = urllib.request.Request(
            "https://api.together.xyz/v1/images/generations",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = _json.loads(resp.read())
        return body["data"][0]["url"]

    def _fetch_image(img_url: str) -> bytes:
        req = urllib.request.Request(img_url, headers={"User-Agent": "AI-Factory/5.6"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    loop = asyncio.get_running_loop()
    img_url = await loop.run_in_executor(None, _fetch_url)
    data = await loop.run_in_executor(None, _fetch_image, img_url)
    if len(data) < 1000:
        raise ValueError(f"Together image too small: {len(data)} bytes")
    return data


# ═══════════════════════════════════════════════════════════════════
# Utility: Build a good prompt from app metadata
# ═══════════════════════════════════════════════════════════════════

def build_logo_prompt(
    app_name: str,
    description: str,
    primary_color: str = "#6366f1",
    style: str = "modern flat",
) -> str:
    """Build a high-quality prompt for app logo generation."""
    return (
        f"App icon for '{app_name}', {description[:120]}. "
        f"Style: {style} icon design, professional, clean, minimal, "
        f"bold geometric shapes, dominant color {primary_color}, "
        f"white or transparent background, no text, no letters, "
        f"suitable for iOS/Android app store, square format, high quality"
    )


def build_splash_prompt(
    app_name: str,
    description: str,
    primary_color: str = "#6366f1",
    secondary_color: str = "#8b5cf6",
) -> str:
    """Build a prompt for an app splash/onboarding screen illustration."""
    return (
        f"App splash screen illustration for '{app_name}', {description[:100]}. "
        f"Style: modern digital illustration, gradient background from "
        f"{primary_color} to {secondary_color}, centered composition, "
        f"friendly and professional, minimal UI, no text, vector-style"
    )
