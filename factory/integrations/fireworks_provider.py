"""
AI Factory Pipeline v5.8 — Fireworks AI Provider

Fireworks AI specializes in structured output (JSON mode) — 4× faster than
standard vLLM for function-calling / structured responses. Ideal for S2
Blueprint generation, S1 legal classification, and any pipeline stage that
requires deterministic JSON output.

Required env var:
  FIREWORKS_API_KEY — API key from https://fireworks.ai/account/api-keys

Default model:  accounts/fireworks/models/llama-v3p3-70b-instruct
  (Best overall free-tier quality; Mixtral and Gemma also available)

Structured output model: accounts/fireworks/models/firefunction-v2
  (purpose-built for function calling / JSON schema enforcement)

Endpoint: https://api.fireworks.ai/inference/v1/chat/completions
  (OpenAI-compatible)

Docs: https://docs.fireworks.ai/api-reference/post-chatcompletions
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Optional

from factory.core.dry_run import is_mock_provider

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.fireworks_provider")

FIREWORKS_ENDPOINT = "https://api.fireworks.ai/inference/v1/chat/completions"

# Default general-purpose model (free trial credits)
FIREWORKS_MODEL = "accounts/fireworks/models/llama-v3p3-70b-instruct"
# Specialized structured-output model (function calling, JSON schema)
FIREWORKS_STRUCTURED_MODEL = "accounts/fireworks/models/firefunction-v2"

FIREWORKS_COST_PER_CALL: float = 0.0  # free trial credits


async def call_fireworks(
    prompt: str,
    contract: "RoleContract",
    structured: bool = False,
    response_schema: Optional[dict] = None,
) -> tuple[str, float]:
    """Call Fireworks AI for chat or structured output.

    Args:
        prompt: User prompt.
        contract: Role contract with token limits.
        structured: If True, use JSON mode + structured-output model.
        response_schema: Optional JSON Schema dict for strict output enforcement.

    Returns:
        (response_text, cost_usd).

    Raises:
        ValueError if FIREWORKS_API_KEY is not configured.
    """
    if is_mock_provider():
        return f"[MOCK:fireworks:{contract.role.value}] {prompt[:80]}", 0.0

    api_key = os.getenv("FIREWORKS_API_KEY", "")
    if not api_key:
        raise ValueError("FIREWORKS_API_KEY not configured")

    import httpx

    model = FIREWORKS_STRUCTURED_MODEL if structured else FIREWORKS_MODEL
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(getattr(contract, "max_output_tokens", 4096), 8192),
        "temperature": 0.1 if structured else 0.7,
    }

    # Enable JSON mode for structured requests
    if structured:
        if response_schema:
            payload["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }
        else:
            payload["response_format"] = {"type": "json_object"}

    logger.debug(f"[fireworks] calling {model} (structured={structured}) for role={contract.role.value}")

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(FIREWORKS_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception("429 Rate Limited — Fireworks AI rate limit reached")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check FIREWORKS_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.debug(f"[fireworks] {model}: {len(text)} chars")
    return text, FIREWORKS_COST_PER_CALL


async def call_fireworks_structured(
    prompt: str,
    contract: "RoleContract",
    schema: Optional[dict] = None,
) -> tuple[str, float]:
    """Convenience wrapper for structured JSON output via Fireworks.

    Use this for S2 blueprint generation, S1 legal classification, and any
    stage that benefits from guaranteed JSON schema compliance.
    """
    return await call_fireworks(prompt, contract, structured=True, response_schema=schema)
