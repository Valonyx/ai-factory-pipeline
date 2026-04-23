"""
AI Factory Pipeline v5.8.16 — Embedding Chain

Unified embedding provider chain. Tries NVIDIA NIM embedding models in
quality order, falls back to Jina Embeddings v3. Returns typed result.

Provider roster (all free-tier):
  1. NVIDIA baai/bge-m3              — best multilingual general embeddings
     Key: NVIDIA_NIM_BGE_M3_API_KEY | NVIDIA_NIM_MULTI_API_KEY
  2. NVIDIA nvidia/nv-embedqa-e5-v5  — QA-tuned retrieval embeddings
     Key: NVIDIA_NIM_EMBEDQA_E5_API_KEY | NVIDIA_NIM_MULTI_API_KEY
  3. NVIDIA nvidia/nv-embed-v1       — high-dimensional general embeddings
     Key: NVIDIA_NIM_EMBED_V1_API_KEY | NVIDIA_NIM_MULTI_API_KEY
  4. NVIDIA nvidia/llama-nemotron-embed-1b-v2 — lightweight general
     Key: NVIDIA_NIM_EMBED_1B_API_KEY | NVIDIA_NIM_MULTI_API_KEY
  5. Jina jina-embeddings-v3         — multilingual, 8K context
     Key: JINA_API_KEY
     Register: https://jina.ai

Specialised entry points:
  embed_code(texts)       → uses nvidia/nv-embedcode-7b-v1
  embed_multimodal(texts) → uses nvidia/llama-nemotron-embed-vl-1b-v2

Configurable via EMBED_PROVIDER_CHAIN env var (comma-separated provider names).

Spec Authority: v5.8.16 §G-embed
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.embed_chain")

# Provider chain — configurable
_PROVIDER_CHAIN: list[str] = [
    p.strip()
    for p in os.getenv(
        "EMBED_PROVIDER_CHAIN",
        "nvidia_bge_m3,nvidia_embedqa_e5,nvidia_embed_v1,nvidia_embed_1b,jina_embeddings",
    ).split(",")
    if p.strip()
]

# Map provider name → (nvidia_model_or_None, jina_flag)
_NVIDIA_MODEL_MAP: dict[str, str] = {
    "nvidia_bge_m3":      "baai/bge-m3",
    "nvidia_embedqa_e5":  "nvidia/nv-embedqa-e5-v5",
    "nvidia_embed_v1":    "nvidia/nv-embed-v1",
    "nvidia_embed_1b":    "nvidia/llama-nemotron-embed-1b-v2",
    "nvidia_embedcode":   "nvidia/nv-embedcode-7b-v1",
    "nvidia_embed_vl":    "nvidia/llama-nemotron-embed-vl-1b-v2",
}


# ── Public API ───────────────────────────────────────────────────────────────


async def embed_texts(
    texts: list[str],
    mode: str = "balanced",
) -> dict:
    """Embed a list of texts using the free provider chain.

    Tries providers in priority order; stops at first success.
    Returns a typed result dict — never raises on all-fail.

    Args:
        texts: List of strings to embed.
        mode:  "basic" | "balanced" | "custom" | "turbo" (all free here).

    Returns:
        {
          "embeddings": list[list[float]],  — one vector per input text
          "model":      str,                — model used
          "source":     str,                — provider name
          "degraded":   bool,               — True only on all-fail
          "error":      str,                — only when degraded=True
        }
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return {
            "embeddings": [[0.0] * 128] * len(texts),
            "model": "mock",
            "source": "mock",
            "degraded": False,
        }

    if not texts:
        return {"embeddings": [], "model": "", "source": "none", "degraded": False}

    errors: list[str] = []
    for provider in _PROVIDER_CHAIN:
        try:
            vecs, model = await _call_embed_provider(provider, texts)
            _track_cost(provider)
            logger.info("[embed_chain] %s succeeded — %d vecs dim=%d", provider, len(vecs), len(vecs[0]) if vecs else 0)
            return {
                "embeddings": vecs,
                "model": model,
                "source": provider,
                "degraded": False,
            }
        except Exception as e:
            err = f"{provider}: {e}"
            errors.append(err)
            logger.warning("[embed_chain] %s", err)

    logger.error("[embed_chain] All providers failed: %s", "; ".join(errors))
    return {
        "embeddings": [],
        "model": "",
        "source": "degraded",
        "degraded": True,
        "error": "; ".join(errors),
    }


async def embed_code(texts: list[str]) -> dict:
    """Embed source code using the NIM code-specific model."""
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return {"embeddings": [[0.0] * 256] * len(texts), "model": "mock", "source": "mock", "degraded": False}
    try:
        vecs, model = await _call_nvidia_embed(texts, "nvidia/nv-embedcode-7b-v1")
        _track_cost("nvidia_embedcode")
        return {"embeddings": vecs, "model": model, "source": "nvidia_embedcode", "degraded": False}
    except Exception as e:
        logger.warning("[embed_chain] embed_code failed: %s", e)
        return embed_texts.__func__ if False else await embed_texts(texts)  # type: ignore[attr-defined]


async def embed_multimodal(texts: list[str]) -> dict:
    """Embed text using the NIM multimodal (VL) model."""
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return {"embeddings": [[0.0] * 256] * len(texts), "model": "mock", "source": "mock", "degraded": False}
    try:
        vecs, model = await _call_nvidia_embed(
            texts, "nvidia/llama-nemotron-embed-vl-1b-v2",
            extra_body={"modality": ["text"], "input_type": "query", "truncate": "NONE"},
        )
        _track_cost("nvidia_embed_vl")
        return {"embeddings": vecs, "model": model, "source": "nvidia_embed_vl", "degraded": False}
    except Exception as e:
        logger.warning("[embed_chain] embed_multimodal failed: %s", e)
        return await embed_texts(texts)


# ── Provider dispatch ────────────────────────────────────────────────────────


async def _call_embed_provider(provider: str, texts: list[str]) -> tuple[list[list[float]], str]:
    """Return (vectors, model_id) or raise."""
    if provider in _NVIDIA_MODEL_MAP:
        model = _NVIDIA_MODEL_MAP[provider]
        return await _call_nvidia_embed(texts, model)

    if provider == "jina_embeddings":
        from factory.integrations.jina_provider import call_jina_embeddings
        vecs = await call_jina_embeddings(texts)
        return vecs, "jina-embeddings-v3"

    raise ValueError(f"Unknown embed provider: {provider}")


async def _call_nvidia_embed(
    texts: list[str],
    model: str,
    extra_body: Optional[dict] = None,
) -> tuple[list[list[float]], str]:
    """Call NVIDIA NIM embeddings endpoint. Returns (vectors, model_id)."""
    from factory.integrations.nvidia_nim_embeddings import _get_api_key, NVIDIA_EMBEDDINGS_ENDPOINT

    api_key = _get_api_key(model)
    if not api_key:
        raise ValueError(f"No API key for NIM embedding model {model}")

    payload: dict = {
        "input": texts,
        "model": model,
        "encoding_format": "float",
    }
    if extra_body:
        payload.update(extra_body)

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            NVIDIA_EMBEDDINGS_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code == 429:
        raise Exception(f"429 rate-limited — {model}")
    if resp.status_code in (401, 403):
        raise ValueError(f"{resp.status_code} Unauthorized — {model}")
    resp.raise_for_status()

    data = resp.json()
    vecs = [item["embedding"] for item in data["data"]]
    return vecs, model


# ── Cost tracking ────────────────────────────────────────────────────────────

_PROVIDER_COST: dict[str, float] = {
    "nvidia_bge_m3":     0.0,
    "nvidia_embedqa_e5": 0.0,
    "nvidia_embed_v1":   0.0,
    "nvidia_embed_1b":   0.0,
    "nvidia_embedcode":  0.0,
    "nvidia_embed_vl":   0.0,
    "jina_embeddings":   0.0001,
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
