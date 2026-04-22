"""
AI Factory Pipeline v5.8 — Quota Tracker (Supabase-persisted)

Tracks per-provider usage, rate limits, and reset times across all chains
(AI, Scout, Image). Persists to Supabase so quota state survives process
restarts and is shared across workers.

Interface consumed by ModeRouter:
  - is_available(provider) -> bool
  - record_usage(provider, tokens=0, calls=1, cost_usd=0.0)
  - mark_exhausted(provider)
  - next_reset(provider) -> Optional[datetime]
  - soonest_reset() -> Optional[datetime]
  - poll_resets() -> list[str]   # providers that reset since last poll

Spec Authority: v5.8 §Phase 1.5
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("factory.core.quota_tracker")


# ═══════════════════════════════════════════════════════════════════
# Default quota ceilings (free-tier / conservative monthly limits)
# ═══════════════════════════════════════════════════════════════════

_DEFAULT_MONTHLY_QUOTAS: dict[str, dict] = {
    # AI providers
    "gemini":      {"calls": 1500,  "tokens": 1_000_000},
    "groq":        {"calls": 14400, "tokens": 500_000},
    "openrouter":  {"calls": 1000,  "tokens": 200_000},
    "cerebras":    {"calls": 1000,  "tokens": 200_000},
    # Scout providers
    "tavily":      {"calls": 1000,  "tokens": 0},
    "exa":         {"calls": 1000,  "tokens": 0},
    "perplexity":  {"calls": 500,   "tokens": 0},
    "stackoverflow": {"calls": 9000, "tokens": 0},
    "brave":       {"calls": 2000,  "tokens": 0},
    # Image providers
    "pollinations": {"calls": 5000, "tokens": 0},
    "huggingface":  {"calls": 1000, "tokens": 0},
}


def _month_key(dt: Optional[datetime] = None) -> str:
    """Return 'YYYY-MM' for the given datetime (UTC now if None)."""
    d = dt or datetime.now(timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def _next_month_reset(from_dt: Optional[datetime] = None) -> datetime:
    """Return UTC midnight on the 1st of the next calendar month."""
    d = from_dt or datetime.now(timezone.utc)
    if d.month == 12:
        return datetime(d.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(d.year, d.month + 1, 1, tzinfo=timezone.utc)


# ═══════════════════════════════════════════════════════════════════
# In-memory provider state record
# ═══════════════════════════════════════════════════════════════════

class _ProviderState:
    __slots__ = (
        "calls", "tokens", "cost_usd",
        "is_exhausted", "exhausted_at",
        "month_key", "next_reset_at",
        "quota_calls", "quota_tokens",
    )

    def __init__(
        self,
        quota_calls: int = 0,
        quota_tokens: int = 0,
    ) -> None:
        self.calls: int = 0
        self.tokens: int = 0
        self.cost_usd: float = 0.0
        self.is_exhausted: bool = False
        self.exhausted_at: Optional[datetime] = None
        self.month_key: str = _month_key()
        self.next_reset_at: datetime = _next_month_reset()
        self.quota_calls: int = quota_calls
        self.quota_tokens: int = quota_tokens

    def reset(self) -> None:
        self.calls = 0
        self.tokens = 0
        self.cost_usd = 0.0
        self.is_exhausted = False
        self.exhausted_at = None
        self.month_key = _month_key()
        self.next_reset_at = _next_month_reset()

    def check_month_rollover(self) -> bool:
        """Return True (and reset) if the current month has changed."""
        current = _month_key()
        if current != self.month_key:
            self.reset()
            return True
        return False

    def usage_fraction_calls(self) -> float:
        if not self.quota_calls:
            return 0.0
        return min(1.0, self.calls / self.quota_calls)

    def usage_fraction_tokens(self) -> float:
        if not self.quota_tokens:
            return 0.0
        return min(1.0, self.tokens / self.quota_tokens)

    def at_capacity(self) -> bool:
        """True when either calls or tokens quota is ≥100%."""
        return (
            self.is_exhausted
            or self.usage_fraction_calls() >= 1.0
            or (self.quota_tokens > 0 and self.usage_fraction_tokens() >= 1.0)
        )


# ═══════════════════════════════════════════════════════════════════
# QuotaTracker
# ═══════════════════════════════════════════════════════════════════

class QuotaTracker:
    """Tracks per-provider usage with Supabase persistence.

    Spec: v5.8 §Phase 1.5

    Usage:
        tracker = QuotaTracker()
        await tracker.load_from_supabase()
        if tracker.is_available("gemini"):
            # use gemini
            await tracker.record_usage("gemini", tokens=1000)
    """

    def __init__(self, supabase_client=None) -> None:
        self._states: dict[str, _ProviderState] = {}
        self._supabase = supabase_client
        self._last_poll: datetime = datetime.now(timezone.utc)
        self._load_quotas_from_env()

    # ── Quota config ────────────────────────────────────────────────

    def _load_quotas_from_env(self) -> None:
        """Load default quotas, allowing env-var overrides (QUOTA_GEMINI_CALLS=2000)."""
        for provider, defaults in _DEFAULT_MONTHLY_QUOTAS.items():
            qc_key = f"QUOTA_{provider.upper()}_CALLS"
            qt_key = f"QUOTA_{provider.upper()}_TOKENS"
            qc = int(os.getenv(qc_key, str(defaults.get("calls", 0))))
            qt = int(os.getenv(qt_key, str(defaults.get("tokens", 0))))
            self._states[provider] = _ProviderState(quota_calls=qc, quota_tokens=qt)

    def _get_state(self, provider: str) -> _ProviderState:
        if provider not in self._states:
            self._states[provider] = _ProviderState()
        return self._states[provider]

    # ── Public API (sync) ────────────────────────────────────────────

    def is_available(self, provider: str) -> bool:
        """True if the provider has not hit its quota this month."""
        s = self._get_state(provider)
        s.check_month_rollover()
        return not s.at_capacity()

    def mark_exhausted(self, provider: str) -> None:
        """Immediately flag provider as exhausted (called by ModeRouter)."""
        s = self._get_state(provider)
        s.is_exhausted = True
        s.exhausted_at = datetime.now(timezone.utc)
        logger.info(f"[QuotaTracker] {provider} marked exhausted")

    def next_reset(self, provider: str) -> Optional[datetime]:
        """Return when this provider's quota will reset (start of next month)."""
        s = self._get_state(provider)
        return s.next_reset_at

    def soonest_reset(self) -> Optional[datetime]:
        """Return the soonest upcoming reset across all exhausted providers."""
        exhausted_resets = [
            self._get_state(p).next_reset_at
            for p in self._states
            if self._get_state(p).at_capacity()
        ]
        return min(exhausted_resets) if exhausted_resets else None

    def poll_resets(self) -> list[str]:
        """Return list of provider names whose quota just reset since last poll.

        Call this periodically (e.g. from ModeRouter's upgrade_poller).
        Checks month rollover — if a provider's month rolled, it's been reset.
        """
        now = datetime.now(timezone.utc)
        reset_providers: list[str] = []
        for provider, state in self._states.items():
            if state.at_capacity() and state.check_month_rollover():
                reset_providers.append(provider)
                logger.info(f"[QuotaTracker] {provider} quota reset (month rollover)")
        self._last_poll = now
        return reset_providers

    def usage_summary(self) -> list[str]:
        """Return human-readable quota status lines for /quota command."""
        lines = []
        for provider in sorted(self._states):
            s = self._states[provider]
            s.check_month_rollover()
            call_pct = int(s.usage_fraction_calls() * 100)
            # v5.8.15 Issue 53 — iOS renders U+2593 (▓) as a tofu box in
            # Telegram's monospace font. Use U+2588 (█) which renders
            # consistently across iOS / Android / Web, matching /cost.
            bar = "█" * (call_pct // 10) + "░" * (10 - call_pct // 10)
            status = " ⛔" if s.at_capacity() else (" ⚠" if call_pct >= 80 else "")
            lines.append(
                f"  {provider:15s} [{bar}] {s.calls}/{s.quota_calls or '∞'}"
                f" calls  ${s.cost_usd:.4f}{status}"
            )
        return lines

    # ── Async: record usage + persist ───────────────────────────────

    async def record_usage(
        self,
        provider: str,
        tokens: int = 0,
        calls: int = 1,
        cost_usd: float = 0.0,
    ) -> None:
        """Record API usage and persist to Supabase asynchronously."""
        s = self._get_state(provider)
        s.check_month_rollover()
        s.calls += calls
        s.tokens += tokens
        s.cost_usd += cost_usd

        # Check if we just hit capacity
        if not s.is_exhausted and s.at_capacity():
            s.is_exhausted = True
            s.exhausted_at = datetime.now(timezone.utc)
            logger.warning(
                f"[QuotaTracker] {provider} hit capacity "
                f"({s.calls}/{s.quota_calls} calls, "
                f"{s.tokens}/{s.quota_tokens} tokens)"
            )

        await self._persist_provider(provider, s)

    async def load_from_supabase(self) -> None:
        """Load persisted quota state from Supabase on startup.

        Table: provider_quota_usage
        Columns: provider_name, month_key, calls, tokens, cost_usd,
                 is_exhausted, exhausted_at, next_reset_at
        """
        if not self._supabase:
            logger.debug("[QuotaTracker] No Supabase client — in-memory only")
            return

        current_month = _month_key()
        try:
            result = (
                self._supabase
                .table("provider_quota_usage")
                .select("*")
                .eq("month_key", current_month)
                .execute()
            )
            rows = result.data or []
            for row in rows:
                provider = row["provider_name"]
                s = self._get_state(provider)
                s.calls = row.get("calls", 0)
                s.tokens = row.get("tokens", 0)
                s.cost_usd = row.get("cost_usd", 0.0)
                s.is_exhausted = row.get("is_exhausted", False)
                raw_exhausted = row.get("exhausted_at")
                if raw_exhausted:
                    s.exhausted_at = datetime.fromisoformat(raw_exhausted)
                s.month_key = current_month
            logger.info(
                f"[QuotaTracker] Loaded {len(rows)} provider states from Supabase"
            )
        except Exception as e:
            logger.warning(f"[QuotaTracker] Supabase load failed (non-fatal): {e}")

    async def _persist_provider(self, provider: str, s: _ProviderState) -> None:
        """Upsert a single provider's quota record to Supabase."""
        if not self._supabase:
            return

        try:
            record = {
                "provider_name": provider,
                "month_key": s.month_key,
                "calls": s.calls,
                "tokens": s.tokens,
                "cost_usd": s.cost_usd,
                "is_exhausted": s.is_exhausted,
                "exhausted_at": (
                    s.exhausted_at.isoformat() if s.exhausted_at else None
                ),
                "next_reset_at": s.next_reset_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            (
                self._supabase
                .table("provider_quota_usage")
                .upsert(record, on_conflict="provider_name,month_key")
                .execute()
            )
        except Exception as e:
            logger.debug(f"[QuotaTracker] Supabase persist failed (non-fatal): {e}")


# ═══════════════════════════════════════════════════════════════════
# Module-level singleton (lazy init)
# ═══════════════════════════════════════════════════════════════════

_quota_tracker_instance: Optional[QuotaTracker] = None


def get_quota_tracker() -> QuotaTracker:
    """Return the module-level QuotaTracker singleton."""
    global _quota_tracker_instance
    if _quota_tracker_instance is None:
        _quota_tracker_instance = QuotaTracker()
    return _quota_tracker_instance
