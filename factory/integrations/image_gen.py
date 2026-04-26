"""
AI Factory Pipeline — Free Image Generation Chain

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

from factory import __version__ as _VERSION

logger = logging.getLogger("factory.integrations.image_gen")

_UA = f"AI-Factory/{_VERSION}"


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
    from factory.core.dry_run import is_dry_run, is_mock_provider
    if (
        is_mock_provider()
        or is_dry_run()
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
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
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
        req = urllib.request.Request(img_url, headers={"User-Agent": _UA})
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
    scout_intel: str = "",
) -> str:
    """Build a high-quality prompt for app logo generation.

    Args:
        app_name: The app's name.
        description: Short description of what the app does.
        primary_color: Brand primary color hex.
        style: Base visual style hint.
        scout_intel: Optional scout research summary (design trends, competitor
                     icon styles, target market aesthetics) — enriches the prompt
                     with market-appropriate visual direction.
    """
    intel_hint = ""
    if scout_intel:
        # Distil the scout intel to a single actionable design direction
        intel_hint = f" Design direction based on market research: {scout_intel[:200]}."

    # Allow letters/text when the user explicitly requests them in the description
    import re as _re
    _text_requested = bool(_re.search(
        r"\b(letter|text|number|digit|word|initial|symbol|[A-Z] letter)\b",
        description, _re.IGNORECASE,
    ))
    _text_clause = (
        f"include the letter/text as described, bold and clear"
        if _text_requested else
        "no text, no letters"
    )

    return (
        f"App icon for '{app_name}'. {description[:200]}.{intel_hint} "
        f"Style: {style} icon design, professional, clean, minimal, "
        f"bold geometric shapes, dominant color {primary_color}, "
        f"white or transparent background, {_text_clause}, "
        f"suitable for iOS/Android app store, square format, high quality, "
        f"ultra-detailed, vibrant colors, sharp edges"
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


# ═══════════════════════════════════════════════════════════════════
# Prompt Enhancer
# ═══════════════════════════════════════════════════════════════════

async def enhance_image_prompt(
    raw_prompt: str,
    app_name: str = "",
    target_market: str = "KSA",
    max_tokens: int = 200,
) -> str:
    """Use the AI chain to enrich a raw image prompt with market-specific design direction.

    Returns the enhanced prompt string, or ``raw_prompt`` unchanged on any error
    (so callers never block on a prompt-enhancement failure).
    """
    from factory.core.dry_run import is_dry_run, is_mock_provider
    if is_dry_run() or is_mock_provider():
        return raw_prompt

    try:
        from factory.integrations.ai_chain import call_ai
        system = (
            "You are a professional art director for mobile app icons. "
            "Rewrite the user's image prompt to be more vivid, specific, and market-appropriate. "
            f"Target market: {target_market}. "
            "Output ONLY the improved prompt — no explanation, no quotes."
        )
        user_msg = f"App: {app_name}\nOriginal prompt: {raw_prompt}"
        enhanced = await call_ai(user_msg, system=system, max_tokens=max_tokens)
        enhanced = enhanced.strip().strip('"').strip("'")
        return enhanced if len(enhanced) > 20 else raw_prompt
    except Exception as e:
        logger.warning(f"[image_gen] prompt enhancement failed: {e}")
        return raw_prompt


# ═══════════════════════════════════════════════════════════════════
# Candidate Scoring
# ═══════════════════════════════════════════════════════════════════

# Provider quality weights: higher = preferred when multiple candidates succeed.
_PROVIDER_QUALITY: dict[str, float] = {
    "nvidia_nim_flux": 1.0,
    "huggingface": 0.85,
    "together": 0.80,
    "pollinations": 0.60,
}


def score_image_candidate(data: bytes, provider: str) -> float:
    """Score a raw image candidate.  Higher is better.

    Combines file-size heuristic (more bytes → more detail) with a
    provider quality weight so premium providers win ties.
    """
    if not data or len(data) < 1000:
        return 0.0
    size_score = min(len(data) / 500_000, 1.0)  # cap at 500 KB
    quality = _PROVIDER_QUALITY.get(provider, 0.5)
    return round(size_score * 0.6 + quality * 0.4, 4)


async def generate_image_best_of(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    style: str = "",
    seed: Optional[int] = None,
    providers: Optional[list[str]] = None,
) -> Optional[bytes]:
    """Generate from up to *providers* in parallel and return the highest-scoring result.

    Falls back to the standard serial chain if all parallel calls fail.
    """
    from factory.core.dry_run import is_dry_run, is_mock_provider
    if is_mock_provider() or is_dry_run():
        return None

    candidate_providers = providers or _IMAGE_PROVIDER_CHAIN
    full_prompt = f"{prompt}, {style}" if style else prompt
    _seed = seed or int(time.time()) % 999999

    tasks = {
        p: asyncio.create_task(_call_provider(p, full_prompt, width, height, _seed))
        for p in candidate_providers
    }

    candidates: list[tuple[float, bytes, str]] = []
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for provider, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.warning(f"[image_gen] candidate {provider} failed: {result}")
            continue
        if result:
            score = score_image_candidate(result, provider)
            candidates.append((score, result, provider))
            logger.info(f"[image_gen] candidate {provider}: {len(result)} bytes, score={score}")

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0], reverse=True)
    best_score, best_data, best_provider = candidates[0]
    logger.info(f"[image_gen] best candidate: {best_provider} (score={best_score})")
    return best_data
