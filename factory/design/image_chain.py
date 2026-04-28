"""
AI Factory Pipeline v5.8 — Image Generation Chain

Eight-provider catalog with master-mode-aware chain selection.
Each provider is skipped gracefully when its key is absent — no silent
quality downgrade, just a logged skip and the next provider in the chain.

Provider ranking (head = best for logo/text-in-image, tail = broadest fallback):
  1  ideogram_v3               — best free text-in-image (letter rendering)
  2  recraft_v3                — best free vector/SVG logos
  3  gemini_flash_image        — best prompt fidelity for complex compositions
  4  fal_ideogram              — Ideogram V3 via fal.ai aggregator
  5  fal_recraft               — Recraft V3 via fal.ai
  6  fal_flux2_pro             — FLUX.2 Pro via fal.ai (TURBO quality)
  7  pollinations              — zero-key FLUX-backed baseline fallback
  8  huggingface_flux_schnell  — HF inference FLUX-schnell
  9  cloudflare_flux_schnell   — Cloudflare Workers AI FLUX-schnell
  10 together_flux_schnell     — Together AI FLUX-schnell

Key resolution:
  IDEOGRAM_API_KEY, RECRAFT_API_KEY, FAL_API_KEY,
  GOOGLE_AI_API_KEY (for gemini_flash_image),
  HUGGINGFACE_API_KEY or HF_TOKEN, CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID,
  TOGETHER_API_KEY
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import Literal, Optional, Sequence

import httpx

logger = logging.getLogger("factory.design.image_chain")

# ── Type alias ────────────────────────────────────────────────────────────────
ImageProvider = Literal[
    "ideogram_v3",
    "recraft_v3",
    "gemini_flash_image",
    "fal_ideogram",
    "fal_recraft",
    "fal_flux2_pro",
    "pollinations",
    "huggingface_flux_schnell",
    "cloudflare_flux_schnell",
    "together_flux_schnell",
]

# ── Provider-quality weight (used for candidate scoring) ──────────────────────
_PROVIDER_QUALITY: dict[str, float] = {
    "ideogram_v3":            1.00,
    "recraft_v3":             0.95,
    "gemini_flash_image":     0.90,
    "fal_ideogram":           1.00,
    "fal_recraft":            0.95,
    "fal_flux2_pro":          0.92,
    "pollinations":           0.60,
    "huggingface_flux_schnell": 0.70,
    "cloudflare_flux_schnell":  0.65,
    "together_flux_schnell":    0.68,
}

# ── Required env key per provider (None = no key needed) ──────────────────────
_KEY_REQUIRED: dict[str, Optional[str]] = {
    "ideogram_v3":              "IDEOGRAM_API_KEY",
    "recraft_v3":               "RECRAFT_API_KEY",
    "gemini_flash_image":       "GOOGLE_AI_API_KEY",
    "fal_ideogram":             "FAL_API_KEY",
    "fal_recraft":              "FAL_API_KEY",
    "fal_flux2_pro":            "FAL_API_KEY",
    "pollinations":             None,
    "huggingface_flux_schnell": "HUGGINGFACE_API_KEY",
    "cloudflare_flux_schnell":  "CLOUDFLARE_API_TOKEN",
    "together_flux_schnell":    "TOGETHER_API_KEY",
}

# ── Whether each provider accepts a negative_prompt field ─────────────────────
_SUPPORTS_NEGATIVE: dict[str, bool] = {
    "ideogram_v3":              True,
    "recraft_v3":               False,  # bake negatives into main prompt
    "gemini_flash_image":       False,  # bake negatives into main prompt
    "fal_ideogram":             True,
    "fal_recraft":              False,
    "fal_flux2_pro":            False,  # FLUX design choice
    "pollinations":             False,
    "huggingface_flux_schnell": False,
    "cloudflare_flux_schnell":  False,
    "together_flux_schnell":    False,
}

# ── Mode chains (head = preferred, tail = fallback) ───────────────────────────
_MODE_CHAINS: dict[str, list[str]] = {
    "basic": [
        # Free-only: Ideogram free (10 slow/wk), Recraft free (30/day),
        # Gemini Flash, Pollinations (unlimited), Cloudflare, HuggingFace
        "ideogram_v3",
        "recraft_v3",
        "gemini_flash_image",
        "pollinations",
        "cloudflare_flux_schnell",
        "huggingface_flux_schnell",
        "together_flux_schnell",
    ],
    "balanced": [
        "ideogram_v3",
        "recraft_v3",
        "fal_recraft",
        "fal_flux2_pro",
        "gemini_flash_image",
        "pollinations",
        "cloudflare_flux_schnell",
    ],
    "turbo": [
        "fal_flux2_pro",
        "fal_recraft",
        "fal_ideogram",
        "ideogram_v3",
        "gemini_flash_image",
        "recraft_v3",
        "pollinations",
    ],
    "custom": [
        # Default to balanced; operator can override via IMAGE_PROVIDER_CHAIN env
        "ideogram_v3",
        "recraft_v3",
        "fal_recraft",
        "fal_flux2_pro",
        "gemini_flash_image",
        "pollinations",
        "cloudflare_flux_schnell",
    ],
}


def _has_key(provider: str) -> bool:
    env_var = _KEY_REQUIRED.get(provider)
    if env_var is None:
        return True
    val = os.getenv(env_var, "") or os.getenv("HF_TOKEN", "") if env_var == "HUGGINGFACE_API_KEY" else os.getenv(env_var, "")
    return bool(val and val not in ("ci-placeholder", ""))


def chain_for_mode(mode: str) -> list[str]:
    """Return the ordered image provider list for a master mode, skipping keyless tiers."""
    env_override = os.getenv("IMAGE_PROVIDER_CHAIN", "").strip()
    if env_override:
        raw = [p.strip().lower() for p in env_override.split(",") if p.strip()]
        available = [p for p in raw if _has_key(p)]
        if available:
            return available

    base = _MODE_CHAINS.get((mode or "basic").lower(), _MODE_CHAINS["basic"])
    available = []
    skipped = []
    for p in base:
        if _has_key(p):
            available.append(p)
        else:
            skipped.append(p)
    if skipped:
        logger.info(f"[image-chain] Skipped (no key): {skipped}")
    if not available:
        logger.warning("[image-chain] No providers available — returning pollinations as emergency fallback")
        return ["pollinations"]
    return available


# ── Negative-prompt handling ──────────────────────────────────────────────────

_DEFAULT_LOGO_NEGATIVE = (
    "watermark, signature, text overlay, busy background, photorealistic, "
    "3D render with deep shadows, anime, blurry, extra letters, multiple "
    "unrelated symbols, stock photo, low quality, cropped"
)


def _prepare_prompt(prompt: str, negative: str, provider: str) -> tuple[str, str]:
    """
    For providers that don't support a dedicated negative_prompt field,
    bake the negative instruction into the main prompt.
    Returns (main_prompt, negative_prompt) where negative_prompt may be empty.
    """
    if _SUPPORTS_NEGATIVE.get(provider, False):
        return prompt, negative
    if negative:
        baked = f"{prompt}. Avoid: {negative}"
        return baked, ""
    return prompt, ""


# ═══════════════════════════════════════════════════════════════════════════════
# Dispatch functions — one per provider
# ═══════════════════════════════════════════════════════════════════════════════


async def generate_via_pollinations(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
) -> Optional[bytes]:
    """Zero-key FLUX-backed fallback. Always available."""
    import urllib.parse

    main_prompt, _ = _prepare_prompt(prompt, negative, "pollinations")
    encoded = urllib.parse.quote(main_prompt)
    params = f"?model=flux&width={width}&height={height}&nologo=true"
    if seed is not None:
        params += f"&seed={seed}"
    url = f"https://image.pollinations.ai/prompt/{encoded}{params}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
            return r.content
    except Exception as exc:
        logger.warning(f"[pollinations] {exc}")
        return None


async def generate_via_ideogram(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
    style_type: str = "DESIGN",
) -> Optional[bytes]:
    """Ideogram V3 — best free text-in-image / letter rendering."""
    key = os.getenv("IDEOGRAM_API_KEY", "")
    if not key:
        logger.info("[ideogram] IDEOGRAM_API_KEY not set — skipping")
        return None

    main_prompt, neg = _prepare_prompt(prompt, negative or _DEFAULT_LOGO_NEGATIVE, "ideogram_v3")
    payload: dict = {
        "image_request": {
            "prompt": main_prompt,
            "model": "V_3",
            "magic_prompt_option": "OFF",  # we enhance client-side
            "style_type": style_type,      # DESIGN, ILLUSTRATION, REALISTIC, RENDER_3D
            "aspect_ratio": "ASPECT_1_1",
        }
    }
    if neg:
        payload["image_request"]["negative_prompt"] = neg
    if seed is not None:
        payload["image_request"]["seed"] = seed

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                "https://api.ideogram.ai/api/v1/generate",
                headers={"Api-Key": key, "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            img_url = data["data"][0]["url"]
            img_r = await client.get(img_url, follow_redirects=True)
            img_r.raise_for_status()
            return img_r.content
    except Exception as exc:
        logger.warning(f"[ideogram] {exc}")
        return None


async def generate_via_recraft(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
    style: str = "digital_illustration",
) -> Optional[bytes]:
    """Recraft V3 — best free vector logos (30 credits/day)."""
    key = os.getenv("RECRAFT_API_KEY", "")
    if not key:
        logger.info("[recraft] RECRAFT_API_KEY not set — skipping")
        return None

    main_prompt, _ = _prepare_prompt(prompt, negative, "recraft_v3")
    payload: dict = {
        "prompt": main_prompt,
        "model": "recraftv3",
        "style": style,
        "size": f"{width}x{height}",
    }
    if seed is not None:
        payload["extra_body"] = {"seed": seed}

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                "https://external.api.recraft.ai/v1/images/generations",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            img_url = data["data"][0]["url"]
            img_r = await client.get(img_url, follow_redirects=True)
            img_r.raise_for_status()
            return img_r.content
    except Exception as exc:
        logger.warning(f"[recraft] {exc}")
        return None


async def generate_via_gemini_flash_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
) -> Optional[bytes]:
    """Gemini 2.0 Flash experimental image generation via REST API (no SDK required).

    Uses the generateContent endpoint with IMAGE responseModality.
    Falls back to the google-genai SDK when the package is installed.
    Requires GOOGLE_AI_API_KEY (AI Studio key).
    """
    key = os.getenv("GOOGLE_AI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    if not key:
        logger.info("[gemini-image] GOOGLE_AI_API_KEY not set — skipping")
        return None

    # Bake negative into prompt (Gemini has no separate field)
    main_prompt, _ = _prepare_prompt(prompt, negative, "gemini_flash_image")

    # ── REST API path (works without the google-genai SDK) ─────────────
    try:
        _endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash-exp-image-generation:generateContent"
        )
        _payload = {
            "contents": [{"parts": [{"text": main_prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        async with httpx.AsyncClient(timeout=90) as _client:
            _resp = await _client.post(
                _endpoint,
                params={"key": key},
                json=_payload,
                headers={"Content-Type": "application/json"},
            )
        if _resp.status_code == 200:
            _data = _resp.json()
            # Extract first inlineData blob from candidates
            for _cand in _data.get("candidates", []):
                for _part in _cand.get("content", {}).get("parts", []):
                    _inline = _part.get("inlineData", {})
                    _b64 = _inline.get("data", "")
                    if _b64:
                        import base64 as _b64mod
                        img_bytes = _b64mod.b64decode(_b64)
                        logger.info(f"[gemini-image] REST: {len(img_bytes)} bytes")
                        return img_bytes
            logger.warning("[gemini-image] REST: response has no inlineData")
        else:
            logger.warning(f"[gemini-image] REST error {_resp.status_code}: {_resp.text[:200]}")
    except Exception as exc:
        logger.warning(f"[gemini-image] REST path failed: {exc}")

    # ── SDK fallback (if google-genai is installed) ────────────────────
    try:
        from google import genai as gai  # type: ignore[import]
        from google.genai import types as gai_types  # type: ignore[import]

        client = gai.Client(api_key=key)
        response = await asyncio.to_thread(
            client.models.generate_images,
            model="imagen-3.0-generate-002",
            prompt=main_prompt,
            config=gai_types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_only_high",
                person_generation="allow_adult",
            ),
        )
        raw = response.generated_images[0].image.image_bytes
        return raw if raw else None
    except Exception as exc:
        logger.warning(f"[gemini-image] SDK path failed: {exc}")
        return None


async def generate_via_fal(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
    model_id: str = "fal-ai/flux/schnell",
) -> Optional[bytes]:
    """fal.ai unified dispatch — supports FLUX.2 Pro, Recraft V3, Ideogram V3."""
    key = os.getenv("FAL_API_KEY", "")
    if not key:
        logger.info(f"[fal] FAL_API_KEY not set — skipping {model_id}")
        return None

    main_prompt, neg = _prepare_prompt(prompt, negative, "fal_flux2_pro")
    payload: dict = {
        "prompt": main_prompt,
        "image_size": {"width": width, "height": height},
        "num_inference_steps": 28,
        "num_images": 1,
        "enable_safety_checker": False,
    }
    if neg:
        payload["negative_prompt"] = neg
    if seed is not None:
        payload["seed"] = seed

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Submit job
            sub = await client.post(
                f"https://queue.fal.run/{model_id}",
                headers={"Authorization": f"Key {key}", "Content-Type": "application/json"},
                json=payload,
            )
            sub.raise_for_status()
            request_id = sub.json()["request_id"]

            # Poll until complete (max 60s)
            for _ in range(30):
                await asyncio.sleep(2)
                poll = await client.get(
                    f"https://queue.fal.run/{model_id}/requests/{request_id}/status",
                    headers={"Authorization": f"Key {key}"},
                )
                status = poll.json().get("status")
                if status == "COMPLETED":
                    result = await client.get(
                        f"https://queue.fal.run/{model_id}/requests/{request_id}",
                        headers={"Authorization": f"Key {key}"},
                    )
                    result.raise_for_status()
                    img_url = result.json()["images"][0]["url"]
                    img_r = await client.get(img_url, follow_redirects=True)
                    img_r.raise_for_status()
                    return img_r.content
                elif status == "FAILED":
                    logger.warning(f"[fal] Job {request_id} failed")
                    return None
            logger.warning(f"[fal] Timeout waiting for {request_id}")
            return None
    except Exception as exc:
        logger.warning(f"[fal] {exc}")
        return None


async def generate_via_cloudflare(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
) -> Optional[bytes]:
    """Cloudflare Workers AI — FLUX-schnell (~30-50 img/day free)."""
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account_id:
        logger.info("[cloudflare] CLOUDFLARE_API_TOKEN/ACCOUNT_ID not set — skipping")
        return None

    main_prompt, _ = _prepare_prompt(prompt, negative, "cloudflare_flux_schnell")
    payload: dict = {
        "prompt": main_prompt,
        "width": min(width, 1024),
        "height": min(height, 1024),
        "num_steps": 8,
    }
    if seed is not None:
        payload["seed"] = seed

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            # Response is raw binary for this model
            content_type = r.headers.get("content-type", "")
            if "image" in content_type:
                return r.content
            # Fallback: base64 wrapped JSON
            data = r.json()
            if isinstance(data, dict) and "result" in data:
                img_b64 = data["result"].get("image", "")
                if img_b64:
                    return base64.b64decode(img_b64)
            return None
    except Exception as exc:
        logger.warning(f"[cloudflare] {exc}")
        return None


async def generate_via_huggingface(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
    model: str = "black-forest-labs/FLUX.1-schnell",
) -> Optional[bytes]:
    """HuggingFace Inference API — FLUX-schnell (free with token)."""
    key = os.getenv("HUGGINGFACE_API_KEY", "") or os.getenv("HF_TOKEN", "")
    if not key:
        logger.info("[huggingface] HUGGINGFACE_API_KEY/HF_TOKEN not set — skipping")
        return None

    main_prompt, _ = _prepare_prompt(prompt, negative, "huggingface_flux_schnell")
    payload: dict = {"inputs": main_prompt}
    if seed is not None:
        payload["parameters"] = {"seed": seed}

    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            return r.content
    except Exception as exc:
        logger.warning(f"[huggingface] {exc}")
        return None


async def generate_via_together(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
) -> Optional[bytes]:
    """Together AI — FLUX-schnell (OpenAI-compatible endpoint)."""
    key = os.getenv("TOGETHER_API_KEY", "")
    if not key:
        logger.info("[together] TOGETHER_API_KEY not set — skipping")
        return None

    main_prompt, _ = _prepare_prompt(prompt, negative, "together_flux_schnell")
    payload: dict = {
        "model": "black-forest-labs/FLUX.1-schnell-Free",
        "prompt": main_prompt,
        "width": width,
        "height": height,
        "steps": 4,
        "n": 1,
        "response_format": "b64_json",
    }
    if seed is not None:
        payload["seed"] = seed

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                "https://api.together.xyz/v1/images/generations",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            b64 = r.json()["data"][0]["b64_json"]
            return base64.b64decode(b64)
    except Exception as exc:
        logger.warning(f"[together] {exc}")
        return None


# ── Provider dispatch router ──────────────────────────────────────────────────

_FAL_MODELS: dict[str, str] = {
    "fal_flux2_pro": "fal-ai/flux-pro/v1.1-ultra",
    "fal_recraft":   "fal-ai/recraft-v3",
    "fal_ideogram":  "fal-ai/ideogram/v2",
}


async def _dispatch(
    provider: str,
    prompt: str,
    width: int,
    height: int,
    seed: Optional[int],
    negative: str,
) -> Optional[bytes]:
    if provider == "pollinations":
        return await generate_via_pollinations(prompt, width, height, seed, negative)
    elif provider == "ideogram_v3":
        return await generate_via_ideogram(prompt, width, height, seed, negative)
    elif provider == "recraft_v3":
        return await generate_via_recraft(prompt, width, height, seed, negative)
    elif provider == "gemini_flash_image":
        return await generate_via_gemini_flash_image(prompt, width, height, seed, negative)
    elif provider in _FAL_MODELS:
        return await generate_via_fal(prompt, width, height, seed, negative, _FAL_MODELS[provider])
    elif provider == "cloudflare_flux_schnell":
        return await generate_via_cloudflare(prompt, width, height, seed, negative)
    elif provider == "huggingface_flux_schnell":
        return await generate_via_huggingface(prompt, width, height, seed, negative)
    elif provider == "together_flux_schnell":
        return await generate_via_together(prompt, width, height, seed, negative)
    else:
        logger.warning(f"[image-chain] Unknown provider: {provider}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Logo prompt enhancer
# ═══════════════════════════════════════════════════════════════════════════════

_LOGO_ENHANCE_TEMPLATE = """\
You are a professional logo brief writer. Transform the operator's casual app logo idea
into a structured prompt that image generation models can render accurately.

CRITICAL RULES:
1. If the prompt mentions a LETTER (e.g. "P", "A", "M"), that letter MUST appear
   in the enhanced prompt as: 'a bold capital letter "X" in clean modern sans-serif,
   clearly readable at thumbnail size, THE LETTER MUST BE PRESENT AND LEGIBLE.'
2. If the prompt mentions an emoji symbol (heart ❤️, star ⭐, etc.), describe the
   object explicitly — don't use the emoji character.
3. End with: 'iOS App Store icon quality. Square composition 1024×1024.
   Clean flat vector design. Simple, bold, memorable.'
4. Output ONLY the enhanced prompt text — no preamble, no explanation.

NEGATIVE PROMPT (output as a second line starting with "NEGATIVE:"):
List 10-15 specific things to avoid as a comma-separated phrase. Always include:
watermark, signature, busy background, extra letters, multiple symbols,
photorealistic, 3D render with deep shadows, blurry, cropped.

OPERATOR INPUT:
{raw_prompt}

APP NAME (hint): {app_name}
TARGET MARKET: {target_market}"""


async def enhance_logo_prompt(
    raw_prompt: str,
    app_name: str = "",
    target_market: str = "KSA",
) -> tuple[str, str]:
    """Enhance a casual logo prompt for image model consumption.

    Returns:
        (enhanced_prompt, negative_prompt)
    If the AI call fails, returns the raw prompt with a default negative.
    """
    from factory.core.dry_run import is_dry_run, is_mock_provider

    if is_dry_run() or is_mock_provider():
        return raw_prompt, _DEFAULT_LOGO_NEGATIVE

    try:
        from factory.core.roles import call_ai

        system_input = _LOGO_ENHANCE_TEMPLATE.format(
            raw_prompt=raw_prompt,
            app_name=app_name or "unknown",
            target_market=target_market,
        )
        result = await call_ai(
            prompt=system_input,
            role="quick_fix",
            max_tokens=400,
            temperature=0.3,
        )
        text = (result or "").strip()
        lines = text.split("\n", 1)
        enhanced = lines[0].strip()
        negative = _DEFAULT_LOGO_NEGATIVE
        if len(lines) > 1 and lines[1].startswith("NEGATIVE:"):
            negative = lines[1][len("NEGATIVE:"):].strip()
        if not enhanced:
            return raw_prompt, negative
        return enhanced, negative
    except Exception as exc:
        logger.warning(f"[enhance-logo-prompt] {exc} — using raw prompt")
        return raw_prompt, _DEFAULT_LOGO_NEGATIVE


# ═══════════════════════════════════════════════════════════════════════════════
# Public API — multi-candidate generation
# ═══════════════════════════════════════════════════════════════════════════════

def _score_candidate(data: bytes, provider: str) -> float:
    """Score: 60% size quality + 40% provider reputation."""
    size = len(data)
    if size < 5_000:
        size_score = 0.0
    elif size < 50_000:
        size_score = 0.4
    elif size < 200_000:
        size_score = 0.7
    else:
        size_score = 1.0
    quality = _PROVIDER_QUALITY.get(provider, 0.5)
    return size_score * 0.6 + quality * 0.4


async def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    negative: str = "",
    master_mode: str = "basic",
    app_name: str = "",
) -> Optional[bytes]:
    """Generate one image through the mode-appropriate chain.

    Tries providers in order, returns the first successful result.
    """
    from factory.core.dry_run import is_dry_run

    if is_dry_run():
        return b"MOCK_IMAGE_BYTES"

    providers = chain_for_mode(master_mode)
    for provider in providers:
        t0 = time.monotonic()
        result = await _dispatch(provider, prompt, width, height, seed, negative)
        latency_ms = int((time.monotonic() - t0) * 1000)
        if result:
            logger.info(f"[image-chain] {provider} succeeded ({len(result)} bytes, {latency_ms}ms)")
            return result
        logger.debug(f"[image-chain] {provider} failed ({latency_ms}ms) — trying next")
    logger.error("[image-chain] All providers failed")
    return None


async def generate_image_best_of(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: Optional[int] = None,
    master_mode: str = "basic",
    app_name: str = "",
    target_market: str = "KSA",
    n_candidates: int = 3,
    enhance: bool = True,
) -> list[dict]:
    """Generate n_candidates images and return them ranked by quality score.

    Each result dict: {"provider": str, "data": bytes, "score": float,
                       "enhanced_prompt": str}
    """
    from factory.core.dry_run import is_dry_run

    if is_dry_run():
        return [{"provider": "mock", "data": b"MOCK_IMAGE_BYTES", "score": 1.0, "enhanced_prompt": prompt}]

    enhanced_prompt, negative = (
        await enhance_logo_prompt(prompt, app_name, target_market)
        if enhance else (prompt, _DEFAULT_LOGO_NEGATIVE)
    )
    logger.info(f"[image-chain] Enhanced prompt: {enhanced_prompt[:120]}")

    providers = chain_for_mode(master_mode)
    # Take up to n_candidates from the top of the chain, generate in parallel
    selected = providers[:n_candidates]
    seeds = [seed] + [((seed or 42) + i * 7) for i in range(1, n_candidates)]

    async def _gen(provider: str, s: Optional[int]) -> dict:
        t0 = time.monotonic()
        data = await _dispatch(provider, enhanced_prompt, width, height, s, negative)
        elapsed = int((time.monotonic() - t0) * 1000)
        if data:
            score = _score_candidate(data, provider)
            logger.info(f"[image-chain] {provider} → {len(data)} bytes, score={score:.2f}, {elapsed}ms")
            return {"provider": provider, "data": data, "score": score, "enhanced_prompt": enhanced_prompt}
        return {"provider": provider, "data": None, "score": 0.0, "enhanced_prompt": enhanced_prompt}

    results = await asyncio.gather(*[_gen(p, s) for p, s in zip(selected, seeds)])
    candidates = [r for r in results if r["data"]]
    candidates.sort(key=lambda r: r["score"], reverse=True)
    if not candidates:
        # Absolute fallback: Pollinations synchronous
        logger.warning("[image-chain] All candidates failed — falling back to pollinations")
        data = await generate_via_pollinations(enhanced_prompt, width, height, seed)
        if data:
            return [{"provider": "pollinations", "data": data, "score": 0.6, "enhanced_prompt": enhanced_prompt}]
    return candidates
