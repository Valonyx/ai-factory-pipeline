"""
AI Factory Pipeline v5.8.13 — Provider Intelligence
Issue 20: Role-specific chains, capability matrix, performance learning,
          rate-limit awareness, and poll-for-upgrades.
Issue 23: resolve_provider_for_role() — key-present + mode-aware chain resolution.
Issue 24: Corrected SCOUT chains (free-only for BASIC; gemini/jina removed).
Issue 33: has_key() + start_health_probes() — real key-presence health checks.

Spec Authority: v5.8.13 §23, §24, §33
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

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
    # NVIDIA NIM — April 2026 additions
    "nvidia_nim_glm":        {Capability.CHAT, Capability.REASONING},                     # ZHIPU AI GLM-4.7 — multilingual (Arabic/Chinese)
    "nvidia_nim_minimax":    {Capability.CHAT, Capability.REASONING},                     # MiniMax M2.7 — 1M context
    "nvidia_nim_phi4":       {Capability.CHAT, Capability.VISION, Capability.CODING},     # Phi-4 Multimodal Instruct
    # Fireworks AI — structured output specialist
    "fireworks":             {Capability.CHAT, Capability.REASONING, Capability.CODING},
    # Retrieval / embedding providers
    "jina":                  {Capability.WEB_TO_TEXT, Capability.EMBEDDINGS, Capability.RERANKING},
    "voyage":                {Capability.EMBEDDINGS, Capability.RERANKING},
    "cohere":                {Capability.CHAT, Capability.EMBEDDINGS, Capability.RERANKING, Capability.CLASSIFICATION},
    "perplexity":            {Capability.CHAT, Capability.SEARCH_GROUNDING},
    "tavily":                {Capability.SEARCH_GROUNDING},
    # Scout / search providers (no AI key — just web access)
    "exa":                   {Capability.SEARCH_GROUNDING, Capability.WEB_TO_TEXT},
    "brave":                 {Capability.SEARCH_GROUNDING},
    "searxng":               {Capability.SEARCH_GROUNDING},
    "duckduckgo":            {Capability.SEARCH_GROUNDING},
    "wikipedia":             {Capability.SEARCH_GROUNDING},
    "hackernews":            {Capability.SEARCH_GROUNDING},
    "reddit":                {Capability.SEARCH_GROUNDING},
    "stackoverflow":         {Capability.SEARCH_GROUNDING},
    "github_search":         {Capability.SEARCH_GROUNDING},
    "ai_scout":              {Capability.SEARCH_GROUNDING, Capability.CHAT},
    # Specialised
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
# ── Context window sizes per provider (input tokens) ─────────────────
# Used to rank providers when prompt is large — prefer largest-window
# provider so context injection never gets truncated.
# Free-tier actual limits (conservative; provider docs may allow more).
PROVIDER_CONTEXT_WINDOWS: dict[str, int] = {
    "gemini":               1_000_000,   # Gemini 2.0 Flash — 1 M context
    "groq":                   128_000,   # Llama-3.3-70b  — 128 K
    "cerebras":               128_000,   # Llama-3.3-70b  — 128 K
    "nvidia_nim":             128_000,   # Llama-3.1-70b  — 128 K
    "nvidia_nim_405b":        128_000,   # Llama-3.1-405B — 128 K
    "kimi_k2":                131_000,   # Kimi K2 — 131 K
    "openrouter":             128_000,   # varies; conservative floor
    "nvidia_nim_mixtral":      64_000,   # Mixtral 8×22B  — 64 K
    "sambanova":               32_000,   # Llama-3.3-70B  — 32 K
    "nvidia_nim_gemma27b":     32_000,   # Gemma-3-27B    — 32 K
    "anthropic":              200_000,   # Claude models  — 200 K
    "github_models":           32_000,
    "cloudflare":               8_000,   # Workers AI — typically 8 K
    "nvidia_nim_fast":          8_000,   # Llama-3.1-8B   — 8 K
    "nvidia_nim_glm":         128_000,   # GLM-4.7   — 128 K
    "nvidia_nim_minimax":   1_000_000,   # MiniMax M2.7 — 1 M context
    "nvidia_nim_phi4":         16_000,   # Phi-4 Multimodal — 16 K
    "fireworks":              131_000,   # Fireworks Llama-3.3-70B — 131 K
    "cohere":                 128_000,   # Command-R+ — 128 K
    "mock":                   200_000,
}

# ── Output token limits per provider ─────────────────────────────────
# Governs how many tokens a provider can generate in a single call.
PROVIDER_OUTPUT_LIMITS: dict[str, int] = {
    "gemini":              8_192,    # Gemini 2.0 Flash free tier
    "groq":               16_384,    # llama-3.3-70b (free tier allows 32 768)
    "cerebras":            8_192,
    "nvidia_nim":          4_096,
    "nvidia_nim_405b":    16_384,
    "nvidia_nim_mixtral": 16_384,
    "kimi_k2":            16_384,
    "openrouter":          8_192,
    "sambanova":           8_192,
    "nvidia_nim_gemma27b": 8_192,
    "anthropic":          16_384,
    "github_models":       4_096,
    "cloudflare":          4_096,
    "nvidia_nim_fast":     4_096,
    "nvidia_nim_glm":      8_192,
    "nvidia_nim_minimax": 16_384,
    "nvidia_nim_phi4":     4_096,
    "fireworks":           8_192,
    "cohere":              4_096,
    "mock":               16_384,
}

ROLE_PROVIDERS: dict[str, dict[str, list[str]]] = {
    "STRATEGIST": {
        # BASIC: free-only.
        # Ordered by: (1) context window desc, (2) output limit desc, (3) quality.
        # gemini=1M ctx, groq=128K/8K out, cerebras=128K, sambanova=32K,
        # nvidia_nim_mixtral=64K/16K out, nvidia_nim=128K/4K out.
        # NOTE: "mock" is NEVER in production chains — it belongs only in unit
        # tests (AI_PROVIDER=mock env var). ModeRouter._filter_available also
        # enforces this at runtime.
        "BASIC":    ["gemini", "groq", "cerebras", "nvidia_nim",
                     "nvidia_nim_mixtral", "nvidia_nim_minimax", "nvidia_nim_glm",
                     "sambanova", "openrouter", "cohere",
                     "nvidia_nim_gemma27b", "cloudflare", "github_models",
                     "nvidia_nim_fast"],
        # BALANCED/CUSTOM/TURBO: paid providers lead; real provider must succeed.
        # When all fail the caller gets [all-providers-exhausted] and the pipeline
        # halts with a meaningful error instead of silently producing garbage content.
        "BALANCED": ["anthropic", "kimi_k2", "gemini", "groq", "cerebras",
                     "fireworks", "nvidia_nim_mixtral", "nvidia_nim_gemma27b",
                     "nvidia_nim", "openrouter"],
        "CUSTOM":   ["anthropic", "kimi_k2", "nvidia_nim_405b", "gemini", "groq",
                     "fireworks", "nvidia_nim_mixtral", "openrouter", "cerebras"],
        "TURBO":    ["anthropic", "kimi_k2", "nvidia_nim_405b", "fireworks",
                     "gemini", "groq"],
    },
    "ENGINEER": {
        # BASIC: highest output tokens first; free-only (no mistral/fireworks).
        "BASIC":    ["gemini", "groq", "cerebras", "nvidia_nim",
                     "nvidia_nim_mixtral", "nvidia_nim_phi4", "sambanova",
                     "openrouter", "nvidia_nim_gemma27b", "cloudflare",
                     "github_models", "nvidia_nim_fast"],
        "BALANCED": ["anthropic", "mistral", "gemini", "groq", "cerebras",
                     "fireworks", "nvidia_nim_mixtral", "nvidia_nim", "openrouter"],
        "CUSTOM":   ["anthropic", "kimi_k2", "mistral", "gemini", "groq",
                     "fireworks", "nvidia_nim_mixtral", "openrouter"],
        "TURBO":    ["anthropic", "kimi_k2", "nvidia_nim_405b", "mistral",
                     "fireworks", "gemini", "groq"],
    },
    "QUICK_FIX": {
        # BASIC: fast models first; context window less critical for short fixes.
        "BASIC":    ["gemini", "groq", "cerebras", "nvidia_nim",
                     "nvidia_nim_gemma27b", "sambanova", "openrouter",
                     "cloudflare", "github_models", "nvidia_nim_fast"],
        "BALANCED": ["anthropic", "gemini", "groq", "nvidia_nim", "openrouter"],
        "CUSTOM":   ["anthropic", "gemini", "groq", "nvidia_nim"],
        "TURBO":    ["anthropic", "gemini", "groq"],
    },
    "SCOUT": {
        # BASIC: free search providers — no perplexity (paid), no brave (paid).
        # exa promoted: most reliable structured grounding.
        "BASIC":    ["exa", "tavily", "searxng", "duckduckgo", "wikipedia",
                     "hackernews", "reddit", "stackoverflow", "github_search", "ai_scout"],
        # BALANCED: perplexity first, then free waterfall
        "BALANCED": ["perplexity", "exa", "tavily", "brave", "searxng",
                     "duckduckgo", "wikipedia", "hackernews", "reddit", "ai_scout"],
        "CUSTOM":   ["perplexity", "exa", "tavily", "brave", "searxng", "ai_scout"],
        "TURBO":    ["perplexity", "brave", "exa", "tavily", "ai_scout"],
    },
}


# ── Issue 33: Required API key env var per provider ───────────────
# None = no key required (always available if the integration is importable).
_KEY_ENV_VARS: dict[str, Optional[str]] = {
    "anthropic":             "ANTHROPIC_API_KEY",
    "gemini":                "GEMINI_API_KEY",
    "groq":                  "GROQ_API_KEY",
    "openrouter":            "OPENROUTER_API_KEY",
    "cerebras":              "CEREBRAS_API_KEY",
    "together":              "TOGETHER_API_KEY",
    "mistral":               "MISTRAL_API_KEY",
    "cloudflare":            "CLOUDFLARE_API_TOKEN",
    "github_models":         "GITHUB_TOKEN",
    "sambanova":             "SAMBANOVA_API_KEY",
    "huggingface":           "HF_TOKEN",
    "nvidia_nim":            "NVIDIA_API_KEY",
    "kimi_k2":               "NVIDIA_API_KEY",
    "nvidia_nim_405b":       "NVIDIA_API_KEY",
    "nvidia_nim_mixtral":    "NVIDIA_API_KEY",
    "nvidia_nim_gemma27b":   "NVIDIA_API_KEY",
    "nvidia_nim_fast":       "NVIDIA_API_KEY",
    "nvidia_nim_vision":     "NVIDIA_API_KEY",
    "nvidia_nim_embeddings": "NVIDIA_API_KEY",
    "nvidia_nim_ocr":        "NVIDIA_API_KEY",
    "nvidia_nim_reranking":  "NVIDIA_API_KEY",
    "nvidia_nim_image_gen":  "NVIDIA_API_KEY",
    # April 2026 additions — dedicated per-model keys
    "nvidia_nim_glm":        "NVIDIA_NIM_GLM_API_KEY",
    "nvidia_nim_minimax":    "NVIDIA_NIM_MINIMAX_API_KEY",
    "nvidia_nim_phi4":       "NVIDIA_NIM_PHI4_API_KEY",
    "fireworks":             "FIREWORKS_API_KEY",
    "perplexity":            "PERPLEXITY_API_KEY",
    "tavily":                "TAVILY_API_KEY",
    "brave":                 "BRAVE_API_KEY",
    "exa":                   "EXA_API_KEY",
    "jina":                  "JINA_API_KEY",
    "voyage":                "VOYAGE_API_KEY",
    "cohere":                "COHERE_API_KEY",
    "ocr_space":             "OCR_SPACE_API_KEY",
    "elevenlabs":            "ELEVENLABS_API_KEY",
    "azure_ai":              "AZURE_AI_KEY",
    "assemblyai":            "ASSEMBLYAI_API_KEY",
    "deepgram":              "DEEPGRAM_API_KEY",
    # Free / keyless providers
    "duckduckgo":            None,
    "wikipedia":             None,
    "hackernews":            None,
    "reddit":                None,
    "stackoverflow":         None,
    "github_search":         None,
    "searxng":               None,
    "ai_scout":              None,
    "mock":                  None,
}


def has_key(provider: str) -> bool:
    """Return True if the provider's required API key is present in the environment.

    Providers with no required key (duckduckgo, wikipedia, etc.) always return True.
    Gemini is special: checks GOOGLE_AI_API_KEY first, then GEMINI_API_KEY.
    """
    if provider == "gemini":
        from factory.integrations.gemini import get_gemini_api_key
        return bool(get_gemini_api_key())
    env_var = _KEY_ENV_VARS.get(provider)
    if env_var is None:
        return True  # keyless provider
    return bool(os.getenv(env_var, "").strip())


# ═══════════════════════════════════════════════════════════════════
# v5.8.15 Issue 54 — hard BASIC-mode paid-provider exclusion.
#
# Live evidence: BASIC mode /providers showed "anthropic: ACTIVE" despite
# the operator having no paid credit. ROLE_PROVIDERS[*][BASIC] already
# excludes paid providers, but the global ai_chain did not know about
# the mode and kept anthropic as "active" from a prior BALANCED run.
# PAID_PROVIDERS is the single source of truth used by both the chain
# filter and the /providers renderer.
# ═══════════════════════════════════════════════════════════════════

PAID_PROVIDERS: frozenset[str] = frozenset({
    "anthropic",
    "perplexity",
    "brave",
    # cohere REMOVED: has a real free trial tier (1,000 req/month), appropriate for BASIC
    "voyage",
    "azure_ai",
    "elevenlabs",
})


def is_paid(provider: str) -> bool:
    """Return True if the provider bills per-request (not free-tier)."""
    return provider in PAID_PROVIDERS


def filter_for_mode(providers: list[str], mode_name: str) -> list[str]:
    """Apply mode-level exclusion rules to a provider list.

    In BASIC mode, paid providers are hard-excluded even if their API
    key is present. In all other modes, the list is returned unchanged.
    """
    if (mode_name or "").upper() == "BASIC":
        return [p for p in providers if not is_paid(p)]
    return list(providers)


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
        self._health_probe_task: Optional[asyncio.Task] = None

    def resolve_provider_for_role(self, role_name: str, state: Any) -> list[str]:
        """Return ordered, available, key-present providers for role + pipeline state.

        Issue 23: extends get_chain_for_role() with:
          - Key-presence filter (skips providers whose env var is unset)
          - Exhausted-provider filter (skips providers in backoff window)
          - Safety: returns full unfiltered chain if all providers are filtered out
        """
        mode_attr = getattr(state, "master_mode", None)
        mode_name = mode_attr.value.upper() if mode_attr is not None else "BALANCED"
        chain = self.get_chain_for_role(role_name, mode_name)
        # v5.8.15 Issue 54 — defensive second pass: even if a paid provider
        # is listed in ROLE_PROVIDERS[role][BASIC] (misconfiguration), the
        # mode filter strips it here.
        chain = filter_for_mode(chain, mode_name)
        result = [
            p for p in chain
            if has_key(p) and self._metrics.get(p, ProviderMetrics(name=p)).is_available()
        ]
        return result if result else chain

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

    def probe_providers(self) -> None:
        """Issue 33: Key-presence health probe — marks keyless paid providers exhausted.

        Called once on startup and periodically by start_health_probes().
        Does NOT make live API calls — checks only whether the env var is set.
        Providers with a key are left in their current state (real latency data wins).
        Providers requiring a key that is absent are marked exhausted (1-year TTL)
        so they never appear as available in resolve_provider_for_role() output.
        """
        for name in list(self._metrics.keys()):
            if not has_key(name):
                m = self._metrics[name]
                if m.exhausted_until is None:
                    m.mark_exhausted(reset_in_seconds=86400 * 365)
                    env_var = _KEY_ENV_VARS.get(name, "?")
                    logger.info(
                        f"[provider-intelligence] {name}: {env_var} absent → marked unavailable"
                    )

    def start_health_probes(self, interval_seconds: int = 300) -> None:
        """Issue 33: Start background task that runs probe_providers() periodically.

        Runs immediately on start, then every interval_seconds (default 5 min).
        This ensures /providers always reflects real key-present status, not
        in-memory defaults (9999ms / 100% success rate) from a fresh restart.
        """
        if self._health_probe_task and not self._health_probe_task.done():
            return

        async def _probe_loop() -> None:
            self.probe_providers()
            while True:
                await asyncio.sleep(interval_seconds)
                self.probe_providers()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._health_probe_task = loop.create_task(_probe_loop())
        except RuntimeError:
            pass  # no running loop at import time — caller must start manually

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

    def status_message(self, mode_name: str = "BALANCED") -> str:
        """Render /providers status for Telegram, scoped to the current mode.

        v5.8.15 Issue 54: mode-aware rendering. In BASIC, paid providers
        are shown as EXCLUDED with a reason ("paid — BASIC free-only")
        so the operator understands why anthropic is not in play.
        """
        mode_upper = (mode_name or "BALANCED").upper()
        lines = [f"📡 *Provider Status* — mode: *{mode_upper}*\n"]
        for role in ROLE_PROVIDERS:
            primary = self.select_provider(role, mode_upper) or "none"
            # Apply mode filter so primary selection obeys BASIC exclusion
            if primary != "none" and is_paid(primary) and mode_upper == "BASIC":
                # recompute with mode filter
                chain = filter_for_mode(
                    self.get_chain_for_role(role, mode_upper),
                    mode_upper,
                )
                primary = next(
                    (p for p in chain
                     if has_key(p)
                     and self._metrics.get(p, ProviderMetrics(name=p)).is_available()),
                    "none",
                )
            lines.append(f"*{role}* → {primary}")
        lines.append("\n*All providers:*")
        for name in PROVIDER_CAPABILITIES:
            m = self._metrics.get(name, ProviderMetrics(name=name))
            key_ok = has_key(name)
            if mode_upper == "BASIC" and is_paid(name):
                lines.append(f"  🚫 {name} — excluded (paid, BASIC free-only)")
            elif not key_ok:
                env_var = _KEY_ENV_VARS.get(name, "?")
                lines.append(f"  🔑 {name} — no {env_var}")
            elif not m.is_available():
                reset_in = max(0, int((m.exhausted_until or 0) - time.time()))
                lines.append(f"  ⏸ {name} — exhausted (reset in {reset_in}s)")
            elif m.success_count > 0:
                lines.append(
                    f"  ✅ {name} — "
                    f"sr={m.success_rate:.0%} lat={m.avg_latency_ms:.0f}ms"
                )
            else:
                lines.append(f"  ✅ {name} — key present, no calls yet")
        return "\n".join(lines)


# Global singleton
provider_intelligence = ProviderIntelligence()
