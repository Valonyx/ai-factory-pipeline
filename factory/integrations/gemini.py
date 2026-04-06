"""
AI Factory Pipeline v5.6 — Google Gemini Free-Tier Provider

DEV ALTERNATIVE for Anthropic when API credits are unavailable.
Switch back to Anthropic by setting AI_PROVIDER=anthropic in .env.

Free-tier limits (as of 2026-04):
  - gemini-1.5-pro:          50 RPD,  1M RPM input tokens  (most capable)
  - gemini-2.0-flash:      1500 RPD, 1M RPM input tokens  (recommended for dev)
  - gemini-2.0-flash-lite: 1500 RPD, 4M RPM input tokens  (fastest/cheapest)
  No credit card required. Free at: aistudio.google.com

Role mapping (dev only):
  - Strategist → gemini-1.5-pro        (architect-grade reasoning)
  - Engineer   → gemini-2.0-flash       (code generation)
  - QuickFix   → gemini-2.0-flash-lite  (fast syntax fixes)

Pricing: $0.00 while within free-tier limits.
Switch to Anthropic for production — better JSON adherence, no daily limits.

Dev note (NB3-DEV-001): This module was added as a free-tier development
alternative when Anthropic API credits were unavailable. All role contracts,
prompts, and cost tracking logic remain identical — only the underlying
model provider changes. Remove AI_PROVIDER=gemini from .env to revert.

Spec Authority: v5.6 §2.2 (provider-agnostic role interface)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.gemini")

# ═══════════════════════════════════════════════════════════════════
# Role → Gemini Model Mapping (dev equivalents)
# ═══════════════════════════════════════════════════════════════════

# Maps Anthropic model names to their Gemini free-tier equivalents
GEMINI_MODEL_MAP: dict[str, str] = {
    # Strategist (Opus-class) → most capable free Gemini
    "claude-opus-4-6":            "gemini-1.5-pro",
    "claude-opus-4-5-20250929":   "gemini-1.5-pro",
    # Engineer (Sonnet-class) → fast capable Gemini
    "claude-sonnet-4-5-20250929": "gemini-2.0-flash",
    "claude-sonnet-4-20250514":   "gemini-2.0-flash",
    # QuickFix (Haiku-class) → fastest Gemini
    "claude-haiku-4-5-20251001":  "gemini-2.0-flash-lite",
}

# Free-tier daily limits per model
GEMINI_FREE_LIMITS: dict[str, int] = {
    "gemini-1.5-pro":         50,
    "gemini-2.0-flash":     1500,
    "gemini-2.0-flash-lite": 1500,
}

# Effective cost = $0 in free tier — reported for budget tracking
GEMINI_COST_PER_CALL: float = 0.0001  # Nominal $0.0001 so budgets register non-zero


def _get_gemini_model(anthropic_model: str) -> str:
    """Map an Anthropic model name to the best free Gemini equivalent."""
    return GEMINI_MODEL_MAP.get(anthropic_model, "gemini-2.0-flash")


async def call_gemini(
    prompt: str,
    contract: "RoleContract",
    system_prompt: str | None = None,
) -> tuple[str, float]:
    """Call Google Gemini API as a free-tier Anthropic replacement.

    Args:
        prompt: The user prompt.
        contract: Role contract (used for model mapping and max_tokens).
        system_prompt: Optional system instruction override.

    Returns:
        (response_text, cost_usd) — cost is nominal ($0.0001) to register
        in budget tracking without affecting budgets meaningfully.

    Falls back to mock when GOOGLE_AI_API_KEY is absent.
    """
    api_key = os.getenv("GOOGLE_AI_API_KEY", "")
    gemini_model = _get_gemini_model(contract.model)

    if not api_key:
        logger.info(
            f"[MOCK-GEMINI] Calling {gemini_model} for {contract.role.value} "
            f"(no GOOGLE_AI_API_KEY — set AI_PROVIDER=anthropic or add key)"
        )
        return (
            f"[MOCK-GEMINI:{gemini_model}] Response to: {prompt[:100]}...",
            0.0,
        )

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        # Load system prompt from prompts module if not overridden
        if system_prompt is None:
            system_prompt = _get_system_prompt(contract)

        model = genai.GenerativeModel(
            model_name=gemini_model,
            system_instruction=system_prompt,
        )

        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=min(contract.max_output_tokens, 8192),
                temperature=0.7,
            ),
        )

        text = response.text if response.text else ""
        logger.info(
            f"Gemini {gemini_model} ({contract.role.value}): "
            f"{len(text)} chars"
        )
        return text, GEMINI_COST_PER_CALL

    except Exception as e:
        logger.error(f"Gemini API error ({gemini_model}): {e}")
        raise


def _get_system_prompt(contract: "RoleContract") -> str:
    """Load the system prompt for this role from prompts.py."""
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
