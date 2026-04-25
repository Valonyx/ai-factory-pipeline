"""
AI Factory Pipeline v5.8 — Local Memory Backend

Writes every memory record to the local filesystem under
  {project_root}/local_memory/

Directory structure:
  local_memory/
    messages/           — Telegram conversation turns (one JSON file per message)
    decisions/          — Pipeline stage decisions
    insights/           — Long-term operator facts and preferences
    operator_states/    — Operator conversational state snapshots
    scout_cache/        — Scout search result cache entries
    projects/
      {project_id}/
        blueprint/      — S2 blueprint outputs
        legal/          — S1 legal classification outputs
        pipeline/       — Stage-by-stage pipeline state snapshots
        artifacts/      — Generated file references

Always available (no API key, no network). Acts as the ultimate fallback
and as a human-readable audit trail.

All write methods accept a flat dict (single `record` argument) so they
are compatible with MemoryChain._fan_out() which calls method(record).

Usage: automatically registered in MemoryChain.initialize() alongside
Supabase, Turso, Upstash, Neo4j.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from factory.memory.backends.base import MemoryBackend

logger = logging.getLogger("factory.memory.backends.local")


def _root() -> Path:
    """Return local_memory root — next to the project root."""
    base = Path(os.getenv("LOCAL_MEMORY_ROOT", "")).expanduser()
    if not base or base == Path(""):
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "factory").is_dir():
                base = parent / "local_memory"
                break
        else:
            base = Path.home() / "factory-projects" / "local_memory"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _safe_filename(s: str) -> str:
    """Strip characters unsafe for filenames."""
    return re.sub(r"[^a-zA-Z0-9_\-.]", "_", str(s))[:80]


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        logger.debug(f"[local-memory] write failed {path}: {e}")


def _read_all(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    records = []
    for f in sorted(directory.glob("*.json")):
        try:
            records.append(json.loads(f.read_text()))
        except Exception:
            pass
    return records


class LocalMemoryBackend(MemoryBackend):
    """Always-on local filesystem memory backend.

    Never exhausts quota, never goes offline. Stores everything in
    local_memory/ next to the project root so the team can inspect,
    version-control, or hand off to other tools.

    All write methods accept a flat record dict (single argument) so
    they work with MemoryChain._fan_out() which calls method(record).
    """

    name = "local"

    async def ping(self) -> bool:
        try:
            _root()
            return True
        except Exception:
            return False

    async def setup(self) -> bool:
        try:
            root = _root()
            for sub in (
                "messages",
                "decisions",
                "insights",
                "operator_states",
                "scout_cache",
                "projects",
            ):
                (root / sub).mkdir(parents=True, exist_ok=True)
            logger.info(f"[local-memory] root: {root}")
            return True
        except Exception as e:
            logger.warning(f"[local-memory] setup failed: {e}")
            return False

    # ── Core write operations ─────────────────────────────────────────

    async def store_message(self, record: dict) -> bool:
        try:
            ts = int(time.time() * 1000)
            op = _safe_filename(record.get("operator_id", "unknown"))
            fname = f"{ts}_{op}.json"
            _write(_root() / "messages" / fname, record)
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_message: {e}")
            return False

    async def store_decision(self, record: dict) -> bool:
        try:
            ts = int(time.time() * 1000)
            proj = _safe_filename(record.get("project_id", "global"))
            stage = _safe_filename(record.get("stage", "unknown"))
            _write(
                _root() / "decisions" / proj / f"{stage}_{ts}.json",
                record,
            )
            # Also mirror under projects/
            _write(
                _root() / "projects" / proj / "pipeline" / f"decision_{stage}_{ts}.json",
                record,
            )
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_decision: {e}")
            return False

    async def store_insight(self, record: dict) -> bool:
        try:
            ts = int(time.time() * 1000)
            op = _safe_filename(record.get("operator_id", "unknown"))
            _write(_root() / "insights" / f"{op}_{ts}.json", record)
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_insight: {e}")
            return False

    # ── Stage output snapshots ────────────────────────────────────────

    async def store_pipeline_state(self, record: dict) -> bool:
        """Save a full pipeline stage output snapshot.

        Accepts a flat dict with at minimum: project_id, stage, state.
        Compatible with MemoryChain._fan_out("store_pipeline_state", record).
        """
        try:
            ts = int(time.time() * 1000)
            pid = _safe_filename(record.get("project_id", "unknown"))
            stg = _safe_filename(record.get("stage", "unknown"))
            _write(
                _root() / "projects" / pid / "pipeline" / f"{stg}_{ts}.json",
                record,
            )
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_pipeline_state: {e}")
            return False

    async def store_blueprint(self, record: dict) -> bool:
        """Save blueprint output.

        Accepts a flat dict with at minimum: project_id.
        Compatible with MemoryChain._fan_out("store_blueprint", record).
        """
        try:
            pid = _safe_filename(record.get("project_id", "unknown"))
            ts = int(time.time() * 1000)
            _write(
                _root() / "projects" / pid / "blueprint" / f"blueprint_{ts}.json",
                record,
            )
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_blueprint: {e}")
            return False

    async def store_legal(self, record: dict) -> bool:
        """Save legal dossier output.

        Accepts a flat dict with at minimum: project_id.
        Compatible with MemoryChain._fan_out("store_legal", record).
        """
        try:
            pid = _safe_filename(record.get("project_id", "unknown"))
            ts = int(time.time() * 1000)
            _write(
                _root() / "projects" / pid / "legal" / f"legal_{ts}.json",
                record,
            )
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_legal: {e}")
            return False

    # ── Operator state / preferences ─────────────────────────────────

    async def store_operator_state(self, record: dict) -> bool:
        """Save operator conversational state or preference update.

        Accepts a flat dict with at minimum: operator_id.
        Compatible with MemoryChain._fan_out("store_operator_state", record).
        """
        try:
            ts = int(time.time() * 1000)
            op = _safe_filename(record.get("operator_id", "unknown"))
            _write(_root() / "operator_states" / f"{op}_{ts}.json", record)
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_operator_state: {e}")
            return False

    # ── Scout result cache ────────────────────────────────────────────

    async def store_scout_cache(self, record: dict) -> bool:
        """Save a scout search cache entry.

        Accepts a flat dict with at minimum: query_hash, source.
        Compatible with MemoryChain._fan_out("store_scout_cache", record).
        """
        try:
            ts = int(time.time() * 1000)
            qh = _safe_filename(record.get("query_hash", "unknown"))
            _write(_root() / "scout_cache" / f"{qh}_{ts}.json", record)
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_scout_cache: {e}")
            return False

    # ── Read operations ───────────────────────────────────────────────

    async def get_messages(
        self,
        operator_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        try:
            records = _read_all(_root() / "messages")
            filtered = [
                r for r in records
                if r.get("operator_id") == operator_id
            ]
            return filtered[-(limit + offset):][-limit:] if limit else filtered
        except Exception:
            return []

    async def get_decisions(self, project_id: str) -> list[dict]:
        try:
            pid = _safe_filename(project_id)
            return _read_all(_root() / "decisions" / pid)
        except Exception:
            return []

    async def get_insights(self, operator_id: str, limit: int = 8) -> list[dict]:
        try:
            records = _read_all(_root() / "insights")
            filtered = [r for r in records if r.get("operator_id") == operator_id]
            return filtered[-limit:] if limit else filtered
        except Exception:
            return []

    async def get_pipeline_state(self, project_id: str, stage: str = "") -> list[dict]:
        """Return all pipeline state snapshots for a project (optionally filtered by stage)."""
        try:
            pid = _safe_filename(project_id)
            records = _read_all(_root() / "projects" / pid / "pipeline")
            if stage:
                records = [r for r in records if r.get("stage") == stage]
            return records
        except Exception:
            return []

    # ── MemoryBackend contract ────────────────────────────────────────

    async def write(self, operation: str, record: dict) -> bool:
        """Route write to the correct sub-store based on operation name."""
        op = operation.lower()
        if op in ("store_message", "message"):
            return await self.store_message(record)
        if op in ("store_decision", "decision", "store_stage_insight"):
            return await self.store_decision(record)
        if op in ("store_insight", "insight"):
            return await self.store_insight(record)
        if op == "store_pipeline_state":
            return await self.store_pipeline_state(record)
        if op == "store_blueprint":
            return await self.store_blueprint(record)
        if op == "store_legal":
            return await self.store_legal(record)
        if op in ("store_operator_state", "operator_state"):
            return await self.store_operator_state(record)
        if op == "store_scout_cache":
            return await self.store_scout_cache(record)
        # Generic fallback — write to decisions
        return await self.store_decision(record)

    async def read(self, operation: str, params: dict) -> list[dict]:
        op = operation.lower()
        if op in ("get_messages", "messages"):
            return await self.get_messages(
                params.get("operator_id", ""),
                limit=params.get("limit", 20),
            )
        if op in ("get_decisions", "decisions"):
            return await self.get_decisions(params.get("project_id", ""))
        if op in ("get_insights", "insights"):
            return await self.get_insights(
                params.get("operator_id", ""),
                limit=params.get("limit", 8),
            )
        if op in ("get_pipeline_state", "pipeline_state"):
            return await self.get_pipeline_state(
                params.get("project_id", ""),
                stage=params.get("stage", ""),
            )
        return []
