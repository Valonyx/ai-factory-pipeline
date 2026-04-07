"""
AI Factory Pipeline v5.6 — Turso SQLite Memory Backend (Fallback #3)

Turso provides serverless SQLite databases accessible via HTTP.
No SDK needed — all queries sent through the Turso HTTP Data API.

Free tier:
  500 databases, 9 GB storage, 1 billion row reads/month,
  25 million row writes/month (resets 1st of each month)
  Free account: https://turso.tech (no credit card)

Env vars:
  TURSO_DATABASE_URL  — e.g. https://dbname-org.turso.io
  TURSO_AUTH_TOKEN    — the auth token from Turso CLI / dashboard

Tables are created automatically on first use via the HTTP pipeline API.

The HTTP Data API endpoint:
  POST {TURSO_DATABASE_URL}/v2/pipeline
  Body: {"requests": [{"type": "execute", "stmt": {"sql": "...", "args": [...]}}]}

Usage tracking:
  We self-track monthly write count; stop at 24M writes/month (true limit 25M).
  Read count is not tracked (1B/month is effectively unlimited for this use).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

import httpx

from factory.memory.backends.base import (
    MemoryBackend,
    seconds_until_first_of_month,
)

logger = logging.getLogger("factory.memory.backends.turso")

_TURSO_MONTHLY_WRITE_LIMIT = 24_000_000  # stop 1M before true limit


def _base() -> str:
    url = os.getenv("TURSO_DATABASE_URL", "").rstrip("/")
    # Turso gives libsql:// URLs; the HTTP Data API uses https://
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return url


def _token() -> str:
    return os.getenv("TURSO_AUTH_TOKEN", "")


async def _execute(sql: str, args: Optional[list] = None) -> dict:
    """Execute one SQL statement via Turso HTTP pipeline API."""
    url = _base()
    token = _token()
    if not url or not token:
        raise ValueError("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN not set")

    stmt: dict[str, Any] = {"sql": sql}
    if args:
        stmt["args"] = [{"type": "text", "value": str(a)} for a in args]

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{url}/v2/pipeline",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"requests": [{"type": "execute", "stmt": stmt}]},
        )

    if r.status_code != 200:
        raise Exception(f"Turso HTTP {r.status_code}: {r.text[:100]}")

    data = r.json()
    results = data.get("results", [])
    if results and results[0].get("type") == "error":
        raise Exception(f"Turso SQL error: {results[0].get('error', {})}")
    return data


async def _query(sql: str, args: Optional[list] = None) -> list[dict]:
    """Execute and return rows as list of dicts."""
    data = await _execute(sql, args)
    results = data.get("results", [])
    if not results:
        return []
    response = results[0].get("response", {})
    result = response.get("result", {})
    cols = [c["name"] for c in result.get("cols", [])]
    rows = result.get("rows", [])
    return [{cols[i]: r[i]["value"] for i in range(len(cols))} for r in rows]


class TursoMemoryBackend(MemoryBackend):
    name = "turso"

    _monthly_writes: int = 0
    _monthly_month: str = ""

    def _count_write(self) -> bool:
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        if self._monthly_month != month:
            self._monthly_writes = 0
            self._monthly_month = month
        self._monthly_writes += 1
        return self._monthly_writes <= _TURSO_MONTHLY_WRITE_LIMIT

    async def ping(self) -> bool:
        if not _base() or not _token():
            return False
        try:
            await _execute("SELECT 1")
            return True
        except Exception as e:
            logger.debug(f"[turso] ping failed: {e}")
            return False

    async def setup(self) -> bool:
        """Create tables if they don't exist."""
        if not _base() or not _token():
            return False
        try:
            await _execute("""
                CREATE TABLE IF NOT EXISTS memory_messages (
                    id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    intent TEXT DEFAULT '',
                    project_id TEXT DEFAULT '',
                    session_tag TEXT DEFAULT '',
                    ts TEXT NOT NULL
                )
            """)
            await _execute(
                "CREATE INDEX IF NOT EXISTS idx_mm_op ON memory_messages (operator_id, ts)"
            )
            await _execute("""
                CREATE TABLE IF NOT EXISTS memory_decisions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    stage TEXT DEFAULT '',
                    decision_type TEXT DEFAULT '',
                    content TEXT,
                    operator_id TEXT DEFAULT '',
                    ts TEXT NOT NULL
                )
            """)
            await _execute("""
                CREATE TABLE IF NOT EXISTS memory_insights (
                    id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    content TEXT,
                    insight_type TEXT DEFAULT 'preference',
                    importance INTEGER DEFAULT 3,
                    project_id TEXT DEFAULT '',
                    ts TEXT NOT NULL
                )
            """)
            logger.info("[turso] tables ready")
            return True
        except Exception as e:
            logger.debug(f"[turso] setup failed: {e}")
            return False

    async def store_message(self, record: dict) -> bool:
        if not self._count_write():
            raise Exception(f"429 RESOURCE_EXHAUSTED — Turso monthly write limit")
        try:
            await _execute(
                "INSERT OR IGNORE INTO memory_messages "
                "(id,operator_id,role,content,intent,project_id,session_tag,ts) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [
                    record["id"], record["operator_id"], record["role"],
                    record["content"], record.get("intent", ""),
                    record.get("project_id", ""), record.get("session_tag", ""),
                    record["ts"],
                ],
            )
            return True
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise
            logger.debug(f"[turso] store_message error: {e}")
            raise

    async def get_messages(self, operator_id: str, limit: int = 40) -> list[dict]:
        try:
            rows = await _query(
                "SELECT role, content, ts, intent, project_id "
                "FROM memory_messages WHERE operator_id=? "
                "ORDER BY ts ASC LIMIT ?",
                [operator_id, limit],
            )
            return [{"role": r["role"], "content": r["content"]} for r in rows]
        except Exception as e:
            logger.debug(f"[turso] get_messages error: {e}")
            return []

    async def store_decision(self, record: dict) -> bool:
        if not self._count_write():
            raise Exception("429 RESOURCE_EXHAUSTED — Turso monthly write limit")
        try:
            await _execute(
                "INSERT OR IGNORE INTO memory_decisions "
                "(id,project_id,stage,decision_type,content,operator_id,ts) "
                "VALUES (?,?,?,?,?,?,?)",
                [
                    record["id"], record["project_id"], record.get("stage", ""),
                    record.get("decision_type", ""), record.get("content", ""),
                    record.get("operator_id", ""), record["ts"],
                ],
            )
            return True
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise
            raise

    async def store_insight(self, record: dict) -> bool:
        if not self._count_write():
            raise Exception("429 RESOURCE_EXHAUSTED — Turso monthly write limit")
        try:
            await _execute(
                "INSERT OR IGNORE INTO memory_insights "
                "(id,operator_id,content,insight_type,importance,project_id,ts) "
                "VALUES (?,?,?,?,?,?,?)",
                [
                    record["id"], record["operator_id"], record.get("content", ""),
                    record.get("insight_type", "preference"),
                    record.get("importance", 3),
                    record.get("project_id", ""), record["ts"],
                ],
            )
            return True
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e):
                raise
            raise

    async def get_insights(self, operator_id: str, limit: int = 8) -> list[dict]:
        try:
            return await _query(
                "SELECT content, insight_type, importance, ts "
                "FROM memory_insights WHERE operator_id=? "
                "ORDER BY importance DESC, ts DESC LIMIT ?",
                [operator_id, limit],
            )
        except Exception as e:
            logger.debug(f"[turso] get_insights error: {e}")
            return []

    async def get_messages_since(self, operator_id: str, since_ts: str) -> list[dict]:
        try:
            return await _query(
                "SELECT id, role, content, ts, intent, project_id, session_tag "
                "FROM memory_messages WHERE operator_id=? AND ts > ? ORDER BY ts ASC",
                [operator_id, since_ts],
            )
        except Exception:
            return []
