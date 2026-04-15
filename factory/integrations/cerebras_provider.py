"""
AI Factory Pipeline v5.8 — Cerebras Provider (Free Tier)

Cerebras offers the fastest LLM inference available — up to 2,000 tokens/sec
on Llama 3.3 70B. Free tier requires no credit card.

Free account: https://inference.cerebras.ai (email sign-up only)
API key env var: CEREBRAS_API_KEY

Models:
  Strategist/Engineer → llama-3.3-70b  (GPT-4 class, 8k context)
  QuickFix            → llama3.1-8b    (very fast, 8k context)

Rate limits (free tier):
  30 requests/minute, 60,000 tokens/minute, 1M tokens/day

OpenAI-compatible API — no SDK needed, uses httpx.

Docs: https://inference-docs.cerebras.ai/introduction
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.cerebras_provider")

CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"

CEREBRAS_MODEL_MAP: dict[str, str] = {
    "claude-opus-4-6":            "llama-3.3-70b",
    "claude-opus-4-5-20250929":   "llama-3.3-70b",
    "claude-sonnet-4-5-20250929": "llama-3.3-70b",
    "claude-sonnet-4-20250514":   "llama-3.3-70b",
    "claude-haiku-4-5-20251001":  "llama3.1-8b",
}

CEREBRAS_COST_PER_CALL: float = 0.0001  # free tier


async def call_cerebras(
    prompt: str,
    contract: "RoleContract",
    system_prompt: str | None = None,
) -> tuple[str, float]:
    """Call Cerebras API. Returns (response_text, cost_usd)."""
    api_key = os.getenv("CEREBRAS_API_KEY", "")
    if not api_key:
        raise ValueError("CEREBRAS_API_KEY not configured")

    model = CEREBRAS_MODEL_MAP.get(contract.model, "llama-3.3-70b")
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
        "max_completion_tokens": min(contract.max_output_tokens, 8192),
        "temperature": 0.7,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{CEREBRAS_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 RESOURCE_EXHAUSTED — Cerebras rate limit")
    if response.status_code == 401:
        raise Exception("401 Unauthorized — check CEREBRAS_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.info(f"Cerebras {model}: {len(text)} chars")
    return text, CEREBRAS_COST_PER_CALL


async def call_cerebras_raw(
    prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.7,
) -> str:
    """Plain-text Cerebras call (no RoleContract — used by Telegram bot)."""
    api_key = os.getenv("CEREBRAS_API_KEY", "")
    if not api_key:
        raise ValueError("CEREBRAS_API_KEY not configured")

    import httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b",
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": min(max_tokens, 8192),
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{CEREBRAS_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 RESOURCE_EXHAUSTED — Cerebras rate limit")
    if response.status_code == 401:
        raise Exception("401 Unauthorized — check CEREBRAS_API_KEY")
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
