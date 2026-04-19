"""
AI Factory Pipeline v5.8 — Mother Memory Chain Orchestrator

The MemoryChain is the single entry point for all memory reads and writes.
It manages four backends in priority order:

  1. Neo4j    (primary)   — graph DB, AuraDB Free, no daily limit
  2. Supabase (fallback1) — PostgreSQL REST, 500 MB free
  3. Upstash  (fallback2) — Redis REST, 10K commands/day, resets midnight UTC
  4. Turso    (fallback3) — SQLite HTTP, 25M writes/month, resets 1st of month

Write strategy — Fan-out:
  Every write goes to ALL available backends simultaneously via asyncio.gather().
  Data is never in only one place. If a backend is unavailable, the write is
  queued in _pending_writes and replayed when the backend comes back online.

Read strategy — Priority waterfall:
  Reads try backends in order (Neo4j → Supabase → Upstash → Turso).
  The first backend that returns a non-empty result wins.

Sync-on-restore:
  When a backend's quota resets or connectivity resumes, the chain calls
  sync_backend() which replays all records the backend missed while offline,
  fetching them from the current read-primary using get_messages_since().

Quota management:
  BackendStatus.check_quota_reset() is called on a background timer.
  Upstash resets at midnight UTC; Turso resets on the 1st of each month.
  When a higher-priority backend restores, it is re-added to the active pool
  and a sync window fills the gap.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from factory.memory.backends.base import (
    BackendStatus,
    MemoryBackend,
    seconds_until_midnight_utc,
    seconds_until_first_of_month,
)

logger = logging.getLogger("factory.memory.memory_chain")

# How long to wait for any single backend write before giving up (seconds)
_WRITE_TIMEOUT = 8
# How long to wait for a read before trying the next backend
_READ_TIMEOUT = 6
# Background quota-reset check interval (seconds)
_QUOTA_CHECK_INTERVAL = 60
# Max pending writes queued per offline backend
_MAX_PENDING = 500


class MemoryChain:
    """
    Orchestrates fan-out writes and priority-waterfall reads across
    all four Mother Memory backends.

    Usage (singleton via get_memory_chain()):
        chain = get_memory_chain()
        await chain.initialize()          # once at startup
        await chain.store_message(record)
        msgs = await chain.get_messages(operator_id)
    """

    def __init__(self) -> None:
        self._backends: list[MemoryBackend] = []
        self._statuses: dict[str, BackendStatus] = {}
        self._initialized = False
        self._quota_task: Optional[asyncio.Task] = None
        # Pending writes: backend_name → list of (operation_name, record)
        self._pending_writes: dict[str, list[tuple[str, dict]]] = {}

    # ═══════════════════════════════════════════════════════════════════
    # Initialization
    # ═══════════════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        """Set up all backends and start background quota checker."""
        if self._initialized:
            return
        self._initialized = True

        from factory.memory.backends.neo4j_backend import Neo4jMemoryBackend
        from factory.memory.backends.supabase_backend import SupabaseMemoryBackend
        from factory.memory.backends.upstash_backend import UpstashMemoryBackend
        from factory.memory.backends.turso_backend import TursoMemoryBackend

        backends = [
            Neo4jMemoryBackend(),
            SupabaseMemoryBackend(),
            UpstashMemoryBackend(),
            TursoMemoryBackend(),
        ]

        for b in backends:
            self._backends.append(b)
            self._statuses[b.name] = BackendStatus(name=b.name)
            self._pending_writes[b.name] = []

        # Ping all backends concurrently; run setup on those that respond
        results = await asyncio.gather(
            *[self._probe_backend(b) for b in self._backends],
            return_exceptions=True,
        )
        for b, r in zip(self._backends, results):
            if isinstance(r, Exception):
                logger.warning(f"[memory-chain] {b.name} probe failed: {r}")

        # Log initial state
        available = [b.name for b in self._backends if self._statuses[b.name].available]
        unavailable = [b.name for b in self._backends if not self._statuses[b.name].available]
        logger.info(f"[memory-chain] ready — available: {available}, unavailable: {unavailable}")

        # Start background quota-reset checker
        try:
            loop = asyncio.get_running_loop()
            self._quota_task = loop.create_task(self._quota_reset_loop())
        except RuntimeError:
            pass  # No event loop — will be started lazily

    async def _probe_backend(self, b: MemoryBackend) -> None:
        """Ping one backend and run setup if reachable."""
        status = self._statuses[b.name]
        try:
            ok = await asyncio.wait_for(b.ping(), timeout=10)
            if ok:
                await asyncio.wait_for(b.setup(), timeout=15)
                status.mark_success()
                logger.info(f"[memory-chain] {b.name} connected")
            else:
                status.available = False
                logger.debug(f"[memory-chain] {b.name} not reachable (ping=False)")
        except Exception as e:
            status.available = False
            logger.debug(f"[memory-chain] {b.name} probe error: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # Fan-out Write
    # ═══════════════════════════════════════════════════════════════════

    async def _write_to_backend(
        self, b: MemoryBackend, operation: str, record: dict
    ) -> bool:
        """Write to one backend; handle quota/errors; queue if unavailable."""
        status = self._statuses[b.name]
        status.check_quota_reset()

        if not status.available:
            # Queue for later replay
            pending = self._pending_writes[b.name]
            if len(pending) < _MAX_PENDING:
                pending.append((operation, record.copy()))
            return False

        method = getattr(b, operation, None)
        if method is None:
            return False

        try:
            ok = await asyncio.wait_for(method(record), timeout=_WRITE_TIMEOUT)
            if ok:
                status.mark_success()
                status.track_write()
            return bool(ok)
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                # Determine reset time based on backend type
                if b.name == "upstash":
                    reset_secs = seconds_until_midnight_utc()
                    status.mark_quota_exhausted(reset_secs, reason="daily limit")
                elif b.name == "turso":
                    reset_secs = seconds_until_first_of_month()
                    status.mark_quota_exhausted(reset_secs, reason="monthly write limit")
                else:
                    status.mark_quota_exhausted(3600, reason=err[:80])
                pending = self._pending_writes[b.name]
                if len(pending) < _MAX_PENDING:
                    pending.append((operation, record.copy()))
            else:
                status.mark_error(err)
                pending = self._pending_writes[b.name]
                if len(pending) < _MAX_PENDING:
                    pending.append((operation, record.copy()))
            return False

    async def _fan_out(self, operation: str, record: dict) -> bool:
        """Write record to all available backends simultaneously."""
        if not self._initialized:
            await self.initialize()

        tasks = [
            self._write_to_backend(b, operation, record)
            for b in self._backends
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        if success_count == 0:
            logger.warning(
                f"[memory-chain] {operation} failed on all backends — "
                f"record id={record.get('id', '?')} lost from persistent store"
            )
            return False
        return True

    # ═══════════════════════════════════════════════════════════════════
    # Priority-Waterfall Read
    # ═══════════════════════════════════════════════════════════════════

    async def _read_from_chain(self, operation: str, **kwargs) -> Any:
        """Try each backend in priority order; return first non-empty result."""
        if not self._initialized:
            await self.initialize()

        for b in self._backends:
            status = self._statuses[b.name]
            status.check_quota_reset()
            if not status.available:
                continue
            method = getattr(b, operation, None)
            if method is None:
                continue
            try:
                result = await asyncio.wait_for(method(**kwargs), timeout=_READ_TIMEOUT)
                if result:  # non-empty list / truthy value
                    return result
            except Exception as e:
                status.mark_error(str(e))
                logger.debug(f"[memory-chain] read {operation} from {b.name} failed: {e}")

        return []  # all backends empty or offline

    # ═══════════════════════════════════════════════════════════════════
    # Public API — mirroring MemoryBackend interface
    # ═══════════════════════════════════════════════════════════════════

    async def store_message(self, record: dict) -> bool:
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        return await self._fan_out("store_message", record)

    async def get_messages(self, operator_id: str, limit: int = 40) -> list[dict]:
        return await self._read_from_chain(
            "get_messages", operator_id=operator_id, limit=limit
        )

    async def store_decision(self, record: dict) -> bool:
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        return await self._fan_out("store_decision", record)

    async def store_insight(self, record: dict) -> bool:
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        return await self._fan_out("store_insight", record)

    async def get_insights(self, operator_id: str, limit: int = 8) -> list[dict]:
        return await self._read_from_chain(
            "get_insights", operator_id=operator_id, limit=limit
        )

    # ═══════════════════════════════════════════════════════════════════
    # Sync-on-Restore
    # ═══════════════════════════════════════════════════════════════════

    async def sync_backend(self, target: MemoryBackend) -> int:
        """
        Replay any records a restored backend missed while offline.

        Fetches records from the current read-primary using get_messages_since()
        and writes them directly to `target`. Also drains the pending_writes
        queue for this backend.

        Returns the number of records synced.
        """
        status = self._statuses[target.name]
        if not status.available:
            return 0

        synced = 0

        # ── 1. Drain pending writes queued while offline ──
        pending = self._pending_writes[target.name]
        if pending:
            logger.info(
                f"[memory-chain] {target.name} restoring {len(pending)} pending writes"
            )
            for operation, record in list(pending):
                method = getattr(target, operation, None)
                if method is None:
                    continue
                try:
                    await asyncio.wait_for(method(record), timeout=_WRITE_TIMEOUT)
                    synced += 1
                except Exception as e:
                    logger.debug(f"[memory-chain] sync pending write failed: {e}")
            self._pending_writes[target.name].clear()

        # ── 2. Fetch missed messages from the read-primary ──
        if status.offline_since:
            since_ts = datetime.fromtimestamp(
                status.offline_since, tz=timezone.utc
            ).isoformat()

            # Find the highest-priority backend (not target) that's available
            source = next(
                (b for b in self._backends
                 if b.name != target.name and self._statuses[b.name].available),
                None,
            )
            if source:
                try:
                    # We don't know all operator_ids, so we use a wildcard approach:
                    # get_messages_since per-backend returns ALL operators if operator_id=""
                    # Use a sentinel that backends interpret as "all operators"
                    missed = await asyncio.wait_for(
                        source.get_messages_since("__all__", since_ts),
                        timeout=15,
                    )
                    for record in missed:
                        try:
                            await asyncio.wait_for(
                                target.store_message(record), timeout=_WRITE_TIMEOUT
                            )
                            synced += 1
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"[memory-chain] sync from {source.name} failed: {e}")

            status.offline_since = None
            status.last_sync_at = time.time()

        if synced:
            logger.info(f"[memory-chain] {target.name} sync complete — {synced} records replayed")
        return synced

    # ═══════════════════════════════════════════════════════════════════
    # Background Quota-Reset Loop
    # ═══════════════════════════════════════════════════════════════════

    async def _quota_reset_loop(self) -> None:
        """Periodically check quota resets and connectivity restoration for offline backends.

        Issue 32: also re-probes backends that went offline due to connectivity errors
        (not just quota exhaustion). When a backend comes back, sync_backend() drains
        the pending writes it missed.
        """
        while True:
            await asyncio.sleep(_QUOTA_CHECK_INTERVAL)
            for b in self._backends:
                status = self._statuses[b.name]
                # ── Path A: quota reset ────────────────────────────────
                if status.check_quota_reset():
                    try:
                        ok = await asyncio.wait_for(b.ping(), timeout=10)
                        if ok:
                            logger.info(
                                f"[memory-chain] {b.name} quota reset confirmed — syncing"
                            )
                            asyncio.create_task(self.sync_backend(b))
                        else:
                            status.available = False
                    except Exception as e:
                        status.available = False
                        logger.debug(f"[memory-chain] {b.name} post-reset ping failed: {e}")
                # ── Path B: Issue 32 — connectivity restore probe ──────
                # Re-probe backends that are offline due to errors (not quota).
                # This allows neo4j or any other backend to recover automatically
                # when connectivity is restored between quota-check cycles.
                elif not status.available and not status.quota_exhausted:
                    try:
                        ok = await asyncio.wait_for(b.ping(), timeout=10)
                        if ok:
                            await asyncio.wait_for(b.setup(), timeout=15)
                            status.mark_success()
                            logger.info(
                                f"[memory-chain] {b.name} connectivity restored — syncing"
                            )
                            asyncio.create_task(self.sync_backend(b))
                    except Exception:
                        pass  # still offline — will retry next cycle

    # ═══════════════════════════════════════════════════════════════════
    # Issue 32: Primary Election
    # ═══════════════════════════════════════════════════════════════════

    def promote_primary(self) -> str:
        """Issue 32: elect the first available backend as effective read-primary.

        When the configured primary (neo4j, index 0) is persistently offline,
        this method identifies the next available backend so callers can know
        which backend is serving reads. Queues a sync for that backend to drain
        any pending writes it may have accumulated.

        Returns the name of the elected primary, or "none" if all backends offline.
        """
        for b in self._backends:
            st = self._statuses[b.name]
            if st.available:
                if b is not self._backends[0]:
                    logger.info(
                        f"[memory-chain] promote_primary: {b.name} is effective read-primary "
                        f"({self._backends[0].name} is offline)"
                    )
                    # Drain pending writes to the elected primary
                    if self._pending_writes.get(b.name):
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(self.sync_backend(b))
                        except RuntimeError:
                            pass  # no running loop — sync will happen on next quota cycle
                return b.name
        logger.warning("[memory-chain] promote_primary: all backends offline")
        return "none"

    # ═══════════════════════════════════════════════════════════════════
    # Status / Diagnostics
    # ═══════════════════════════════════════════════════════════════════

    def status_report(self) -> list[dict]:
        """Return a list of status dicts for all backends (used by /providers command)."""
        report = []
        for b in self._backends:
            s = self._statuses[b.name]
            entry: dict[str, Any] = {
                "name": b.name,
                "available": s.available,
                "quota_exhausted": s.quota_exhausted,
                "consecutive_errors": s.consecutive_errors,
                "pending_writes": len(self._pending_writes[b.name]),
            }
            if s.quota_reset_at:
                eta = int(s.quota_reset_at - time.time())
                entry["quota_resets_in"] = max(0, eta)
            report.append(entry)
        return report


# ═══════════════════════════════════════════════════════════════════
# Singleton accessor
# ═══════════════════════════════════════════════════════════════════

_chain: Optional[MemoryChain] = None


def get_memory_chain() -> MemoryChain:
    """Return the process-wide MemoryChain singleton."""
    global _chain
    if _chain is None:
        _chain = MemoryChain()
    return _chain
