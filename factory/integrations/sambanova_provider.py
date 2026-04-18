"""
AI Factory Pipeline v5.8.12 — SambaNova Cloud Provider

SambaNova Cloud offers fast LLM inference via an OpenAI-compatible API.
Free tier: generous limits on Llama 3.3 70B — no credit card required.

Required env var:
  SAMBANOVA_API_KEY — API key from https://cloud.sambanova.ai

Model used: Meta-Llama-3.3-70B-Instruct
Endpoint:   https://api.sambanova.ai/v1/chat/completions

Uses httpx.AsyncClient with OpenAI-compatible request format.
Docs: https://docs.sambanova.ai/cloud/latest/
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.sambanova_provider")

SAMBANOVA_ENDPOINT = "https://api.sambanova.ai/v1/chat/completions"
SAMBANOVA_MODEL = "Meta-Llama-3.3-70B-Instruct"
SAMBANOVA_COST_PER_CALL: float = 0.0  # free tier


async def call_sambanova(
    prompt: str,
    contract: "RoleContract",
) -> tuple[str, float]:
    """Call SambaNova Cloud as a free-tier provider.

    Returns (response_text, cost_usd).
    Raises ValueError if SAMBANOVA_API_KEY is not configured.
    Raises on API errors so the caller can cascade to the next provider.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        mock_text = f"[MOCK:sambanova:{contract.role.value}] {prompt[:80]}"
        logger.debug("[sambanova] mock mode — returning stub response")
        return mock_text, 0.0

    api_key = os.getenv("SAMBANOVA_API_KEY", "")
    if not api_key:
        raise ValueError("SAMBANOVA_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": SAMBANOVA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(contract.max_output_tokens, 4096),
        "temperature": 0.7,
        "stream": False,
    }

    logger.debug(f"[sambanova] calling {SAMBANOVA_MODEL} for role={contract.role.value}")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(SAMBANOVA_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception("429 Rate Limited — SambaNova Cloud rate limit reached")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check SAMBANOVA_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.debug(f"[sambanova] {SAMBANOVA_MODEL}: {len(text)} chars")
    return text, SAMBANOVA_COST_PER_CALL
