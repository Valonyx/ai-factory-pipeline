"""
AI Factory Pipeline v5.6 — Mistral Provider (La Plateforme Free Tier)

Mistral AI offers free access to their models via La Plateforme.
No credit card required, rate-limited.

Free account: https://console.mistral.ai (email sign-up)
API key env var: MISTRAL_API_KEY

Free models (La Plateforme):
  Strategist/Engineer → mistral-small-latest   (24B, strong reasoning)
  QuickFix            → mistral-small-latest   (same — only one free tier)

Rate limits (free tier): ~1 req/sec, 500,000 tokens/month

OpenAI-compatible API — no SDK needed, uses httpx.

Docs: https://docs.mistral.ai/api/
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.mistral_provider")

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

MISTRAL_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-6":            "mistral-small-latest",
    "claude-opus-4-5-20250929":   "mistral-small-latest",
    "claude-sonnet-4-5-20250929": "mistral-small-latest",
    "claude-sonnet-4-20250514":   "mistral-small-latest",
    "claude-haiku-4-5-20251001":  "mistral-small-latest",
}

MISTRAL_COST_PER_CALL: float = 0.0001  # free tier


async def call_mistral(
    prompt: str,
    contract: "RoleContract",
    system_prompt: str | None = None,
) -> tuple[str, float]:
    """Call Mistral API. Returns (response_text, cost_usd)."""
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not configured")

    model = MISTRAL_MODEL_MAP.get(contract.model, "mistral-small-latest")
    if system_prompt is None:
        system_prompt = _get_system_prompt(contract)

    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": min(contract.max_output_tokens, 4096),
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{MISTRAL_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 RESOURCE_EXHAUSTED — Mistral rate limit")
    if response.status_code == 401:
        raise Exception("401 Unauthorized — check MISTRAL_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.info(f"Mistral {model}: {len(text)} chars")
    return text, MISTRAL_COST_PER_CALL


async def call_mistral_raw(
    prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.7,
) -> str:
    """Plain-text Mistral call (no RoleContract — used by Telegram bot)."""
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not configured")

    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(max_tokens, 4096),
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{MISTRAL_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 RESOURCE_EXHAUSTED — Mistral rate limit")
    if response.status_code == 401:
        raise Exception("401 Unauthorized — check MISTRAL_API_KEY")
    response.raise_for_status()

    data = response.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


def _get_system_prompt(contract: "RoleContract") -> str:
    try:
        from factory.integrations.prompts import (
            STRATEGIST_SYSTEM_PROMPT, ENGINEER_SYSTEM_PROMPT, QUICK_FIX_SYSTEM_PROMPT,
        )
        from factory.core.state import AIRole
        mapping = {
            AIRole.STRATEGIST: STRATEGIST_SYSTEM_PROMPT,
            AIRole.ENGINEER:   ENGINEER_SYSTEM_PROMPT,
            AIRole.QUICK_FIX:  QUICK_FIX_SYSTEM_PROMPT,
        }
        return mapping.get(contract.role, "You are a helpful AI assistant.")
    except ImportError:
        return "You are a helpful AI assistant."
