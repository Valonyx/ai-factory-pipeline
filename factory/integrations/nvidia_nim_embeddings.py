"""
AI Factory Pipeline v5.8.12 — NVIDIA NIM Embeddings Provider

Provides text and multimodal embeddings via NVIDIA's NIM APIs.
Used for: Mother Memory RAG, Scout result reranking, legal document similarity.

Models (in quality/specificity order):
  1. baai/bge-m3              — best general-purpose multilingual embeddings
  2. nvidia/nv-embedqa-e5-v5  — QA-tuned retrieval
  3. nvidia/nv-embed-v1       — high-dim general embeddings
  4. nvidia/nv-embedcode-7b-v1 — code-specific (via multi key)
  5. nvidia/llama-nemotron-embed-vl-1b-v2 — multimodal (text+image)
  6. nvidia/llama-nemotron-embed-1b-v2 — lightweight general

All models use the OpenAI-compatible embeddings endpoint.
Endpoint: https://integrate.api.nvidia.com/v1/embeddings

Required env vars (one per model, falls back to NVIDIA_NIM_MULTI_API_KEY):
  NVIDIA_NIM_BGE_M3_API_KEY
  NVIDIA_NIM_EMBEDQA_E5_API_KEY
  NVIDIA_NIM_EMBED_VL_API_KEY
  NVIDIA_NIM_EMBED_V1_API_KEY
  NVIDIA_NIM_EMBED_1B_API_KEY
  NVIDIA_NIM_MULTI_API_KEY  (fallback for all + embedcode)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.nvidia_nim_embeddings")

NVIDIA_EMBEDDINGS_ENDPOINT = "https://integrate.api.nvidia.com/v1/embeddings"

_MODEL_KEY_MAP: dict[str, str] = {
    "baai/bge-m3":                      "NVIDIA_NIM_BGE_M3_API_KEY",
    "nvidia/nv-embedqa-e5-v5":           "NVIDIA_NIM_EMBEDQA_E5_API_KEY",
    "nvidia/llama-nemotron-embed-vl-1b-v2": "NVIDIA_NIM_EMBED_VL_API_KEY",
    "nvidia/nv-embed-v1":               "NVIDIA_NIM_EMBED_V1_API_KEY",
    "nvidia/nv-embedcode-7b-v1":        "NVIDIA_NIM_MULTI_API_KEY",
    "nvidia/llama-nemotron-embed-1b-v2": "NVIDIA_NIM_EMBED_1B_API_KEY",
}

# Priority order for embedding model selection
EMBEDDING_MODEL_CHAIN = [
    "baai/bge-m3",
    "nvidia/nv-embedqa-e5-v5",
    "nvidia/nv-embed-v1",
    "nvidia/llama-nemotron-embed-1b-v2",
]

CODE_EMBEDDING_MODEL = "nvidia/nv-embedcode-7b-v1"
MULTIMODAL_EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"


def _get_api_key(model: str) -> str:
    env_var = _MODEL_KEY_MAP.get(model, "NVIDIA_NIM_MULTI_API_KEY")
    key = os.getenv(env_var, "") or os.getenv("NVIDIA_NIM_MULTI_API_KEY", "")
    return key


async def embed_texts(
    texts: list[str],
    model: Optional[str] = None,
    truncate: str = "END",
    input_type: str = "query",
) -> list[list[float]]:
    """Embed a list of texts using NVIDIA NIM embeddings.

    Args:
        texts: Input texts to embed (max 512 tokens each for most models).
        model: Model ID to use. If None, tries the chain in order.
        truncate: "END" or "NONE" — truncation strategy.
        input_type: "query" or "passage" for retrieval models.

    Returns:
        List of float vectors, one per input text.

    Raises:
        ValueError if no key is configured or all models fail.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        logger.debug("[nvidia_nim_embeddings] mock mode")
        return [[0.0] * 1024 for _ in texts]

    if not texts:
        return []

    models_to_try = [model] if model else EMBEDDING_MODEL_CHAIN

    for model_id in models_to_try:
        api_key = _get_api_key(model_id)
        if not api_key:
            logger.debug(f"[nvidia_nim_embeddings] no key for {model_id}, skipping")
            continue

        try:
            result = await _call_embeddings(texts, model_id, api_key, truncate, input_type)
            return result
        except Exception as e:
            logger.warning(f"[nvidia_nim_embeddings] {model_id} failed: {e}")

    raise ValueError("All NVIDIA NIM embedding models failed or have no API key")


async def _call_embeddings(
    texts: list[str],
    model: str,
    api_key: str,
    truncate: str,
    input_type: str,
) -> list[list[float]]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": model,
        "input": texts,
        "truncate": truncate,
    }
    if "embedqa" in model or "bge" in model:
        payload["input_type"] = input_type

    logger.debug(f"[nvidia_nim_embeddings] calling {model} for {len(texts)} texts")

    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(NVIDIA_EMBEDDINGS_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception(f"429 Rate Limited — {model}")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check key for {model}")
    response.raise_for_status()

    data = response.json()
    embeddings = [item["embedding"] for item in data["data"]]
    logger.debug(f"[nvidia_nim_embeddings] {model}: {len(embeddings)} vectors, dim={len(embeddings[0]) if embeddings else 0}")
    return embeddings


async def embed_code(snippets: list[str]) -> list[list[float]]:
    """Embed code snippets using the code-optimized model."""
    return await embed_texts(snippets, model=CODE_EMBEDDING_MODEL)


async def embed_for_retrieval(passages: list[str]) -> list[list[float]]:
    """Embed passages for retrieval (QA-tuned models preferred)."""
    return await embed_texts(passages, model="nvidia/nv-embedqa-e5-v5", input_type="passage")
