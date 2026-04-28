"""
AI Factory Pipeline v5.8.16 — NVIDIA NIM Chat Provider

NVIDIA NIM provides OpenAI-compatible LLM inference across many models.
All models use https://integrate.api.nvidia.com/v1/chat/completions

Model tiers (routed from call_nvidia_nim via provider arg):
  ULTRA-PREMIUM  kimi_k2              moonshotai/kimi-k2.5 (reasoning)
  ULTRA-PREMIUM  nvidia_nim_405b      meta/llama-3.1-405b-instruct
  PAID_PREMIUM   nvidia_nim_mistral_large mistralai/mistral-large-3-675b-instruct-2512
  PAID_CHEAP     nvidia_nim_mixtral   mistralai/mixtral-8x22b-instruct-v0.1
  PAID_CHEAP     nvidia_nim_ministral14b mistralai/ministral-14b-instruct-2512
  FREE           nvidia_nim           meta/llama-3.3-70b-instruct  [default]
  FREE           nvidia_nim_gemma27b  google/gemma-3-27b-it
  FREE           nvidia_nim_gemma2b   google/gemma-2-2b-it
  FREE           nvidia_nim_phi4mini  microsoft/phi-4-mini-instruct
  FREE           nvidia_nim_fast      meta/llama-3.1-8b-instruct

All models use NVIDIA_NIM_MULTI_API_KEY as fallback when dedicated key absent.
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import RoleContract

logger = logging.getLogger("factory.integrations.nvidia_nim_provider")

NVIDIA_NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"

# ── Model registry ──────────────────────────────────────────────────
_MODEL_REGISTRY: dict[str, dict] = {
    # provider_name → {model_id, env_key, cost_per_call}
    "nvidia_nim": {
        "model": "meta/llama-3.3-70b-instruct",
        "key_env": "NVIDIA_NIM_API_KEY",
        "cost": 0.0001,
    },
    "kimi_k2": {
        "model": "moonshotai/kimi-k2.5",
        "key_env": "NVIDIA_NIM_KIMI_API_KEY",
        "cost": 0.002,
    },
    "nvidia_nim_405b": {
        "model": "meta/llama-3.1-405b-instruct",
        "key_env": "NVIDIA_NIM_LLAMA405B_API_KEY",
        "cost": 0.005,
    },
    "nvidia_nim_mixtral": {
        "model": "mistralai/mixtral-8x22b-instruct-v0.1",
        "key_env": "NVIDIA_NIM_MIXTRAL_API_KEY",
        "cost": 0.0,
    },
    "nvidia_nim_gemma27b": {
        "model": "google/gemma-3-27b-it",
        "key_env": "NVIDIA_NIM_GEMMA27B_API_KEY",
        "cost": 0.0,
    },
    "nvidia_nim_fast": {
        "model": "meta/llama-3.1-8b-instruct",
        "key_env": "NVIDIA_NIM_LLAMA8B_API_KEY",
        "cost": 0.0,
    },
    # ── New in v5.8.16 ───────────────────────────────────────────────
    "nvidia_nim_mistral_large": {
        "model": "mistralai/mistral-large-3-675b-instruct-2512",
        "key_env": "NVIDIA_NIM_MULTI_API_KEY",
        "cost": 0.003,
    },
    "nvidia_nim_ministral14b": {
        "model": "mistralai/ministral-14b-instruct-2512",
        "key_env": "NVIDIA_NIM_MULTI_API_KEY",
        "cost": 0.0,
    },
    "nvidia_nim_phi4mini": {
        "model": "microsoft/phi-4-mini-instruct",
        "key_env": "NVIDIA_NIM_MULTI_API_KEY",
        "cost": 0.0,
    },
    "nvidia_nim_gemma2b": {
        "model": "google/gemma-2-2b-it",
        "key_env": "NVIDIA_NIM_MULTI_API_KEY",
        "cost": 0.0,
    },
    # ── Added April 2026 — keys provided by operator ─────────────────
    "nvidia_nim_glm": {
        # ZHIPU AI GLM-4.7 — strong multilingual (Arabic/Chinese/English) reasoning
        # Correct model ID verified via /v1/models: z-ai/glm4.7
        "model": "z-ai/glm4.7",
        "key_env": "NVIDIA_NIM_GLM_API_KEY",
        "cost": 0.0,
    },
    "nvidia_nim_minimax": {
        # MiniMax M2.7 — 1M context window, excellent for long legal dossiers
        # Correct model ID verified via /v1/models: minimaxai/minimax-m2.7
        "model": "minimaxai/minimax-m2.7",
        "key_env": "NVIDIA_NIM_MINIMAX_API_KEY",
        "cost": 0.0,
    },
    "nvidia_nim_phi4": {
        # Phi-4 Multimodal Instruct — vision + text + code
        "model": "microsoft/phi-4-multimodal-instruct",
        "key_env": "NVIDIA_NIM_PHI4_API_KEY",
        "cost": 0.0,
    },
}

# Fallback key used when a model-specific key is absent
_FALLBACK_KEY_ENV = "NVIDIA_NIM_MULTI_API_KEY"


def _resolve_key(key_env: str) -> str:
    """Return the API key for a model, falling back to multi key."""
    return os.getenv(key_env, "") or os.getenv(_FALLBACK_KEY_ENV, "") or os.getenv("NVIDIA_NIM_API_KEY", "")


async def call_nvidia_nim(
    prompt: str,
    contract: "RoleContract",
    provider: str = "nvidia_nim",
) -> tuple[str, float]:
    """Call a NVIDIA NIM LLM model.

    Args:
        prompt: User prompt text.
        contract: Role contract with token limits.
        provider: Provider name from _MODEL_REGISTRY (default: nvidia_nim).

    Returns:
        (response_text, cost_usd) tuple.

    Raises:
        ValueError if the API key is not configured.
        Exception on API errors (quota, auth, network) so the caller can cascade.
    """
    if is_mock_provider():
        cfg = _MODEL_REGISTRY.get(provider, _MODEL_REGISTRY["nvidia_nim"])
        mock_text = f"[MOCK:nvidia_nim:{cfg['model']}:{contract.role.value}] {prompt[:80]}"
        logger.debug(f"[nvidia_nim] mock mode — {provider}")
        return mock_text, 0.0

    cfg = _MODEL_REGISTRY.get(provider, _MODEL_REGISTRY["nvidia_nim"])
    model_id = cfg["model"]
    cost_per_call = cfg["cost"]

    api_key = _resolve_key(cfg["key_env"])
    if not api_key:
        raise ValueError(f"{cfg['key_env']} not configured (provider: {provider})")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(contract.max_output_tokens, 4096),
        "temperature": 0.7,
        "stream": False,
    }

    logger.debug(f"[nvidia_nim] calling {model_id} for role={contract.role.value}")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(NVIDIA_NIM_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception(f"429 Rate Limited — NVIDIA NIM {model_id}")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized — check {cfg['key_env']}")
    response.raise_for_status()

    data = response.json()
    raw_content = data["choices"][0]["message"].get("content", "")
    # phi-4-multimodal and some vision models return content as a list of objects
    if isinstance(raw_content, list):
        text = " ".join(
            item.get("text", "") for item in raw_content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    else:
        text = raw_content or ""
    logger.debug(f"[nvidia_nim] {model_id}: {len(text)} chars")
    return text, cost_per_call


# Convenience aliases used by _call_single_ai_provider dispatch
async def call_nvidia_nim_default(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim")

async def call_kimi_k2(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="kimi_k2")

async def call_nvidia_nim_405b(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_405b")

async def call_nvidia_nim_mixtral(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_mixtral")

async def call_nvidia_nim_gemma27b(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_gemma27b")

async def call_nvidia_nim_fast(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_fast")

async def call_nvidia_nim_mistral_large(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_mistral_large")

async def call_nvidia_nim_ministral14b(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_ministral14b")

async def call_nvidia_nim_phi4mini(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_phi4mini")

async def call_nvidia_nim_gemma2b(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_gemma2b")

# ── April 2026 additions ──────────────────────────────────────────────────────

async def call_nvidia_nim_glm(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    """ZHIPU AI GLM-4.7 — strong multilingual (Arabic/Chinese/English) reasoning."""
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_glm")

async def call_nvidia_nim_minimax(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    """MiniMax M2.7 — 1M context window, excellent for long legal document generation."""
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_minimax")

async def call_nvidia_nim_phi4(prompt: str, contract: "RoleContract") -> tuple[str, float]:
    """Phi-4 Multimodal Instruct — vision + text + code (uses NVIDIA_NIM_PHI4_API_KEY)."""
    return await call_nvidia_nim(prompt, contract, provider="nvidia_nim_phi4")
