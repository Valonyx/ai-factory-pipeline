"""
AI Factory Pipeline v5.8.12 — Cloudflare Workers AI Provider (Free Tier)

Cloudflare Workers AI provides free LLM inference via Llama 3.1 8B.
Free tier: 10,000 neurons/day at no cost — no credit card required.

Free account: https://dash.cloudflare.com (email sign-up)
Required env vars:
  CLOUDFLARE_ACCOUNT_ID  — your Cloudflare account ID
  CLOUDFLARE_API_TOKEN   — Workers AI API token (AI Gateway or CF API token)

Model used: @cf/meta/llama-3.1-8b-instruct (free, fast)

Uses httpx.AsyncClient (consistent with other adapters).
Docs: https://developers.cloudflare.com/workers-ai/

Issue 20: Added as part of full free-provider integration.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.cloudflare_provider")

CLOUDFLARE_BASE_URL = "https://api.cloudflare.com/client/v4/accounts"
CLOUDFLARE_MODEL = "@cf/meta/llama-3.1-8b-instruct"
CLOUDFLARE_COST_PER_CALL: float = 0.0  # free tier


async def call_cloudflare(
    prompt: str,
    contract: "RoleContract",
) -> tuple[str, float]:
    """Call Cloudflare Workers AI as a free provider.

    Returns (response_text, cost_usd).
    Raises ValueError if credentials are not configured.
    Raises on API errors so the caller can update the provider chain.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        mock_text = f"[MOCK:cloudflare:{contract.role.value}] {prompt[:80]}"
        logger.debug(f"[cloudflare] mock mode — returning stub response")
        return mock_text, CLOUDFLARE_COST_PER_CALL

    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")

    if not account_id or not api_token:
        raise ValueError("CLOUDFLARE credentials not set")

    endpoint = f"{CLOUDFLARE_BASE_URL}/{account_id}/ai/run/{CLOUDFLARE_MODEL}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": prompt}],
    }

    logger.debug(f"[cloudflare] calling {CLOUDFLARE_MODEL} for role={contract.role.value}")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(endpoint, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception("429 Rate Limited — Cloudflare Workers AI daily quota reached")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check CLOUDFLARE_API_TOKEN")
    response.raise_for_status()

    data = response.json()
    # Cloudflare returns {"result": {"response": "..."}, "success": true}
    result = data.get("result", {})
    text = result.get("response", "")
    if not text:
        logger.warning(f"[cloudflare] empty response: {data}")
        text = ""
    logger.debug(f"[cloudflare] {CLOUDFLARE_MODEL}: {len(text)} chars")
    return text, CLOUDFLARE_COST_PER_CALL
