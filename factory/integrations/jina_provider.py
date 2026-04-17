"""
AI Factory Pipeline v5.8.12 — Jina AI Provider (Retrieval / Web-to-Text)

Jina AI provides:
  - Reader API: convert any URL to clean text (free without key)
  - Embeddings API: generate text embeddings (free with key)
  - Reranking API: rerank search results (free with key)

Optional env var:
  JINA_API_KEY — Jina API key (reader works without key, embeddings require one)

Free tier: Reader works without auth. Embeddings require free signup.
Docs: https://jina.ai/reader/, https://jina.ai/embeddings/

Issue 20: Added as part of full free-provider integration.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("factory.integrations.jina_provider")

JINA_READER_BASE = "https://r.jina.ai"
JINA_EMBEDDINGS_ENDPOINT = "https://api.jina.ai/v1/embeddings"
JINA_EMBEDDINGS_MODEL = "jina-embeddings-v3"


async def call_jina_reader(url: str) -> str:
    """Fetch a URL and return its clean text content via Jina Reader.

    Works without an API key (free public access).
    Raises ValueError if the URL is empty or the request fails.
    Returns a non-empty string on success.
    """
    if not url or not url.strip():
        raise ValueError("call_jina_reader: url must be non-empty")

    api_key = os.getenv("JINA_API_KEY", "")
    headers: dict[str, str] = {
        "Accept": "text/plain",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Normalize URL — strip protocol if present for Jina Reader path format
    clean_url = url.strip()
    reader_url = f"{JINA_READER_BASE}/{clean_url}"

    logger.debug(f"[jina_reader] fetching {reader_url} (auth={'yes' if api_key else 'no'})")

    import httpx
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(reader_url, headers=headers)

    if response.status_code == 402:
        raise ValueError("Jina Reader requires API key for this content — set JINA_API_KEY")
    if response.status_code == 429:
        raise ValueError("Jina Reader rate limited — try again later or add JINA_API_KEY")
    response.raise_for_status()

    text = response.text.strip()
    if not text:
        raise ValueError(f"Jina Reader returned empty content for {url}")

    logger.debug(f"[jina_reader] received {len(text)} chars for {url}")
    return text


async def call_jina_embeddings(
    texts: list[str],
    api_key: str = "",
) -> list[list[float]]:
    """Generate embeddings for a list of texts using Jina Embeddings v3.

    Requires a Jina API key. Falls back to raising ValueError if key is absent.
    Returns a list of float vectors (one per input text).
    """
    if not api_key:
        api_key = os.getenv("JINA_API_KEY", "")

    if not api_key:
        raise ValueError("JINA_API_KEY not set — cannot call Jina Embeddings API")

    if not texts:
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": JINA_EMBEDDINGS_MODEL,
        "input": texts,
    }

    logger.debug(f"[jina_embeddings] embedding {len(texts)} texts with {JINA_EMBEDDINGS_MODEL}")

    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            JINA_EMBEDDINGS_ENDPOINT, headers=headers, json=payload
        )

    if response.status_code == 401:
        raise ValueError("Jina Embeddings: invalid JINA_API_KEY")
    if response.status_code == 429:
        logger.warning("[jina_embeddings] rate limited")
        raise ValueError("Jina Embeddings rate limited — try again later")
    response.raise_for_status()

    data = response.json()
    embeddings = [item["embedding"] for item in data["data"]]
    logger.debug(f"[jina_embeddings] returned {len(embeddings)} vectors of dim {len(embeddings[0]) if embeddings else 0}")
    return embeddings
