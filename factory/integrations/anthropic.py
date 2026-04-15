"""
AI Factory Pipeline v5.8 — Real Anthropic Client

Production replacement for the stub Anthropic integration.

Implements:
  - §2.2.2  call_anthropic() — real API calls via anthropic.AsyncAnthropic
  - §3.2    Strategist prompts (Opus 4.6)
  - §3.3    Engineer prompts (Sonnet 4.5)
  - §3.6    Cost tracking from actual message.usage fields
  - §2.14   Budget Governor pre-check (via caller in roles.py)

Pricing verified 2025-02-27 from platform.claude.com/docs/en/about-claude/pricing:
  - claude-opus-4-6:            $5.00 input / $25.00 output per MTok
  - claude-opus-4-5-20250929:   $5.00 input / $25.00 output per MTok
  - claude-sonnet-4-5-20250929: $3.00 input / $15.00 output per MTok
  - claude-sonnet-4-20250514:   $3.00 input / $15.00 output per MTok
  - claude-haiku-4-5-20251001:  $1.00 input /  $5.00 output per MTok

Spec Authority: v5.6 §2.2, §3.2, §3.3, §3.6
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import anthropic

logger = logging.getLogger("factory.integrations.anthropic")


# ═══════════════════════════════════════════════════════════════════
# Pricing Table (per million tokens, USD)
# Verified 2025-02-27 — update if Anthropic changes pricing
# ═══════════════════════════════════════════════════════════════════

ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6":            {"input": 5.00,  "output": 25.00},
    "claude-opus-4-5-20250929":   {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6":          {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4-20250514":   {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001":  {"input": 1.00,  "output": 5.00},
}

# Fallback for unknown models — assume Sonnet-tier pricing
_DEFAULT_PRICING = {"input": 3.00, "output": 15.00}


# ═══════════════════════════════════════════════════════════════════
# Client Singleton
# ═══════════════════════════════════════════════════════════════════

_client: Optional[anthropic.AsyncAnthropic] = None


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Get or create the singleton AsyncAnthropic client.

    Reads ANTHROPIC_API_KEY from environment (standard SDK behavior).
    Configures timeout and max retries.
    """
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Required for production AI calls. "
                "Set via GCP Secret Manager (§2.15) or .env for local dev."
            )
        _client = anthropic.AsyncAnthropic(
            api_key=api_key,
            timeout=httpx_timeout(),
            max_retries=3,  # SDK built-in retry on transient errors (429, 500, 529)
        )
        logger.info("Anthropic AsyncAnthropic client initialized")
    return _client


def httpx_timeout() -> float:
    """Timeout for Anthropic API calls in seconds.

    Opus with large context can take 60-120s. Default 120s.
    Override with ANTHROPIC_TIMEOUT_SECONDS env var.
    """
    return float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "120"))


def reset_client() -> None:
    """Reset client singleton (for testing)."""
    global _client
    _client = None


# ═══════════════════════════════════════════════════════════════════
# Cost Calculation
# ═══════════════════════════════════════════════════════════════════

def calculate_cost(
    model: str, input_tokens: int, output_tokens: int,
) -> float:
    """Calculate USD cost from actual token usage.

    Spec: §3.6 — costs tracked per-call for circuit breaker enforcement.

    Args:
        model: Anthropic model string (e.g., "claude-opus-4-6").
        input_tokens: From message.usage.input_tokens.
        output_tokens: From message.usage.output_tokens.

    Returns:
        Cost in USD, rounded to 6 decimal places.
    """
    pricing = ANTHROPIC_PRICING.get(model, _DEFAULT_PRICING)
    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
    )
    return round(cost, 6)


# ═══════════════════════════════════════════════════════════════════
# Core API Call
# ═══════════════════════════════════════════════════════════════════

async def call_anthropic(
    prompt: str,
    model: str,
    max_tokens: int,
    system_prompt: str = "",
    temperature: float = 0.0,
) -> tuple[str, float, dict[str, int]]:
    """Make a real Anthropic API call.

    Spec: §2.2.2 — every Anthropic call routes through here.

    Args:
        prompt: User message content.
        model: Model string from ROLE_CONTRACTS.
        max_tokens: Maximum output tokens (from contract.max_output_tokens).
        system_prompt: System instructions for the role.
        temperature: Sampling temperature (0.0 = deterministic for code).

    Returns:
        Tuple of:
          - response_text: str — the model's text response
          - cost_usd: float — calculated from actual token usage
          - usage: dict — {"input_tokens": N, "output_tokens": N}

    Raises:
        anthropic.APIError: On non-retryable API errors.
        anthropic.APITimeoutError: On timeout (after SDK retries).
        anthropic.RateLimitError: On 429 after SDK retries exhausted.
    """
    client = get_anthropic_client()

    t0 = time.monotonic()

    # Build messages payload
    messages = [{"role": "user", "content": prompt}]

    # Build kwargs
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        message = await client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        logger.error(
            f"Anthropic API error: {e.status_code} {e.message} "
            f"(model={model})"
        )
        raise
    except anthropic.APITimeoutError:
        logger.error(
            f"Anthropic API timeout after {httpx_timeout()}s "
            f"(model={model}, prompt_len={len(prompt)})"
        )
        raise
    except anthropic.APIConnectionError as e:
        logger.error(f"Anthropic connection error: {e} (model={model})")
        raise

    elapsed = time.monotonic() - t0

    # Extract response text — handle multiple content blocks
    response_text = ""
    for block in message.content:
        if block.type == "text":
            response_text += block.text

    # Calculate cost from actual usage
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    cost_usd = calculate_cost(model, input_tokens, output_tokens)

    usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }

    logger.info(
        f"Anthropic call: model={model} "
        f"in={input_tokens} out={output_tokens} "
        f"cost=${cost_usd:.4f} elapsed={elapsed:.1f}s"
    )

    return response_text, cost_usd, usage


# ═══════════════════════════════════════════════════════════════════
# Structured JSON Parsing
# ═══════════════════════════════════════════════════════════════════

def parse_json_response(
    text: str, fallback: Any = None,
) -> Any:
    """Parse JSON from an AI response, handling common issues.

    Many AI responses wrap JSON in markdown fences or include
    preamble text. This function strips those and parses.

    Args:
        text: Raw response text from the model.
        fallback: Value to return if parsing fails.

    Returns:
        Parsed JSON object, or fallback if parsing fails.
    """
    # Strip markdown code fences
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object/array within the text
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue

    logger.warning(
        f"Failed to parse JSON from response "
        f"(length={len(text)}, preview={text[:100]}...)"
    )
    return fallback


# ═══════════════════════════════════════════════════════════════════
# JSON-Guaranteed Call (with retry)
# ═══════════════════════════════════════════════════════════════════

async def call_anthropic_json(
    prompt: str,
    model: str,
    max_tokens: int,
    system_prompt: str = "",
    max_retries: int = 2,
) -> tuple[Any, float, dict[str, int]]:
    """Call Anthropic and parse response as JSON, retrying on parse failure.

    Used by stages that require structured output (S0 extraction,
    S1 legal classification, S2 blueprint schema, etc.).

    Args:
        prompt: Should instruct the model to respond in JSON.
        model: Anthropic model string.
        max_tokens: Max output tokens.
        system_prompt: System instructions (should include JSON instruction).
        max_retries: Number of parse-failure retries (default 2).

    Returns:
        Tuple of (parsed_json, total_cost_usd, last_usage).
    """
    total_cost = 0.0
    last_usage = {"input_tokens": 0, "output_tokens": 0}

    for attempt in range(1 + max_retries):
        retry_prompt = prompt
        if attempt > 0:
            retry_prompt = (
                f"{prompt}\n\n"
                f"IMPORTANT: Your previous response was not valid JSON. "
                f"Respond with ONLY a JSON object, no markdown fences, "
                f"no explanatory text. Attempt {attempt + 1}/{1 + max_retries}."
            )

        text, cost, usage = await call_anthropic(
            prompt=retry_prompt,
            model=model,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            temperature=0.0,
        )
        total_cost += cost
        last_usage = usage

        parsed = parse_json_response(text)
        if parsed is not None:
            return parsed, total_cost, last_usage

        logger.warning(
            f"JSON parse failed (attempt {attempt + 1}/{1 + max_retries}), "
            f"model={model}"
        )

    # All retries exhausted — return raw text wrapped in error dict
    logger.error(
        f"JSON parse failed after {1 + max_retries} attempts, "
        f"returning error wrapper"
    )
    return {"_parse_error": True, "_raw_text": text}, total_cost, last_usage