"""
AI Factory Pipeline v5.6 — Upstash Redis Memory Backend (Fallback #2)

Upstash provides serverless Redis with a REST API — no SDK needed, uses httpx.
Data is stored in sorted sets (by unix timestamp) for chronological retrieval.

Free tier:
  10,000 commands/day (resets midnight UTC)
  256 MB storage, no bandwidth limit
  Free account: https://upstash.com (no credit card)

Env vars:
  UPSTASH_REDIS_REST_URL   — e.g. https://cute-yak-xxxxx.upstash.io
  UPSTASH_REDIS_REST_TOKEN — the REST token from Upstash console (REST API tab)

Data layout in Redis:
  Sorted set "mem:msg:{operator_id}"   → score=unix_ts, value=json(record)
  Sorted set "mem:ins:{operator_id}"   → score=importance*1e9+unix_ts
  Sorted set "mem:dec:{project_id}"    → score=unix_ts, value=json(record)

Usage tracking:
  Key "meta:daily_cmds" is incremented on each request (1 Redis command)
  We self-report quota at 9,500 commands/day to leave headroom.
  Reset detected via BackendStatus.check_quota_reset() at midnight UTC.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import timezone

import httpx

from factory.memory.backends.base import (
    MemoryBackend,
    seconds_until_midnight_utc,
)

logger = logging.getLogger("factory.memory.backends.upstash")

# Self-imposed daily limit (true limit is 10K, we stop at 9.5K for safety)
_UPSTASH_DAILY_LIMIT = 9_500


def _base() -> str:
    # Support both naming conventions (console uses REST_ prefix)
    return (
        os.getenv("UPSTASH_REDIS_REST_URL")
        or os.getenv("UPSTASH_REDIS_URL", "")
    ).rstrip("/")


def _token() -> str:
    return (
        os.getenv("UPSTASH_REDIS_REST_TOKEN")
        or os.getenv("UPSTASH_REDIS_TOKEN", "")
    )


async def _cmd(*args) -> dict:
    """Execute one Redis command via Upstash REST API."""
    url = _base()
    token = _token()
    if not url or not token:
        raise ValueError("UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN not set")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=list(args),
        )
    if r.status_code != 200:
        raise Exception(f"Upstash HTTP {r.status_code}: {r.text[:100]}")
    return r.json()


class UpstashMemoryBackend(MemoryBackend):
    name = "upstash"

    # In-process daily command counter (reset at midnight UTC)
    _daily_cmds: int = 0
    _daily_date: str = ""

    def _check_and_count(self) -> bool:
        """Increment counter; return False if daily limit reached."""
        from datetime import datetime
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_cmds = 0
            self._daily_date = today
        self._daily_cmds += 1
        return self._daily_cmds <= _UPSTASH_DAILY_LIMIT

    async def ping(self) -> bool:
        if not _base() or not _token():
            return False
        try:
            result = await _cmd("PING")  # type: ignore[arg-type]
            return result.get("result") == "PONG"
        except Exception as e:
            logger.debug(f"[upstash] ping failed: {e}")
            return False

    async def store_message(self, record: dict) -> bool:
        if not self._check_and_count():
            raise Exception(f"429 RESOURCE_EXHAUSTED — Upstash daily limit {_UPSTASH_DAILY_LIMIT}")
        try:
            score = _ts_to_score(record["ts"])
            key = f"mem:msg:{record['operator_id']}"
            value = json.dumps({
                "id": record["id"],
                "role": record["role"],
                "content": record["content"],
                "intent": record.get("intent", ""),
                "project_id": record.get("project_id", ""),
                "session_tag": record.get("session_tag", ""),
                "ts": record["ts"],
            })
            result = await _cmd("ZADD", key, str(score), value)
            return result.get("error") is None
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                raise
            logger.debug(f"[upstash] store_message error: {e}")
            raise

    async def get_messages(self, operator_id: str, limit: int = 40) -> list[dict]:
        if not self._check_and_count():
            return []
        try:
            key = f"mem:msg:{operator_id}"
            # ZRANGE key 0 -1 — all members, lowest score first (chronological)
            # Then take last `limit` items
            result = await _cmd("ZRANGE", key, str(-limit), "-1")
            members = result.get("result", [])
            rows = []
            for m in members:
                try:
                    rows.append(json.loads(m))
                except json.JSONDecodeError:
                    pass
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        except Exception as e:
            logger.debug(f"[upstash] get_messages error: {e}")
            return []

    async def store_decision(self, record: dict) -> bool:
        if not self._check_and_count():
            raise Exception(f"429 RESOURCE_EXHAUSTED — Upstash daily limit")
        try:
            score = _ts_to_score(record["ts"])
            key = f"mem:dec:{record['project_id']}"
            value = json.dumps({
                "id": record["id"],
                "stage": record.get("stage", ""),
                "decision_type": record.get("decision_type", ""),
                "content": record.get("content", "")[:500],
                "operator_id": record.get("operator_id", ""),
                "ts": record["ts"],
            })
            result = await _cmd("ZADD", key, str(score), value)
            return result.get("error") is None
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise
            raise

    async def store_insight(self, record: dict) -> bool:
        if not self._check_and_count():
            raise Exception(f"429 RESOURCE_EXHAUSTED — Upstash daily limit")
        try:
            # Score = importance * 1e10 + timestamp (higher importance = higher priority in ZREVRANGE)
            score = record.get("importance", 3) * 10_000_000_000 + _ts_to_score(record["ts"])
            key = f"mem:ins:{record['operator_id']}"
            value = json.dumps({
                "content": record.get("content", ""),
                "insight_type": record.get("insight_type", "preference"),
                "importance": record.get("importance", 3),
                "ts": record["ts"],
            })
            result = await _cmd("ZADD", key, str(score), value)
            return result.get("error") is None
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise
            raise

    async def get_insights(self, operator_id: str, limit: int = 8) -> list[dict]:
        if not self._check_and_count():
            return []
        try:
            key = f"mem:ins:{operator_id}"
            # ZREVRANGE = highest score first (most important/recent)
            result = await _cmd("ZREVRANGE", key, "0", str(limit - 1))
            members = result.get("result", [])
            rows = []
            for m in members:
                try:
                    rows.append(json.loads(m))
                except json.JSONDecodeError:
                    pass
            return rows
        except Exception as e:
            logger.debug(f"[upstash] get_insights error: {e}")
            return []

    async def get_messages_since(self, operator_id: str, since_ts: str) -> list[dict]:
        if not self._check_and_count():
            return []
        try:
            since_score = _ts_to_score(since_ts)
            key = f"mem:msg:{operator_id}"
            result = await _cmd("ZRANGEBYSCORE", key, str(since_score + 1), "+inf")
            members = result.get("result", [])
            rows = []
            for m in members:
                try:
                    rows.append(json.loads(m))
                except json.JSONDecodeError:
                    pass
            return rows
        except Exception:
            return []


def _ts_to_score(ts: str) -> int:
    """Convert ISO timestamp to unix microseconds for sorted set score."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1_000_000)
    except Exception:
        return int(time.time() * 1_000_000)
