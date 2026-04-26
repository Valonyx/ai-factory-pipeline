"""
AI Factory Pipeline v5.8.12 — NVIDIA NIM Reranking Provider

Cross-encoder reranking to improve Scout search result quality.
Wired into: ScoutOrchestrator result ranking, RAG pipeline.

Models:
  nvidia/nv-rerank-qa-mistral-4b:1  — best accuracy, Mistral-based
  nvidia/llama-nemotron-rerank-1b-v2 — faster, lightweight

Endpoint: https://ai.api.nvidia.com/v1/retrieval/<model>/reranking

Required env var:
  NVIDIA_NIM_MULTI_API_KEY — covers both reranking models
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.nvidia_nim_reranking")

_RERANK_MODELS = [
    {
        "id": "nvidia/nv-rerank-qa-mistral-4b:1",
        "endpoint": "https://ai.api.nvidia.com/v1/retrieval/nvidia/nv-rerank-qa-mistral-4b/reranking",
    },
    {
        "id": "nvidia/llama-nemotron-rerank-1b-v2",
        "endpoint": "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking",
    },
]


def _get_api_key() -> str:
    return os.getenv("NVIDIA_NIM_MULTI_API_KEY", "") or os.getenv("NVIDIA_NIM_API_KEY", "")


async def rerank(
    query: str,
    passages: list[str],
    top_n: Optional[int] = None,
    model: Optional[str] = None,
) -> list[tuple[int, float, str]]:
    """Rerank passages by relevance to a query.

    Args:
        query: The search query.
        passages: List of text passages to rerank.
        top_n: Return only top N results (None = all).
        model: Specific model ID (None = try chain).

    Returns:
        List of (original_index, score, text) tuples, sorted by score descending.
    """
    if is_mock_provider():
        return [(i, 1.0 - i * 0.1, p) for i, p in enumerate(passages[:top_n or len(passages)])]

    if not passages:
        return []

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("NVIDIA_NIM_MULTI_API_KEY not configured — cannot rerank")

    models_to_try = [m for m in _RERANK_MODELS if m["id"] == model] if model else _RERANK_MODELS

    for model_cfg in models_to_try:
        try:
            return await _call_rerank(query, passages, top_n, model_cfg, api_key)
        except Exception as e:
            logger.warning(f"[nvidia_nim_reranking] {model_cfg['id']} failed: {e}")

    # Fallback: return original order with dummy scores
    logger.warning("[nvidia_nim_reranking] all models failed, returning original order")
    return [(i, 1.0, p) for i, p in enumerate(passages[:top_n or len(passages)])]


async def _call_rerank(
    query: str,
    passages: list[str],
    top_n: Optional[int],
    model_cfg: dict,
    api_key: str,
) -> list[tuple[int, float, str]]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload: dict = {
        "model": model_cfg["id"],
        "query": {"text": query},
        "passages": [{"text": p} for p in passages],
    }
    if top_n is not None:
        payload["top_n"] = top_n

    logger.debug(f"[nvidia_nim_reranking] {model_cfg['id']} — {len(passages)} passages")

    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(model_cfg["endpoint"], headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception(f"429 Rate Limited — {model_cfg['id']}")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized")
    response.raise_for_status()

    data = response.json()
    rankings = data.get("rankings", [])
    results = []
    for item in rankings:
        idx = item.get("index", 0)
        score = item.get("logit", item.get("score", 0.0))
        text = passages[idx] if idx < len(passages) else ""
        results.append((idx, float(score), text))

    return sorted(results, key=lambda x: x[1], reverse=True)
