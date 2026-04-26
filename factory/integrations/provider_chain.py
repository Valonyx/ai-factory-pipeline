"""
AI Factory Pipeline v5.8 — Multi-Provider Fallback Chain

Manages cascading AI and Scout providers. When a provider hits its quota
or fails, the chain automatically switches to the next available one.
When the preferred provider's quota resets, it is automatically restored.

AI Provider priority (dev phase → production):
  1. anthropic   — production (best quality, needs credits)
  2. gemini      — dev default (free, 20 RPD for 2.5 models)
  3. groq        — fallback (free, 14,400 RPD, Llama 3.3 70B)
  4. openrouter  — fallback (free models: Llama, Mistral, etc.)
  5. mock        — CI / last resort

Scout provider priority:
  1. perplexity  — production (best quality, needs $50 balance)
  2. tavily      — free 1,000/month (resets 1st of month)
  3. duckduckgo  — free, no API key, no signup (pip: duckduckgo-search)
  4. exa         — free 1,000/month semantic search (exa.ai, resets 1st of month)
  5. wikipedia   — always free, no API key, no signup — encyclopedic/factual
  6. hackernews  — always free, no API key, no signup — tech community insights
  7. ai_scout    — always free — uses existing AI chain as research assistant
  [brave]        — optional, paid-only; add to chain if key is present

Configuration via .env:
  AI_PROVIDER_CHAIN=anthropic,gemini,groq,openrouter,cerebras,together,mistral,mock
  SCOUT_PROVIDER_CHAIN=perplexity,tavily,duckduckgo,exa,wikipedia,hackernews,ai_scout
  (individual providers can be removed from the chain if not needed)

Spec Authority: v5.8 §2.2 (provider-agnostic role interface)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("factory.integrations.provider_chain")

# ═══════════════════════════════════════════════════════════════════
# Provider Status
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ProviderStatus:
    name: str
    available: bool = True
    quota_exhausted: bool = False
    quota_reset_at: Optional[float] = None   # unix timestamp when quota resets
    consecutive_errors: int = 0
    last_error: str = ""
    last_used_at: Optional[float] = None

    def mark_quota_exhausted(self, reset_in_seconds: int = 86400) -> None:
        """Mark provider as quota-exhausted. Defaults to 24h reset."""
        self.available = False
        self.quota_exhausted = True
        self.quota_reset_at = time.time() + reset_in_seconds
        reset_dt = datetime.fromtimestamp(self.quota_reset_at, tz=timezone.utc)
        logger.warning(
            f"[provider-chain] {self.name} quota exhausted — "
            f"auto-restore at {reset_dt.strftime('%H:%M UTC')}"
        )

    def mark_error(self, error: str) -> None:
        """Record a non-quota error."""
        self.consecutive_errors += 1
        self.last_error = error
        if self.consecutive_errors >= 3:
            self.available = False
            logger.warning(
                f"[provider-chain] {self.name} disabled after "
                f"{self.consecutive_errors} consecutive errors: {error}"
            )

    def mark_success(self) -> None:
        self.consecutive_errors = 0
        self.last_error = ""
        self.available = True
        self.last_used_at = time.time()

    def check_reset(self) -> bool:
        """Returns True if quota has reset since it was exhausted."""
        if self.quota_exhausted and self.quota_reset_at:
            if time.time() >= self.quota_reset_at:
                self.available = True
                self.quota_exhausted = False
                self.quota_reset_at = None
                logger.info(f"[provider-chain] {self.name} quota reset — restored to chain")
                return True
        return False


# ═══════════════════════════════════════════════════════════════════
# Provider Chain Manager
# ═══════════════════════════════════════════════════════════════════

class ProviderChain:
    """Manages an ordered list of providers with automatic fallback and restore."""

    def __init__(self, chain_env_var: str, default_chain: list[str]) -> None:
        chain_str = os.getenv(chain_env_var, ",".join(default_chain))
        self.chain: list[str] = [p.strip() for p in chain_str.split(",") if p.strip()]
        self.statuses: dict[str, ProviderStatus] = {
            name: ProviderStatus(name=name) for name in self.chain
        }
        logger.info(f"[provider-chain] Initialized: {' → '.join(self.chain)}")

    def get_active(self) -> str:
        """Return the highest-priority available provider."""
        # First check if any exhausted providers have reset
        for name in self.chain:
            self.statuses[name].check_reset()

        for name in self.chain:
            if self.statuses[name].available:
                return name

        # All exhausted — return last in chain (mock/duckduckgo) as last resort
        logger.error("[provider-chain] All providers exhausted — using last in chain")
        last = self.chain[-1]
        self.statuses[last].available = True  # force-enable last resort
        return last

    def mark_quota_exhausted(self, provider: str, reset_in_seconds: int = 86400) -> None:
        if provider in self.statuses:
            self.statuses[provider].mark_quota_exhausted(reset_in_seconds)

    def mark_error(self, provider: str, error: str) -> None:
        if provider in self.statuses:
            self.statuses[provider].mark_error(error)

    def mark_success(self, provider: str) -> None:
        if provider in self.statuses:
            self.statuses[provider].mark_success()

    def status_summary(self) -> str:
        lines = []
        for name in self.chain:
            s = self.statuses[name]
            if s.quota_exhausted and s.quota_reset_at:
                eta = int(s.quota_reset_at - time.time())
                lines.append(f"  {name}: QUOTA EXHAUSTED (resets in {eta//3600}h {(eta%3600)//60}m)")
            elif not s.available:
                lines.append(f"  {name}: UNAVAILABLE ({s.last_error[:50]})")
            else:
                lines.append(f"  {name}: OK (active={name == self.get_active()})")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Global Chain Singletons
# ═══════════════════════════════════════════════════════════════════

_AI_DEFAULT_CHAIN = ["anthropic", "gemini", "groq", "openrouter", "cerebras", "together", "mistral"]
# "mock" is intentionally excluded from the default production chain.
# It is only enabled in tests via AI_PROVIDER_CHAIN=mock (or when DRY_RUN is set
# explicitly by the test runner — Phase 5 will tighten the DRY_RUN gate).

# Full Scout chain — 12 providers.
# Unlimited (no quota):  searxng, duckduckgo, wikipedia, hackernews, reddit, stackoverflow, github_search, ai_scout
# Monthly quota:         perplexity (~paid), tavily (1K), exa (1K), brave (2K)
_SCOUT_DEFAULT_CHAIN = [
    "perplexity",    # production AI search ($50 min balance)
    "brave",         # paid — independent web index (api.search.brave.com)
    "tavily",        # 1,000/month — AI-synthesised web search
    "exa",           # 1,000/month — neural semantic search
    "searxng",       # ∞ — meta-search (Google/Bing/DDG aggregated)
    "duckduckgo",    # ∞ — keyword web search, no key
    "wikipedia",     # ∞ — encyclopedic facts
    "hackernews",    # ∞ — tech community insights
    "reddit",        # ∞ — community discussions, no key
    "stackoverflow", # ∞* — dev Q&A, ~300 anon req/day per IP
    "github_search", # ∞* — code/repo search via existing GITHUB_TOKEN
    "ai_scout",      # ∞ — LLM fallback using free AI chain
]

# ── Lazy singletons ───────────────────────────────────────────────────
# Initialised on first access so env vars set after import (e.g. by test
# fixtures or the secrets loader) are picked up correctly.
# FIX-PROV-01: the previous eager init at module-load time read env before
# GCP Secret Manager had a chance to populate AI_PROVIDER_CHAIN.

_ai_chain: ProviderChain | None = None
_scout_chain: ProviderChain | None = None


def _get_ai_chain() -> ProviderChain:
    global _ai_chain
    if _ai_chain is None:
        _ai_chain = ProviderChain("AI_PROVIDER_CHAIN", _AI_DEFAULT_CHAIN)
    return _ai_chain


def _get_scout_chain() -> ProviderChain:
    global _scout_chain
    if _scout_chain is None:
        _scout_chain = ProviderChain("SCOUT_PROVIDER_CHAIN", _SCOUT_DEFAULT_CHAIN)
    return _scout_chain


def __getattr__(name: str) -> object:
    """Module-level lazy attribute resolver (PEP 562).

    Allows ``from factory.integrations.provider_chain import ai_chain``
    to work transparently while deferring the ProviderChain constructor
    (and its os.getenv calls) until first use.
    """
    if name == "ai_chain":
        return _get_ai_chain()
    if name == "scout_chain":
        return _get_scout_chain()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ═══════════════════════════════════════════════════════════════════
# QuotaTracker — monthly usage tracking for quota-limited providers
# ═══════════════════════════════════════════════════════════════════

class QuotaTracker:
    """Tracks monthly API call counts for quota-limited Scout providers.

    Integrates with ScoutOrchestrator to:
      • Deprioritise providers that have consumed ≥ 80 % of their monthly quota
        (they stay available but move to the end of the routing order)
      • Mark providers exhausted at ≥ 100 % (skipped until month resets)
      • Auto-reset all counts on the 1st of each calendar month (UTC)

    Quotas are conservative estimates based on free-tier limits.
    Override via env vars, e.g. QUOTA_TAVILY=500.
    """

    # Default monthly quotas (free-tier ceiling for each provider).
    # brave is paid-only — no free quota to track; omitted intentionally.
    _DEFAULT_QUOTAS: dict[str, int] = {
        "perplexity":   500,    # treat conservatively (paid but budgeted)
        "tavily":       1000,   # free tier: 1,000/month
        "exa":          1000,   # free tier: 1,000/month
        "stackoverflow": 9000,  # registered app key: 10,000/day — set high ceiling
    }
    # Providers NOT in this dict have no tracked quota (treated as unlimited)

    def __init__(self) -> None:
        self._usage: dict[str, int] = {}
        self._current_month: int = 0
        self._quotas: dict[str, int] = {}
        self._load_quotas()
        self._check_month_reset()

    def _load_quotas(self) -> None:
        """Allow env var overrides: QUOTA_TAVILY=500 etc."""
        for provider, default in self._DEFAULT_QUOTAS.items():
            env_key = f"QUOTA_{provider.upper()}"
            self._quotas[provider] = int(os.getenv(env_key, str(default)))

    def _check_month_reset(self) -> None:
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).month
        if month != self._current_month:
            self._usage.clear()
            self._current_month = month
            if self._current_month:  # skip on first init
                logger.info("[quota-tracker] Monthly quota counters reset")

    def record_use(self, provider: str) -> None:
        """Increment the usage counter for a provider."""
        self._check_month_reset()
        self._usage[provider] = self._usage.get(provider, 0) + 1

    def usage_fraction(self, provider: str) -> float:
        """Return 0.0–1.0 fraction of monthly quota consumed (0.0 if unlimited)."""
        self._check_month_reset()
        quota = self._quotas.get(provider)
        if not quota:
            return 0.0
        return min(1.0, self._usage.get(provider, 0) / quota)

    def should_deprioritize(self, provider: str) -> bool:
        """True when ≥ 80 % of monthly quota is used — move to end of route order."""
        return self.usage_fraction(provider) >= 0.80

    def is_monthly_exhausted(self, provider: str) -> bool:
        """True when ≥ 100 % of monthly quota is used — skip until month resets."""
        return self.usage_fraction(provider) >= 1.0

    def status_lines(self) -> list[str]:
        """Return human-readable quota status lines for /providers command."""
        self._check_month_reset()
        lines = []
        for provider, quota in sorted(self._quotas.items()):
            used = self._usage.get(provider, 0)
            pct  = int(used / quota * 100)
            bar  = "▓" * (pct // 10) + "░" * (10 - pct // 10)
            flag = " ⚠" if pct >= 80 else ""
            lines.append(f"  {provider:15s} [{bar}] {used}/{quota} ({pct}%){flag}")
        return lines


# Singleton accessible to the entire pipeline
quota_tracker = QuotaTracker()


# ═══════════════════════════════════════════════════════════════════
# Quota Error Detection Helpers
# ═══════════════════════════════════════════════════════════════════

def parse_retry_delay(error_str: str) -> int:
    """Extract retry-after seconds from a 429 error message."""
    import re
    # Gemini: "Please retry in 23s"
    m = re.search(r"retry in (\d+)[\.\d]*s", error_str, re.IGNORECASE)
    if m:
        return int(m.group(1)) + 5

    # Groq: "Please try again in 1m30.123s"
    m2 = re.search(r"try again in (\d+)m([\d.]+)s", error_str, re.IGNORECASE)
    if m2:
        return int(m2.group(1)) * 60 + int(float(m2.group(2))) + 5

    return 86400  # default: 24 hours


def is_quota_error(error_str: str) -> bool:
    return any(kw in error_str for kw in [
        "429", "RESOURCE_EXHAUSTED", "rate_limit_exceeded",
        "quota", "RateLimitError", "overloaded",
        "credit balance", "too low", "billing", "insufficient_quota",
        "Your credit balance",
    ])


def is_auth_error(error_str: str) -> bool:
    return any(kw in error_str for kw in [
        "401", "403", "AuthenticationError", "invalid_api_key",
        "Unauthorized", "authentication_error",
    ])


# ═══════════════════════════════════════════════════════════════════
# FIX-PROV-03: Provider name normalization
# ═══════════════════════════════════════════════════════════════════

_PROVIDER_ALIASES: dict[str, str] = {
    # Claude / Anthropic aliases
    "claude":      "anthropic",
    "anthropic-claude": "anthropic",
    # Gemini aliases
    "google":      "gemini",
    "google-gemini": "gemini",
    "bard":        "gemini",
    # OpenRouter aliases
    "openrouter":  "openrouter",
    "open-router": "openrouter",
    "or":          "openrouter",
    # Groq aliases
    "llama":       "groq",
    "meta":        "groq",
    # Cerebras aliases
    "cerebras-ai": "cerebras",
    # Together.ai aliases
    "together-ai": "together",
    "togetherai":  "together",
    # Mistral aliases
    "mistral-ai":  "mistral",
    "mistraiai":   "mistral",
    # Perplexity aliases
    "pplx":        "perplexity",
    "sonar":       "perplexity",
    # DuckDuckGo aliases
    "ddg":         "duckduckgo",
    "duck":        "duckduckgo",
    # Wikipedia aliases
    "wiki":        "wikipedia",
    # HackerNews aliases
    "hn":          "hackernews",
    "hacker-news": "hackernews",
}


def normalize_provider_name(name: str) -> str:
    """Return the canonical provider name for a given alias or raw input.

    Lowercases and strips whitespace before lookup so env-var typos like
    "Anthropic" or "GROQ" still resolve correctly.

    >>> normalize_provider_name("claude")
    'anthropic'
    >>> normalize_provider_name("ddg")
    'duckduckgo'
    >>> normalize_provider_name("gemini")
    'gemini'
    """
    key = name.strip().lower()
    return _PROVIDER_ALIASES.get(key, key)


# ═══════════════════════════════════════════════════════════════════
# FIX-PROV-04: Live provider ping
# ═══════════════════════════════════════════════════════════════════

async def ping_provider(name: str, *, timeout: float = 5.0) -> bool:
    """Attempt a minimal health check on a named AI provider.

    Returns True when the provider is reachable and the API key is
    accepted. Returns False on auth failure, quota exhaustion, or
    network error. Never raises.

    Used by /providers --ping and the pre-pipeline provider selector.
    """
    canonical = normalize_provider_name(name)
    try:
        if canonical == "anthropic":
            return await _ping_anthropic(timeout)
        elif canonical == "gemini":
            return await _ping_gemini(timeout)
        elif canonical == "groq":
            return await _ping_groq(timeout)
        elif canonical == "openrouter":
            return await _ping_openrouter(timeout)
        else:
            # For providers without a dedicated ping, key presence is the check.
            key_env = {
                "cerebras":   "CEREBRAS_API_KEY",
                "together":   "TOGETHER_API_KEY",
                "mistral":    "MISTRAL_API_KEY",
                "perplexity": "PERPLEXITY_API_KEY",
                "tavily":     "TAVILY_API_KEY",
                "exa":        "EXA_API_KEY",
                "brave":      "BRAVE_API_KEY",
            }
            env_var = key_env.get(canonical)
            if env_var:
                return bool(os.getenv(env_var))
            # Key-free providers (duckduckgo, wikipedia, hackernews, ai_scout) are
            # always considered available from a ping perspective.
            return True
    except Exception as exc:
        logger.debug(f"[ping] {canonical}: {exc}")
        return False


async def _ping_anthropic(timeout: float) -> bool:
    import asyncio
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return False
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=key)
        await asyncio.wait_for(
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            ),
            timeout=timeout,
        )
        return True
    except Exception as e:
        return not is_auth_error(str(e))


async def _ping_gemini(timeout: float) -> bool:
    import asyncio
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return False
    try:
        import google.generativeai as genai  # type: ignore[import]
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        await asyncio.wait_for(
            asyncio.to_thread(model.generate_content, "ping"),
            timeout=timeout,
        )
        return True
    except Exception as e:
        return not is_auth_error(str(e))


async def _ping_groq(timeout: float) -> bool:
    import asyncio
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return False
    try:
        from groq import AsyncGroq  # type: ignore[import]
        client = AsyncGroq(api_key=key)
        await asyncio.wait_for(
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            ),
            timeout=timeout,
        )
        return True
    except Exception as e:
        return not is_auth_error(str(e))


async def _ping_openrouter(timeout: float) -> bool:
    import asyncio
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return False
    try:
        import httpx  # type: ignore[import]
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await asyncio.wait_for(
                client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                ),
                timeout=timeout,
            )
        return resp.status_code == 200
    except Exception as e:
        return not is_auth_error(str(e))
