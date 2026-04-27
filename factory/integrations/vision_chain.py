"""
AI Factory Pipeline v5.8.16 — Vision Chain (4 Free Providers)

Unified multimodal image-analysis chain. Tries providers in priority order
according to the active MasterMode, tracks cost through QuotaTracker, and
returns a typed degraded result if all options fail — never fake success.

Provider roster (all free-tier):
  1. NVIDIA NIM Vision       — llama-3.2-90b-vision  (highest quality)
     Key: NVIDIA_NIM_VISION_API_KEY | NVIDIA_NIM_API_KEY
     Register: https://build.nvidia.com
  2. Google Gemini Vision    — gemini-2.0-flash       (1 500 RPD free)
     Key: GEMINI_API_KEY
     Register: https://aistudio.google.com
  3. Groq Vision             — llama-4-scout-17b      (14 400 RPD, fastest)
     Key: GROQ_API_KEY
     Register: https://console.groq.com
  4. Cloudflare Workers AI   — llama-3.2-11b-vision   (10k neurons/day)
     Keys: CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN
     Register: https://dash.cloudflare.com

MasterMode behaviour:
  BASIC    — all 4 providers are free (all eligible)
  BALANCED — same free set; order by quality rank
  TURBO    — same providers; may use higher-quality model variant
  CUSTOM   — operator-ordered preference respected

Spec Authority: v5.8.16 §G4 (Vision Gap closure)
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.vision_chain")

# ── Provider priority (lower rank = better quality) ─────────────────────────
# All providers are free-tier. Rank reflects response quality in practice.
_PROVIDER_PRIORITY: list[str] = [
    p.strip()
    for p in os.getenv(
        "VISION_PROVIDER_CHAIN",
        "nvidia_nim_vision,gemini_vision,groq_vision,cloudflare_vision",
    ).split(",")
    if p.strip()
]


# ── Public API ───────────────────────────────────────────────────────────────


async def analyze_image(
    image_bytes: bytes,
    prompt: str,
    mode: str = "balanced",
) -> dict:
    """Analyse an image using the free vision provider chain.

    Tries providers in priority order; stops at first success.
    Returns a typed result dict — never raises on all-fail (returns degraded).

    Args:
        image_bytes: Raw PNG or JPEG screenshot/image bytes.
        prompt:      Analysis instruction.
        mode:        "basic" | "balanced" | "custom" | "turbo".
                     Included for chain-interface consistency; all four
                     providers are free so BASIC still gets real results.

    Returns:
        {
          "text":     str   — model's analysis,
          "source":   str   — provider name,
          "degraded": bool  — True only when all providers failed,
          "error":    str   — error summary (only when degraded=True),
        }
    """
    if is_mock_provider():
        return {
            "text": f"[MOCK:vision_chain] {prompt[:60]}",
            "source": "mock",
            "degraded": False,
        }

    errors: list[str] = []
    for provider in _PROVIDER_PRIORITY:
        try:
            text = await _call_provider(provider, image_bytes, prompt)
            logger.info("[vision_chain] %s succeeded", provider)
            _track_cost(provider)
            return {"text": text, "source": provider, "degraded": False}
        except Exception as e:
            err = f"{provider}: {e}"
            errors.append(err)
            logger.warning("[vision_chain] %s", err)

    logger.error("[vision_chain] All providers failed: %s", "; ".join(errors))
    return {
        "text": "",
        "source": "degraded",
        "degraded": True,
        "error": "; ".join(errors),
    }


async def analyze_ui_screenshot(
    screenshot_bytes: bytes,
    task: str = "",
    mode: str = "balanced",
) -> dict:
    """Specialised wrapper for UI/UX screenshot analysis."""
    prompt = (
        (f"Task: {task}\n\n" if task else "") +
        "Analyse this UI screenshot. Identify all interactive elements (buttons, "
        "inputs, links, menus), describe the layout structure, navigation, color "
        "scheme, typography, and any UX concerns. Be concise and structured."
    )
    return await analyze_image(screenshot_bytes, prompt, mode)


# ── Provider dispatch ────────────────────────────────────────────────────────


async def _call_provider(provider: str, image_bytes: bytes, prompt: str) -> str:
    if provider == "nvidia_nim_vision":
        from factory.integrations.nvidia_nim_vision import describe_image
        return await describe_image(image_bytes, prompt)

    if provider == "gemini_vision":
        from factory.integrations.gemini_vision import describe_image
        return await describe_image(image_bytes, prompt)

    if provider == "groq_vision":
        from factory.integrations.groq_vision import describe_image
        return await describe_image(image_bytes, prompt)

    if provider == "cloudflare_vision":
        from factory.integrations.cloudflare_vision import describe_image
        return await describe_image(image_bytes, prompt)

    if provider == "claude_vision":
        from factory.integrations.claude_vision import call_claude_vision
        text, _ = await call_claude_vision(image_bytes, prompt)
        return text

    raise ValueError(f"Unknown vision provider: {provider}")


# ── Cost tracking ────────────────────────────────────────────────────────────

# Per-provider nominal cost for QuotaTracker (all free-tier, $0 effective)
_PROVIDER_COST: dict[str, float] = {
    "nvidia_nim_vision":   0.0001,
    "gemini_vision":       0.0001,
    "groq_vision":         0.0001,
    "cloudflare_vision":   0.0,
    "claude_vision":       0.002,  # paid — only if explicitly in chain
}


def _track_cost(provider: str) -> None:
    """Record a vision call in QuotaTracker (non-fatal)."""
    try:
        from factory.core.quota_tracker import get_quota_tracker
        import asyncio
        qt = get_quota_tracker()
        asyncio.create_task(
            qt.record_usage(
                provider,
                tokens=0,
                calls=1,
                cost_usd=_PROVIDER_COST.get(provider, 0.0001),
            )
        )
    except Exception:
        pass


# ── Provider availability check ──────────────────────────────────────────────


def available_providers() -> list[str]:
    """Return vision providers that have valid credentials configured."""
    result: list[str] = []
    for p in _PROVIDER_PRIORITY:
        if _provider_has_key(p):
            result.append(p)
    return result


def _provider_has_key(provider: str) -> bool:
    if is_mock_provider():
        return True
    env_map = {
        "nvidia_nim_vision":   ["NVIDIA_NIM_VISION_API_KEY", "NVIDIA_NIM_API_KEY"],
        "gemini_vision":       ["GOOGLE_AI_API_KEY"],  # also accepts GEMINI_API_KEY via get_gemini_api_key()
        "groq_vision":         ["GROQ_API_KEY"],
        "cloudflare_vision":   ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"],
        "claude_vision":       ["ANTHROPIC_API_KEY"],
    }
    required = env_map.get(provider, [])
    return all(os.getenv(k, "") for k in required)
