"""
AI Factory Pipeline v5.8.16 — Reranking Chain

Unified cross-encoder reranking chain. Tries NVIDIA NIM rerankers first
(highest accuracy), falls back to Jina Reranker v2. Returns typed result.

Provider roster (all free-tier):
  1. NVIDIA nv-rerank-qa-mistral-4b:1   — best accuracy, Mistral-based
     Key: NVIDIA_NIM_MULTI_API_KEY
  2. NVIDIA llama-nemotron-rerank-1b-v2 — lightweight, fast
     Key: NVIDIA_NIM_MULTI_API_KEY
  3. Jina jina-reranker-v2-base-multilingual — multilingual, 8K context
     Key: JINA_API_KEY
     Register: https://jina.ai

Usage:
    result = await rerank_passages(query, passages, top_n=5)
    # result["ranked"] is list of (original_index, score, text) tuples

Configurable via RERANK_PROVIDER_CHAIN env var.

Spec Authority: v5.8.16 §G-rerank
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.rerank_chain")

_PROVIDER_CHAIN: list[str] = [
    p.strip()
    for p in os.getenv(
        "RERANK_PROVIDER_CHAIN",
        "nvidia_rerank_mistral4b,nvidia_rerank_nemotron1b,jina_rerank",
    ).split(",")
    if p.strip()
]


# ── Public API ───────────────────────────────────────────────────────────────


async def rerank_passages(
    query: str,
    passages: list[str],
    top_n: Optional[int] = None,
    mode: str = "balanced",
) -> dict:
    """Rerank passages by relevance to a query.

    Tries providers in priority order; stops at first success.
    On all-fail: returns passages in original order (never raises).

    Args:
        query:    The search query.
        passages: List of text passages to rerank.
        top_n:    Return only top N results (None = all passages).
        mode:     "basic" | "balanced" | "custom" | "turbo".

    Returns:
        {
          "ranked":   list[(int, float, str)],  — (orig_idx, score, text)
          "model":    str,
          "source":   str,
          "degraded": bool,
          "error":    str,   — only when degraded=True
        }
    """
    if is_mock_provider():
        ranked = [(i, 1.0 - i * 0.1, p) for i, p in enumerate(passages[:top_n or len(passages)])]
        return {"ranked": ranked, "model": "mock", "source": "mock", "degraded": False}

    if not passages:
        return {"ranked": [], "model": "", "source": "none", "degraded": False}

    errors: list[str] = []
    for provider in _PROVIDER_CHAIN:
        try:
            ranked, model = await _call_rerank_provider(provider, query, passages, top_n)
            _track_cost(provider)
            logger.info("[rerank_chain] %s succeeded — %d results", provider, len(ranked))
            return {"ranked": ranked, "model": model, "source": provider, "degraded": False}
        except Exception as e:
            err = f"{provider}: {e}"
            errors.append(err)
            logger.warning("[rerank_chain] %s", err)

    # All-fail: return original order so the pipeline doesn't halt
    logger.error("[rerank_chain] All providers failed: %s", "; ".join(errors))
    fallback = [(i, 0.0, p) for i, p in enumerate(passages[:top_n or len(passages)])]
    return {
        "ranked": fallback,
        "model": "",
        "source": "degraded",
        "degraded": True,
        "error": "; ".join(errors),
    }


# ── Provider dispatch ────────────────────────────────────────────────────────


async def _call_rerank_provider(
    provider: str,
    query: str,
    passages: list[str],
    top_n: Optional[int],
) -> tuple[list[tuple[int, float, str]], str]:
    """Return (ranked_list, model_id) or raise."""
    if provider == "nvidia_rerank_mistral4b":
        from factory.integrations.nvidia_nim_reranking import rerank as nim_rerank
        result = await nim_rerank(query, passages, top_n=top_n, model="nvidia/nv-rerank-qa-mistral-4b:1")
        return result, "nvidia/nv-rerank-qa-mistral-4b:1"

    if provider == "nvidia_rerank_nemotron1b":
        from factory.integrations.nvidia_nim_reranking import rerank as nim_rerank
        result = await nim_rerank(query, passages, top_n=top_n, model="nvidia/llama-nemotron-rerank-1b-v2")
        return result, "nvidia/llama-nemotron-rerank-1b-v2"

    if provider == "jina_rerank":
        from factory.integrations.jina_provider import call_jina_rerank
        result = await call_jina_rerank(query, passages, top_n=top_n)
        return result, "jina-reranker-v2-base-multilingual"

    raise ValueError(f"Unknown rerank provider: {provider}")


# ── Cost tracking ────────────────────────────────────────────────────────────

_PROVIDER_COST: dict[str, float] = {
    "nvidia_rerank_mistral4b":  0.0,
    "nvidia_rerank_nemotron1b": 0.0,
    "jina_rerank":              0.0001,
}


def _track_cost(provider: str) -> None:
    try:
        from factory.core.quota_tracker import get_quota_tracker
        import asyncio
        qt = get_quota_tracker()
        asyncio.create_task(
            qt.record_usage(provider, tokens=0, calls=1,
                            cost_usd=_PROVIDER_COST.get(provider, 0.0))
        )
    except Exception:
        pass
