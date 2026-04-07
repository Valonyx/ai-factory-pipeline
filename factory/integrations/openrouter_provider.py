"""
AI Factory Pipeline v5.6 — OpenRouter Provider (Free Models)

OpenRouter provides access to multiple AI models via a single API.
Several models are available for free (no credits required).

Free account: https://openrouter.ai (no credit card required)
API key env var: OPENROUTER_API_KEY

Free models used (ordered by quality):
  Strategist  → meta-llama/llama-3.3-70b-instruct:free
  Engineer    → meta-llama/llama-3.3-70b-instruct:free
  QuickFix    → mistralai/mistral-7b-instruct:free

Note: Free models have rate limits (variable per model). OpenRouter is
the 4th fallback in the chain — used only when Gemini + Groq are both
exhausted.

SDK: uses httpx (already in requirements) with OpenAI-compatible endpoint
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.openrouter_provider")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Role → OpenRouter free model mapping
OPENROUTER_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-6":            "meta-llama/llama-3.3-70b-instruct:free",
    "claude-opus-4-5-20250929":   "meta-llama/llama-3.3-70b-instruct:free",
    "claude-sonnet-4-5-20250929": "meta-llama/llama-3.3-70b-instruct:free",
    "claude-sonnet-4-20250514":   "meta-llama/llama-3.3-70b-instruct:free",
    "claude-haiku-4-5-20251001":  "mistralai/mistral-7b-instruct:free",
}

OPENROUTER_COST_PER_CALL: float = 0.0001  # free models


async def call_openrouter(
    prompt: str,
    contract: "RoleContract",
    system_prompt: str | None = None,
) -> tuple[str, float]:
    """Call OpenRouter API using a free model.

    Returns (response_text, cost_usd).
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("[OPENROUTER] OPENROUTER_API_KEY not set — get free key at openrouter.ai")
        raise ValueError("OPENROUTER_API_KEY not configured")

    model = OPENROUTER_MODEL_MAP.get(contract.model, "meta-llama/llama-3.3-70b-instruct:free")

    if system_prompt is None:
        system_prompt = _get_system_prompt(contract)

    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/Valonyx/ai-factory-pipeline",
        "X-Title": "AI Factory Pipeline",
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

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception(f"429 RESOURCE_EXHAUSTED — OpenRouter rate limit")
    if response.status_code == 401:
        raise Exception(f"401 Unauthorized — check OPENROUTER_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.info(f"OpenRouter {model} ({contract.role.value}): {len(text)} chars")
    return text, OPENROUTER_COST_PER_CALL


async def call_openrouter_raw(
    prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.7,
) -> str:
    """Plain-text OpenRouter call for components without a RoleContract (e.g. Telegram bot).

    Returns response text. Raises on error.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/Valonyx/ai-factory-pipeline",
        "X-Title": "AI Factory Pipeline",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(max_tokens, 4096),
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 RESOURCE_EXHAUSTED — OpenRouter rate limit")
    if response.status_code == 401:
        raise Exception("401 Unauthorized — check OPENROUTER_API_KEY")
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
