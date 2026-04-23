"""
AI Factory Pipeline v5.8 — Groq Provider (Free Tier)

Groq provides extremely fast inference on open-source models.
Free tier: 14,400 requests/day, 6,000 RPM — far more generous than Gemini.

Free account: https://console.groq.com (no credit card required)
API key env var: GROQ_API_KEY

Role → model mapping (quality-matched to Anthropic equivalents):
  Strategist  → llama-3.3-70b-versatile   (GPT-4 class, 128k context)
  Engineer    → llama-3.3-70b-versatile   (same — Groq has fewer tiers)
  QuickFix    → llama-3.1-8b-instant      (very fast, 128k context)
  Scout       → (not used for search — Groq is text-gen only)

SDK: groq (pip install groq)
Docs: https://console.groq.com/docs/openai

Dev note: Groq's Llama 3.3 70B performs on par with Claude Sonnet for
code generation and structured output tasks. Suitable for all pipeline
stages as a fallback when Gemini quota is exhausted.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.groq_provider")

# Role → Groq model mapping
GROQ_MODEL_MAP: dict[str, str] = {
    # Strategist (Opus-class) → best available Groq model
    "claude-opus-4-6":            "llama-3.3-70b-versatile",
    "claude-opus-4-5-20250929":   "llama-3.3-70b-versatile",
    # Engineer (Sonnet-class) → same — Groq has fewer tiers
    "claude-sonnet-4-5-20250929": "llama-3.3-70b-versatile",
    "claude-sonnet-4-20250514":   "llama-3.3-70b-versatile",
    # QuickFix (Haiku-class) → fastest Groq model
    "claude-haiku-4-5-20251001":  "llama-3.1-8b-instant",
}

GROQ_COST_PER_CALL: float = 0.0001  # nominal — free tier


async def call_groq(
    prompt: str,
    contract: "RoleContract",
    system_prompt: str | None = None,
) -> tuple[str, float]:
    """Call Groq API as a fallback AI provider.

    Returns (response_text, cost_usd).
    Raises on quota/auth errors so the caller can update the provider chain.
    """
    api_key = os.getenv("GROQ_API_KEY", "")

    if not api_key:
        logger.warning("[GROQ] GROQ_API_KEY not set — get free key at console.groq.com")
        raise ValueError("GROQ_API_KEY not configured")

    model = GROQ_MODEL_MAP.get(contract.model, "llama-3.3-70b-versatile")

    if system_prompt is None:
        system_prompt = _get_system_prompt(contract)

    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=api_key)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt},
            ],
            # llama-3.3-70b-versatile supports 32 768 output tokens on free tier.
            # Cap at 16 384 — matches ENGINEER contract and prevents runaway cost
            # on a single call. QuickFix still naturally stays well below this.
            max_tokens=min(contract.max_output_tokens, 16384),
            temperature=0.7,
        )
        text = response.choices[0].message.content or ""
        logger.info(f"Groq {model} ({contract.role.value}): {len(text)} chars")
        return text, GROQ_COST_PER_CALL

    except Exception as e:
        err = str(e)
        logger.error(f"Groq API error ({model}): {err}")
        raise


async def call_groq_raw(
    prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.7,
) -> str:
    """Plain-text Groq call for components without a RoleContract (e.g. Telegram bot).

    Returns response text. Raises on error.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not configured")

    from groq import AsyncGroq
    client = AsyncGroq(api_key=api_key)
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(max_tokens, 8192),
        temperature=temperature,
    )
    return (response.choices[0].message.content or "").strip()


def _get_system_prompt(contract: "RoleContract") -> str:
    try:
        from factory.integrations.prompts import (
            STRATEGIST_SYSTEM_PROMPT,
            ENGINEER_SYSTEM_PROMPT,
            QUICK_FIX_SYSTEM_PROMPT,
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
