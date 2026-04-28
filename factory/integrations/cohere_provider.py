"""
AI Factory Pipeline v5.8 — Cohere Provider

Cohere offers chat (command-r-plus), embeddings (embed-v4.0), and reranking.
Free trial: 1,000 req/month across all APIs — appropriate for BASIC mode.

Required env var:
  COHERE_API_KEY — API key from https://dashboard.cohere.com/api-keys

Chat model:      command-r-plus-08-2024
Embeddings model: embed-v4.0
Endpoint:        https://api.cohere.com/v2/chat

Docs: https://docs.cohere.com/reference/chat
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from factory.core.dry_run import is_mock_provider

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.cohere_provider")

COHERE_CHAT_ENDPOINT = "https://api.cohere.com/v2/chat"
COHERE_EMBED_ENDPOINT = "https://api.cohere.com/v2/embed"
COHERE_CHAT_MODEL = "command-r-plus-08-2024"
COHERE_EMBED_MODEL = "embed-v4.0"
COHERE_COST_PER_CALL: float = 0.0  # free trial tier


async def call_cohere(
    prompt: str,
    contract: "RoleContract",
) -> tuple[str, float]:
    """Call Cohere command-r-plus for chat/reasoning tasks.

    Returns (response_text, cost_usd).
    Raises ValueError if COHERE_API_KEY is not configured.
    Raises on API errors so the caller can cascade to the next provider.
    """
    if is_mock_provider():
        return f"[MOCK:cohere:{contract.role.value}] {prompt[:80]}", 0.0

    api_key = os.getenv("COHERE_API_KEY", "")
    if not api_key:
        raise ValueError("COHERE_API_KEY not configured")

    import httpx

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": COHERE_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(getattr(contract, "max_output_tokens", 4096), 4096),
        "temperature": 0.7,
    }

    logger.debug(f"[cohere] calling {COHERE_CHAT_MODEL} for role={contract.role.value}")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(COHERE_CHAT_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception("429 Rate Limited — Cohere free tier exhausted")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check COHERE_API_KEY")
    response.raise_for_status()

    data = response.json()
    # v2 response: data["message"]["content"][0]["text"]
    try:
        text = data["message"]["content"][0]["text"] or ""
    except (KeyError, IndexError, TypeError):
        # Fallback for alternate response shapes
        text = str(data.get("text", data.get("generations", [{}])[0].get("text", "")))

    logger.debug(f"[cohere] {COHERE_CHAT_MODEL}: {len(text)} chars")
    return text, COHERE_COST_PER_CALL


async def embed_with_cohere(texts: list[str], input_type: str = "search_document") -> list[list[float]]:
    """Embed texts using Cohere embed-v4.0.

    Args:
        texts: List of strings to embed (max 96 per call).
        input_type: 'search_document', 'search_query', 'classification', or 'clustering'.

    Returns:
        List of embedding vectors (1024-dim for embed-v4.0).

    Raises:
        ValueError if COHERE_API_KEY not set.
    """
    if is_mock_provider():
        return [[0.0] * 1024 for _ in texts]

    api_key = os.getenv("COHERE_API_KEY", "")
    if not api_key:
        raise ValueError("COHERE_API_KEY not configured")

    import httpx

    payload = {
        "model": COHERE_EMBED_MODEL,
        "texts": texts[:96],  # API max per batch
        "input_type": input_type,
        "embedding_types": ["float"],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            COHERE_EMBED_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )

    if response.status_code == 429:
        raise Exception("429 Rate Limited — Cohere embed free tier exhausted")
    response.raise_for_status()

    data = response.json()
    return data["embeddings"]["float"]
