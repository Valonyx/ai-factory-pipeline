"""
AI Factory Pipeline v5.8.12 — NVIDIA NIM Provider

NVIDIA NIM (NVIDIA Inference Microservices) provides OpenAI-compatible LLM
inference. Free tier available via build.nvidia.com (1000 credits/month).

Required env var:
  NVIDIA_NIM_API_KEY — API key from https://build.nvidia.com

Model used: meta/llama-3.3-70b-instruct
Endpoint:   https://integrate.api.nvidia.com/v1/chat/completions

Uses httpx.AsyncClient with OpenAI-compatible request format.
Docs: https://docs.api.nvidia.com/nim/reference/llm-apis
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.nvidia_nim_provider")

NVIDIA_NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_NIM_MODEL = "meta/llama-3.3-70b-instruct"
NVIDIA_NIM_COST_PER_CALL: float = 0.0001  # ~$0.0001 per call on free tier


async def call_nvidia_nim(
    prompt: str,
    contract: "RoleContract",
) -> tuple[str, float]:
    """Call NVIDIA NIM as a free-tier provider.

    Returns (response_text, cost_usd).
    Raises ValueError if NVIDIA_NIM_API_KEY is not configured.
    Raises on API errors so the caller can cascade to the next provider.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        mock_text = f"[MOCK:nvidia_nim:{contract.role.value}] {prompt[:80]}"
        logger.debug("[nvidia_nim] mock mode — returning stub response")
        return mock_text, 0.0

    api_key = os.getenv("NVIDIA_NIM_API_KEY", "")
    if not api_key:
        raise ValueError("NVIDIA_NIM_API_KEY not configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NVIDIA_NIM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(contract.max_output_tokens, 4096),
        "temperature": 0.7,
        "stream": False,
    }

    logger.debug(f"[nvidia_nim] calling {NVIDIA_NIM_MODEL} for role={contract.role.value}")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(NVIDIA_NIM_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception("429 Rate Limited — NVIDIA NIM monthly credits exhausted")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check NVIDIA_NIM_API_KEY")
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    logger.debug(f"[nvidia_nim] {NVIDIA_NIM_MODEL}: {len(text)} chars")
    return text, NVIDIA_NIM_COST_PER_CALL
