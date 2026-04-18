"""
AI Factory Pipeline v5.8.12 — Provider Intelligence
Issue 20: Role-specific chains, capability matrix, performance learning,
          rate-limit awareness, and poll-for-upgrades.

Spec Authority: v5.8.12 §20
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("factory.core.provider_intelligence")


# ── Capability tags ───────────────────────────────────────────────
class Capability(str, Enum):
    CHAT            = "chat"
    REASONING       = "reasoning"
    CODING          = "coding"
    VISION          = "vision"
    EMBEDDINGS      = "embeddings"
    RERANKING       = "reranking"
    IMAGE_GEN       = "image_gen"
    STT             = "stt"          # speech-to-text
    TTS             = "tts"          # text-to-speech
    OCR             = "ocr"
    SEARCH_GROUNDING = "search_grounding"
    WEB_TO_TEXT     = "web_to_text"
    MODERATION      = "moderation"
    CLASSIFICATION  = "classification"


# ── Capability matrix — what each provider supports ───────────────
PROVIDER_CAPABILITIES: dict[str, set[Capability]] = {
    # Core LLM providers
    "anthropic":             {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.VISION, Capability.MODERATION},
    "gemini":                {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.VISION, Capability.EMBEDDINGS, Capability.SEARCH_GROUNDING, Capability.IMAGE_GEN},
    "groq":                  {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.VISION, Capability.STT, Capability.TTS, Capability.MODERATION},
    "openrouter":            {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.VISION},
    "cerebras":              {Capability.CHAT, Capability.REASONING, Capability.CODING},
    "together":              {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.IMAGE_GEN},
    "mistral":               {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.OCR},
    "cloudflare":            {Capability.CHAT, Capability.CODING, Capability.EMBEDDINGS, Capability.IMAGE_GEN, Capability.VISION, Capability.CLASSIFICATION},
    "github_models":         {Capability.CHAT, Capability.REASONING, Capability.CODING},
    "sambanova":             {Capability.CHAT, Capability.REASONING, Capability.CODING},
    "huggingface":           {Capability.CHAT, Capability.CODING, Capability.EMBEDDINGS, Capability.IMAGE_GEN},
    # NVIDIA NIM LLM providers
    "nvidia_nim":            {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.MODERATION},
    "kimi_k2":               {Capability.CHAT, Capability.REASONING, Capability.CODING},  # moonshotai/kimi-k2.5 — best for reasoning
    "nvidia_nim_405b":       {Capability.CHAT, Capability.REASONING, Capability.CODING},  # llama-405b — ultra scale
    "nvidia_nim_mixtral":    {Capability.CHAT, Capability.REASONING, Capability.CODING},  # mixtral-8x22b
    "nvidia_nim_gemma27b":   {Capability.CHAT, Capability.CODING},                        # gemma-3-27b
    "nvidia_nim_fast":       {Capability.CHAT, Capability.CODING},                        # llama-3.1-8b — fast/bulk
    # NVIDIA NIM specialized providers
    "nvidia_nim_vision":     {Capability.VISION, Capability.CHAT},                        # nemotron-vl, llama-90b-vision, phi-4-multimodal
    "nvidia_nim_embeddings": {Capability.EMBEDDINGS},                                     # bge-m3, nv-embedqa-e5, nv-embed-v1, etc.
    "nvidia_nim_ocr":        {Capability.OCR},                                            # nemotron-ocr-v1, nemoretriever-ocr-v1
    "nvidia_nim_reranking":  {Capability.RERANKING},                                      # nv-rerank-qa-mistral-4b, llama-nemotron-rerank-1b
    "nvidia_nim_image_gen":  {Capability.IMAGE_GEN},                                      # FLUX models
    # Retrieval / embedding providers
    "jina":                  {Capability.WEB_TO_TEXT, Capability.EMBEDDINGS, Capability.RERANKING},
    "voyage":                {Capability.EMBEDDINGS, Capability.RERANKING},
    "cohere":                {Capability.CHAT, Capability.EMBEDDINGS, Capability.RERANKING, Capability.CLASSIFICATION},
    "perplexity":            {Capability.CHAT, Capability.SEARCH_GROUNDING},
    "tavily":                {Capability.SEARCH_GROUNDING},
    "ocr_space":             {Capability.OCR},
    "elevenlabs":            {Capability.TTS, Capability.STT},
    "azure_ai":              {Capability.STT, Capability.TTS, Capability.VISION, Capability.OCR, Capability.CHAT},
    "assemblyai":            {Capability.STT},
    "deepgram":              {Capability.STT, Capability.TTS},
    "mock":                  {Capability.CHAT, Capability.REASONING, Capability.CODING, Capability.VISION, Capability.EMBEDDINGS},
}

# ── Role → required capability ─────────────────────────────────────
ROLE_REQUIRED_CAPABILITY: dict[str, Capability] = {
    "STRATEGIST":  Capability.REASONING,
    "ENGINEER":    Capability.CODING,
    "QUICK_FIX":   Capability.CHAT,
    "SCOUT":       Capability.SEARCH_GROUNDING,
}

# ── Role → preferred provider chains per mode ──────────────────────
# Keys match MasterMode.value strings.
# New NIM providers (kimi_k2, nvidia_nim_405b, nvidia_nim_mixtral, nvidia_nim_gemma27b)
# are positioned by quality tier within each mode's cascade.
ROLE_PROVIDERS: dict[str, dict[str, list[str]]] = {
    "STRATEGIST": {
        # BASIC: free-only, best free quality first
        "BASIC":    ["gemini", "groq", "nvidia_nim_mixtral", "nvidia_nim_gemma27b", "nvidia_nim",
                     "openrouter", "cerebras", "cloudflare", "github_models", "sambanova",
                     "nvidia_nim_fast", "mock"],
        # BALANCED: anthropic for critical, cascade through quality tiers
        "BALANCED": ["anthropic", "kimi_k2", "gemini", "groq", "nvidia_nim_mixtral",
                     "nvidia_nim_gemma27b", "nvidia_nim", "openrouter", "cerebras", "mock"],
        # CUSTOM: operator selects, reasonable default ordering
        "CUSTOM":   ["anthropic", "kimi_k2", "nvidia_nim_405b", "gemini", "groq",
                     "nvidia_nim_mixtral", "openrouter", "cerebras", "mock"],
        # TURBO: max quality first
        "TURBO":    ["anthropic", "kimi_k2", "nvidia_nim_405b", "gemini", "groq", "mock"],
    },
    "ENGINEER": {
        "BASIC":    ["gemini", "groq", "nvidia_nim_mixtral", "nvidia_nim_gemma27b", "nvidia_nim",
                     "openrouter", "cerebras", "cloudflare", "github_models", "nvidia_nim_fast", "mock"],
        "BALANCED": ["anthropic", "gemini", "groq", "nvidia_nim_mixtral", "nvidia_nim",
                     "openrouter", "cerebras", "mock"],
        "CUSTOM":   ["anthropic", "kimi_k2", "gemini", "groq", "nvidia_nim_mixtral",
                     "openrouter", "mock"],
        "TURBO":    ["anthropic", "kimi_k2", "nvidia_nim_405b", "gemini", "groq", "mock"],
    },
    "QUICK_FIX": {
        "BASIC":    ["gemini", "groq", "nvidia_nim_gemma27b", "nvidia_nim", "openrouter",
                     "cerebras", "cloudflare", "github_models", "nvidia_nim_fast", "mock"],
        "BALANCED": ["anthropic", "gemini", "groq", "nvidia_nim", "openrouter", "mock"],
        "CUSTOM":   ["anthropic", "gemini", "groq", "nvidia_nim", "mock"],
        "TURBO":    ["anthropic", "gemini", "groq", "mock"],
    },
    "SCOUT": {
        "BASIC":    ["gemini", "tavily", "jina", "perplexity", "mock"],
        "BALANCED": ["perplexity", "gemini", "tavily", "jina", "mock"],
        "CUSTOM":   ["perplexity", "gemini", "tavily", "mock"],
        "TURBO":    ["perplexity", "gemini", "mock"],
    },
}


@dataclass
class RateLimitInfo:
    """Rate-limit info parsed from response headers or API metadata."""
    requests_remaining: Optional[int] = None
    tokens_remaining: Optional[int] = None
    reset_at: Optional[float] = None  # unix timestamp


@dataclass
class ProviderMetrics:
    """Observed performance metrics for a provider."""
    name: str
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_rate_limit: Optional[RateLimitInfo] = None
    exhausted_until: Optional[float] = None  # unix timestamp

    @property
    def avg_latency_ms(self) -> float:
        if self.success_count == 0:
            return 9999.0
        return self.total_latency_ms / self.success_count

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0

    def record_success(self, latency_ms: float) -> None:
        self.success_count += 1
        self.total_latency_ms += latency_ms

    def record_failure(self) -> None:
        self.failure_count += 1

    def is_available(self) -> bool:
        if self.exhausted_until and time.time() < self.exhausted_until:
            return False
        return True

    def mark_exhausted(self, reset_in_seconds: int = 86400) -> None:
        self.exhausted_until = time.time() + reset_in_seconds
        logger.warning(f"[provider-intelligence] {self.name} marked exhausted for {reset_in_seconds}s")


class ProviderIntelligence:
    """
    Role-aware provider coordinator sitting above ModeRouter.

    Adds on top of ModeRouter:
    - Role-specific provider chains (ROLE_PROVIDERS)
    - Capability matrix enforcement
    - Per-provider performance metrics + learning
    - Rate-limit awareness (pre-switch 10% before hard-limit)
    - poll_for_upgrades background task
    - /providers status rendering
    """

    def __init__(self) -> None:
        self._metrics: dict[str, ProviderMetrics] = {
            name: ProviderMetrics(name=name)
            for name in PROVIDER_CAPABILITIES
        }
        self._upgrade_poller_task: Optional[asyncio.Task] = None

    def get_chain_for_role(self, role_name: str, mode: str) -> list[str]:
        """Return the ordered provider list for a role+mode, filtered by capability."""
        role_upper = role_name.upper()
        mode_upper = mode.upper()
        chain = ROLE_PROVIDERS.get(role_upper, {}).get(mode_upper, ["mock"])
        required_cap = ROLE_REQUIRED_CAPABILITY.get(role_upper)
        if required_cap is None:
            return chain
        # Filter out providers that don't support the required capability
        return [p for p in chain if required_cap in PROVIDER_CAPABILITIES.get(p, set())]

    def select_provider(self, role_name: str, mode: str) -> Optional[str]:
        """Return the best available provider for role+mode."""
        for name in self.get_chain_for_role(role_name, mode):
            m = self._metrics.get(name)
            if m and not m.is_available():
                continue
            return name
        return None

    def record_call(self, provider: str, latency_ms: float, success: bool,
                    rate_limit: Optional[RateLimitInfo] = None) -> None:
        m = self._metrics.setdefault(provider, ProviderMetrics(name=provider))
        if success:
            m.record_success(latency_ms)
        else:
            m.record_failure()
        if rate_limit:
            m.last_rate_limit = rate_limit
            # Pre-switch: if <10% requests remaining, mark exhausted proactively
            if (rate_limit.requests_remaining is not None
                    and rate_limit.reset_at is not None
                    and rate_limit.requests_remaining < 10):
                reset_in = max(0, int(rate_limit.reset_at - time.time()))
                m.mark_exhausted(reset_in or 3600)

    def on_provider_exhausted(self, provider: str, reset_in_seconds: int = 86400) -> None:
        m = self._metrics.setdefault(provider, ProviderMetrics(name=provider))
        m.mark_exhausted(reset_in_seconds)

    def start_upgrade_poller(self, interval_seconds: int = 60) -> None:
        """Start background task that checks for exhausted-provider recovery."""
        if self._upgrade_poller_task and not self._upgrade_poller_task.done():
            return
        async def _poll():
            while True:
                await asyncio.sleep(interval_seconds)
                now = time.time()
                for m in self._metrics.values():
                    if m.exhausted_until and now >= m.exhausted_until:
                        m.exhausted_until = None
                        logger.info(f"[provider-intelligence] {m.name} restored to available")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._upgrade_poller_task = loop.create_task(_poll())
        except RuntimeError:
            pass  # no running loop at import time — caller must start manually

    def status_message(self) -> str:
        """Render /providers status for Telegram."""
        lines = ["📡 *Provider Status*\n"]
        for role, modes in ROLE_PROVIDERS.items():
            primary = self.select_provider(role, "BALANCED") or "none"
            lines.append(f"*{role}* → {primary}")
        lines.append("\n*All providers:*")
        for name, caps in PROVIDER_CAPABILITIES.items():
            m = self._metrics.get(name, ProviderMetrics(name=name))
            status = "✅" if m.is_available() else f"⏸ (reset {int(m.exhausted_until or 0) - int(time.time())}s)"
            lines.append(
                f"  {status} {name} — "
                f"sr={m.success_rate:.0%} lat={m.avg_latency_ms:.0f}ms"
            )
        return "\n".join(lines)


# Global singleton
provider_intelligence = ProviderIntelligence()
