"""
AI Factory Pipeline v5.8.12 — GitHub Models Provider (Free Tier)

GitHub Models provides free access to Llama 3.1 70B and other models
via an OpenAI-compatible API. No credit card required — uses your GitHub PAT.

Free account: https://github.com/marketplace/models (GitHub account)
Required env var:
  GITHUB_TOKEN — Personal Access Token (classic or fine-grained)

Model used: meta-llama-3.1-70b-instruct (free, no rate-limit card)
Endpoint: https://models.inference.ai.azure.com/chat/completions

Uses httpx.AsyncClient with OpenAI-compatible request format.
Docs: https://docs.github.com/en/github-models

Issue 20: Added as part of full free-provider integration.
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.github_models_provider")

GITHUB_MODELS_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
GITHUB_MODELS_MODEL = "meta-llama-3.1-70b-instruct"
GITHUB_MODELS_COST_PER_CALL: float = 0.0  # free tier


async def call_github_models(
    prompt: str,
    contract: "RoleContract",
) -> tuple[str, float]:
    """Call GitHub Models API as a free provider.

    Returns (response_text, cost_usd).
    Raises ValueError if GITHUB_TOKEN is not set.
    Raises on API errors so the caller can update the provider chain.
    """
    if is_mock_provider():
        mock_text = f"[MOCK:github_models:{contract.role.value}] {prompt[:80]}"
        logger.debug(f"[github_models] mock mode — returning stub response")
        return mock_text, GITHUB_MODELS_COST_PER_CALL

    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        raise ValueError("GITHUB_TOKEN not set")

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GITHUB_MODELS_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(contract.max_output_tokens, 4096),
        "temperature": 0.7,
    }

    logger.debug(f"[github_models] calling {GITHUB_MODELS_MODEL} for role={contract.role.value}")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            GITHUB_MODELS_ENDPOINT, headers=headers, json=payload
        )

    if response.status_code == 429:
        raise Exception("429 Rate Limited — GitHub Models rate limit reached")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check GITHUB_TOKEN")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.debug(f"[github_models] {GITHUB_MODELS_MODEL}: {len(text)} chars")
    return text, GITHUB_MODELS_COST_PER_CALL
