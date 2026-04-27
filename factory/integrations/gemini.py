"""
AI Factory Pipeline v5.8 — Google Gemini Free-Tier Provider

DEV ALTERNATIVE for Anthropic when API credits are unavailable.
Switch back to Anthropic by setting AI_PROVIDER=anthropic in .env.

Free-tier limits (as of 2026-04):
  - gemini-2.5-pro:        50 RPD, rate-limited  (most capable — Strategist)
  - gemini-2.5-flash:    1500 RPD, 1M TPM        (fast + capable — Engineer)
  - gemini-2.5-flash-lite: same free tier         (fastest — QuickFix)
  No credit card required. Free at: aistudio.google.com

Role mapping (dev only):
  - Strategist → gemini-2.5-pro         (architect-grade reasoning)
  - Engineer   → gemini-2.5-flash        (code generation)
  - QuickFix   → gemini-2.5-flash-lite   (fast syntax fixes)

SDK: google-genai (replaces deprecated google-generativeai)
Pricing: $0.00 while within free-tier limits.
Switch to Anthropic for production — better JSON adherence, no daily limits.

Dev note (NB3-DEV-001): Added as a free-tier development alternative when
Anthropic API credits were unavailable. All role contracts, prompts, and cost
tracking logic remain identical — only the underlying model provider changes.
Remove AI_PROVIDER=gemini from .env to revert to Anthropic.

Spec Authority: v5.8 §2.2 (provider-agnostic role interface)
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

GEMINI_MODEL_MAP: dict[str, str] = {
    # Strategist (Opus-class) → gemini-2.5-flash (20 req/day free, most capable)
    # Used sparingly — 20 RPD is enough for Strategist calls which are infrequent.
    "claude-opus-4-6":            "gemini-2.5-flash",
    "claude-opus-4-5-20250929":   "gemini-2.5-flash",
    # Engineer (Sonnet-class) → gemini-2.5-flash-lite (high quota, good quality)
    "claude-sonnet-4-5-20250929": "gemini-2.5-flash-lite",
    "claude-sonnet-4-20250514":   "gemini-2.5-flash-lite",
    # QuickFix (Haiku-class) → gemini-2.5-flash-lite (highest free-tier quota)
    "claude-haiku-4-5-20251001":  "gemini-2.5-flash-lite",
}

# Effective cost = $0 in free tier — nominal value so budgets register non-zero
GEMINI_COST_PER_CALL: float = 0.0001


def _get_gemini_model(anthropic_model: str) -> str:
    """Map an Anthropic model name to the best free Gemini equivalent."""
    return GEMINI_MODEL_MAP.get(anthropic_model, "gemini-2.5-flash-lite")


def get_gemini_api_key() -> str:
    """Canonical resolver: tries GOOGLE_AI_API_KEY (primary) then GEMINI_API_KEY (alias)."""
    return (
        os.getenv("GOOGLE_AI_API_KEY", "")
        or os.getenv("GEMINI_API_KEY", "")
        or os.getenv("GOOGLE_API_KEY", "")
    )


async def call_gemini(
    prompt: str,
    contract: "RoleContract",
    system_prompt: str | None = None,
) -> tuple[str, float]:
    """Call Google Gemini API as a free-tier Anthropic replacement.

    Uses the google-genai SDK (replaces deprecated google-generativeai).

    Args:
        prompt: The user prompt.
        contract: Role contract (used for model mapping and max_tokens).
        system_prompt: Optional system instruction override.

    Returns:
        (response_text, cost_usd) — cost is nominal ($0.0001) for budget tracking.

    Falls back to mock when GOOGLE_AI_API_KEY is absent.
    """
    api_key = get_gemini_api_key()
    gemini_model = _get_gemini_model(contract.model)

    if not api_key:
        logger.info(
            f"[MOCK-GEMINI] Calling {gemini_model} for {contract.role.value} "
            "(no GOOGLE_AI_API_KEY — set AI_PROVIDER=anthropic or add key)"
        )
        return (
            f"[MOCK-GEMINI:{gemini_model}] Response to: {prompt[:100]}...",
            0.0,
        )

    try:
        from google import genai
        from google.genai import types
        import asyncio as _asyncio

        client = genai.Client(api_key=api_key)

        if system_prompt is None:
            system_prompt = _get_system_prompt(contract)

        # Retry up to 3 times on 429 rate-limit with exponential backoff
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.aio.models.generate_content(
                    model=gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=min(contract.max_output_tokens, 8192),
                        temperature=0.7,
                    ),
                )
                text = _strip_markdown_fences(response.text or "")
                logger.info(
                    f"Gemini {gemini_model} ({contract.role.value}): {len(text)} chars"
                )
                return text, GEMINI_COST_PER_CALL

            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if "429" in err_str and attempt < 2:
                    wait = 20 * (attempt + 1)  # 20s, 40s
                    logger.warning(
                        f"Gemini 429 rate limit ({gemini_model}), "
                        f"retry {attempt + 1}/2 in {wait}s…"
                    )
                    await _asyncio.sleep(wait)
                else:
                    raise

        raise last_exc  # type: ignore[misc]

    except Exception as e:
        logger.error(f"Gemini API error ({gemini_model}): {e}")
        raise


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences that Gemini wraps around JSON responses.

    Gemini often returns: ```json\n{...}\n```
    The pipeline expects: {...}
    This normalises the output so json.loads() succeeds downstream.
    """
    import re
    # Strip ```json ... ``` or ``` ... ``` blocks
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    stripped = re.sub(r"\n?```\s*$", "", stripped.strip(), flags=re.MULTILINE)
    return stripped.strip()


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


async def _call_gemini_raw(
    prompt: str,
    max_tokens: int = 1200,
    temperature: float = 0.3,
) -> str:
    """Call Gemini without a RoleContract (used by Scout synthesis & AI Scout).

    Uses gemini-2.5-flash-lite — fastest, highest free quota.
    Raises on error so callers can cascade to the next provider.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        raise ValueError("GOOGLE_AI_API_KEY not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=min(max_tokens, 8192),
            temperature=temperature,
        ),
    )
    text = _strip_markdown_fences(response.text or "").strip()
    if not text:
        raise ValueError("Gemini returned empty response")
    return text
