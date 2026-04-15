"""
AI Factory Pipeline v5.8 — Supabase Memory Backend (Fallback #1)

Uses the existing Supabase project (hqdbiwtcozkfzzzqanrs.supabase.co)
via its REST API (httpx — no extra SDK). Tables are auto-created on
first use via the `/rest/v1/rpc` setup endpoint.

Free tier:
  500 MB database storage, no row count limit, 5 GB bandwidth/month
  No daily rate limit — only storage cap
  Reset: storage grows until 500MB limit (effectively no reset needed)

Tables:
  memory_messages   — Telegram turns (user + bot, including off-topic)
  memory_decisions  — Pipeline stage decisions
  memory_insights   — Long-term operator facts/preferences

All queries use the Supabase PostgREST REST API:
  GET  /rest/v1/memory_messages?select=*&operator_id=eq.{id}&order=ts.desc
  POST /rest/v1/memory_messages  (upsert via Prefer: resolution=merge-duplicates)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

from factory.memory.backends.base import MemoryBackend

logger = logging.getLogger("factory.memory.backends.supabase")

_SUPABASE_URL = ""
_SUPABASE_KEY = ""


def _get_headers() -> dict:
    url = os.getenv("SUPABASE_URL", _SUPABASE_URL)
    key = os.getenv("SUPABASE_SERVICE_KEY", _SUPABASE_KEY)
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def _base() -> str:
    return os.getenv("SUPABASE_URL", _SUPABASE_URL).rstrip("/")


class SupabaseMemoryBackend(MemoryBackend):
    name = "supabase"

    async def ping(self) -> bool:
        if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{_base()}/rest/v1/memory_messages",
                    headers=_get_headers(),
                    params={"select": "id", "limit": "1"},
                )
            # 404 = table not yet created (need setup), otherwise ok
            return r.status_code in (200, 206, 404)
        except Exception as e:
            logger.debug(f"[supabase] ping failed: {e}")
            return False

    async def setup(self) -> bool:
        """Create tables via direct SQL through the REST API."""
        if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
            return False
        try:
            # Use the Supabase SQL endpoint (available with service key)
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    f"{_base()}/rest/v1/rpc/exec_sql",
                    headers={**_get_headers(), "Prefer": ""},
                    json={"query": _SETUP_SQL},
                )
            if r.status_code not in (200, 201, 204):
                # RPC exec_sql may not exist — try direct query headers
                logger.debug(f"[supabase] setup via rpc failed ({r.status_code}), tables may need manual creation")
            return True
        except Exception as e:
            logger.debug(f"[supabase] setup failed: {e}")
            return False

    async def store_message(self, record: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{_base()}/rest/v1/memory_messages",
                    headers=_get_headers(),
                    json={
                        "id": record["id"],
                        "operator_id": record["operator_id"],
                        "role": record["role"],
                        "content": record["content"],
                        "intent": record.get("intent", ""),
                        "project_id": record.get("project_id", ""),
                        "session_tag": record.get("session_tag", ""),
                        "ts": record["ts"],
                    },
                )
            if r.status_code in (200, 201, 204):
                return True
            logger.debug(f"[supabase] store_message HTTP {r.status_code}: {r.text[:100]}")
            return False
        except Exception as e:
            logger.debug(f"[supabase] store_message error: {e}")
            raise

    async def get_messages(self, operator_id: str, limit: int = 40) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{_base()}/rest/v1/memory_messages",
                    headers={**_get_headers(), "Prefer": ""},
                    params={
                        "select": "role,content,ts,intent,project_id",
                        "operator_id": f"eq.{operator_id}",
                        "order": "ts.asc",
                        "limit": str(limit),
                    },
                )
            if r.status_code == 200:
                return r.json()
            return []
        except Exception as e:
            logger.debug(f"[supabase] get_messages error: {e}")
            return []

    async def store_decision(self, record: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{_base()}/rest/v1/memory_decisions",
                    headers=_get_headers(),
                    json={
                        "id": record["id"],
                        "project_id": record["project_id"],
                        "stage": record.get("stage", ""),
                        "decision_type": record.get("decision_type", ""),
                        "content": record.get("content", ""),
                        "operator_id": record.get("operator_id", ""),
                        "ts": record["ts"],
                    },
                )
            return r.status_code in (200, 201, 204)
        except Exception as e:
            logger.debug(f"[supabase] store_decision error: {e}")
            raise

    async def store_insight(self, record: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"{_base()}/rest/v1/memory_insights",
                    headers=_get_headers(),
                    json={
                        "id": record["id"],
                        "operator_id": record["operator_id"],
                        "content": record.get("content", ""),
                        "insight_type": record.get("insight_type", "preference"),
                        "importance": record.get("importance", 3),
                        "project_id": record.get("project_id", ""),
                        "ts": record["ts"],
                    },
                )
            return r.status_code in (200, 201, 204)
        except Exception as e:
            logger.debug(f"[supabase] store_insight error: {e}")
            raise

    async def get_insights(self, operator_id: str, limit: int = 8) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{_base()}/rest/v1/memory_insights",
                    headers={**_get_headers(), "Prefer": ""},
                    params={
                        "select": "content,insight_type,importance,ts",
                        "operator_id": f"eq.{operator_id}",
                        "order": "importance.desc,ts.desc",
                        "limit": str(limit),
                    },
                )
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            logger.debug(f"[supabase] get_insights error: {e}")
            return []

    async def get_messages_since(self, operator_id: str, since_ts: str) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{_base()}/rest/v1/memory_messages",
                    headers={**_get_headers(), "Prefer": ""},
                    params={
                        "select": "id,role,content,ts,intent,project_id,session_tag",
                        "operator_id": f"eq.{operator_id}",
                        "ts": f"gt.{since_ts}",
                        "order": "ts.asc",
                        "limit": "500",
                    },
                )
            return r.json() if r.status_code == 200 else []
        except Exception:
            return []


# SQL executed once to create tables (via Supabase SQL editor or migration)
_SETUP_SQL = """
CREATE TABLE IF NOT EXISTS memory_messages (
    id          TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT,
    intent      TEXT DEFAULT '',
    project_id  TEXT DEFAULT '',
    session_tag TEXT DEFAULT '',
    ts          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mem_msg_op ON memory_messages (operator_id, ts DESC);

CREATE TABLE IF NOT EXISTS memory_decisions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    stage         TEXT DEFAULT '',
    decision_type TEXT DEFAULT '',
    content       TEXT,
    operator_id   TEXT DEFAULT '',
    ts            TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mem_dec_proj ON memory_decisions (project_id, ts DESC);

CREATE TABLE IF NOT EXISTS memory_insights (
    id           TEXT PRIMARY KEY,
    operator_id  TEXT NOT NULL,
    content      TEXT,
    insight_type TEXT DEFAULT 'preference',
    importance   INTEGER DEFAULT 3,
    project_id   TEXT DEFAULT '',
    ts           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mem_ins_op ON memory_insights (operator_id, importance DESC);
"""
