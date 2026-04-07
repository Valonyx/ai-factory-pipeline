"""
AI Factory Pipeline v5.6 — Together AI Provider (Free Models)

Together AI hosts hundreds of open-source models. Many are completely free
with no rate limits. Requires no credit card for free models.

Free account: https://api.together.xyz (email sign-up)
API key env var: TOGETHER_API_KEY

Free models used:
  Strategist/Engineer → meta-llama/Llama-3.3-70B-Instruct-Turbo-Free
  QuickFix            → meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo  (free)

Note: Models ending in "-Free" are truly unlimited. Other models use credits.

OpenAI-compatible API — no SDK needed, uses httpx.

Docs: https://docs.together.ai/docs/openai-api-compatibility
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.together_provider")

TOGETHER_BASE_URL = "https://api.together.xyz/v1"

TOGETHER_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-6":            "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    "claude-opus-4-5-20250929":   "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    "claude-sonnet-4-5-20250929": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    "claude-sonnet-4-20250514":   "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
    "claude-haiku-4-5-20251001":  "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
}

TOGETHER_COST_PER_CALL: float = 0.0  # free models are fully free


async def call_together(
    prompt: str,
    contract: "RoleContract",
    system_prompt: str | None = None,
) -> tuple[str, float]:
    """Call Together AI with a free model. Returns (response_text, cost_usd)."""
    api_key = os.getenv("TOGETHER_API_KEY", "")
    if not api_key:
        raise ValueError("TOGETHER_API_KEY not configured")

    model = TOGETHER_MODEL_MAP.get(contract.model, "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free")
    if system_prompt is None:
        system_prompt = _get_system_prompt(contract)

    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
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

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{TOGETHER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 RESOURCE_EXHAUSTED — Together AI rate limit")
    if response.status_code == 401:
        raise Exception("401 Unauthorized — check TOGETHER_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.info(f"Together AI {model.split('/')[-1]}: {len(text)} chars")
    return text, TOGETHER_COST_PER_CALL


async def call_together_raw(
    prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.7,
) -> str:
    """Plain-text Together AI call (no RoleContract — used by Telegram bot)."""
    api_key = os.getenv("TOGETHER_API_KEY", "")
    if not api_key:
        raise ValueError("TOGETHER_API_KEY not configured")

    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(max_tokens, 4096),
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{TOGETHER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 RESOURCE_EXHAUSTED — Together AI rate limit")
    if response.status_code == 401:
        raise Exception("401 Unauthorized — check TOGETHER_API_KEY")
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
