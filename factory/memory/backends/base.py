"""
AI Factory Pipeline v5.8 — Memory Backend Base

Defines the contract every storage backend must implement, plus the
BackendStatus dataclass that tracks availability, quota, and sync state.

The MemoryChain (memory_chain.py) operates on MemoryBackend instances.

Storage hierarchy (primary → fallback):
  1. Neo4j     — graph DB, 200K nodes free, no daily limit
  2. Supabase  — PostgreSQL, 500MB free, no row limit
  3. Upstash   — Redis, 10K commands/day free, resets midnight UTC
  4. Turso     — SQLite, 1B reads/25M writes per month free

Spec Authority: v5.6 §2.10 (Mother Memory)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("factory.memory.backends.base")


# ═══════════════════════════════════════════════════════════════════
# Backend Status Tracking
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BackendStatus:
    """Tracks availability, quota, and sync state for one storage backend."""
    name: str
    available: bool = True
    quota_exhausted: bool = False
    quota_reset_at: Optional[float] = None   # unix timestamp
    consecutive_errors: int = 0
    last_error: str = ""
    last_write_at: Optional[float] = None
    last_sync_at: Optional[float] = None     # when it last synced from another backend
    offline_since: Optional[float] = None   # when it went offline (for sync window)

    # ── Daily/monthly write counters (for self-tracking) ──
    daily_writes: int = 0
    daily_write_date: str = ""   # YYYY-MM-DD
    monthly_writes: int = 0
    monthly_write_month: str = "" # YYYY-MM

    def mark_quota_exhausted(self, reset_in_seconds: int, reason: str = "") -> None:
        self.available = False
        self.quota_exhausted = True
        self.quota_reset_at = time.time() + reset_in_seconds
        if not self.offline_since:
            self.offline_since = time.time()
        eta = datetime.fromtimestamp(self.quota_reset_at, tz=timezone.utc)
        logger.warning(
            f"[memory-chain] {self.name} quota exhausted{': ' + reason if reason else ''} "
            f"— auto-restore at {eta.strftime('%H:%M UTC')}"
        )

    def mark_error(self, error: str) -> None:
        self.consecutive_errors += 1
        self.last_error = error[:200]
        if self.consecutive_errors >= 3:
            self.available = False
            if not self.offline_since:
                self.offline_since = time.time()
            logger.warning(
                f"[memory-chain] {self.name} disabled after "
                f"{self.consecutive_errors} consecutive errors"
            )

    def mark_success(self) -> None:
        self.consecutive_errors = 0
        self.last_error = ""
        self.available = True
        self.last_write_at = time.time()

    def check_quota_reset(self) -> bool:
        """Returns True if quota has now reset (and re-enables the backend)."""
        if self.quota_exhausted and self.quota_reset_at:
            if time.time() >= self.quota_reset_at:
                self.available = True
                self.quota_exhausted = False
                self.quota_reset_at = None
                logger.info(f"[memory-chain] {self.name} quota reset — restored")
                return True
        return False

    def track_write(self) -> None:
        """Increment daily/monthly write counters."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        month = now.strftime("%Y-%m")
        if self.daily_write_date != today:
            self.daily_writes = 0
            self.daily_write_date = today
        if self.monthly_write_month != month:
            self.monthly_writes = 0
            self.monthly_write_month = month
        self.daily_writes += 1
        self.monthly_writes += 1


def seconds_until_midnight_utc() -> int:
    """Seconds until next midnight UTC (for daily-reset quotas like Upstash)."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    next_midnight = midnight + timedelta(days=1)
    return max(1, int((next_midnight - now).total_seconds()))


def seconds_until_first_of_month() -> int:
    """Seconds until 1st of next month UTC (for monthly-reset quotas like Turso)."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1,
                                  hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month = now.replace(month=now.month + 1, day=1,
                                  hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((next_month - now).total_seconds()))


# ═══════════════════════════════════════════════════════════════════
# MemoryBackend — abstract base class
# ═══════════════════════════════════════════════════════════════════

class MemoryBackend:
    """Base class for all Mother Memory storage backends.

    Subclasses must override the async methods below.
    All methods return bool (True = success) or list[dict].
    They must raise on hard failures (auth errors, network errors)
    and return False/[] on soft failures so the chain can handle fallback.
    """

    name: str = "base"

    async def ping(self) -> bool:
        """Check if backend is reachable. Returns True/False."""
        raise NotImplementedError

    async def setup(self) -> bool:
        """Create tables/indexes if needed. Called once at startup."""
        return True

    async def store_message(self, record: dict) -> bool:
        raise NotImplementedError

    async def get_messages(self, operator_id: str, limit: int = 40) -> list[dict]:
        raise NotImplementedError

    async def store_decision(self, record: dict) -> bool:
        raise NotImplementedError

    async def store_insight(self, record: dict) -> bool:
        raise NotImplementedError

    async def get_insights(self, operator_id: str, limit: int = 8) -> list[dict]:
        raise NotImplementedError

    async def get_messages_since(self, operator_id: str, since_ts: str) -> list[dict]:
        """Get messages created after since_ts (ISO format). Used for sync."""
        return []
