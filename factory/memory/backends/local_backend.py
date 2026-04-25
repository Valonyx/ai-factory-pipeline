"""
AI Factory Pipeline v5.8 — Local Memory Backend

Writes every memory record to the local filesystem under
  {project_root}/local_memory/

Directory structure:
  local_memory/
    messages/        — Telegram conversation turns (one JSON file per message)
    decisions/       — Pipeline stage decisions
    insights/        — Long-term operator facts and preferences
    projects/
      {project_id}/
        blueprint/   — S2 blueprint outputs
        legal/       — S1 legal classification outputs
        pipeline/    — Stage-by-stage pipeline state snapshots
        artifacts/   — Generated file references

Always available (no API key, no network). Acts as the ultimate fallback
and as a human-readable audit trail.

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
        # Walk up from this file to find the project root (contains factory/)
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
            for sub in ("messages", "decisions", "insights", "projects"):
                (root / sub).mkdir(parents=True, exist_ok=True)
            logger.info(f"[local-memory] root: {root}")
            return True
        except Exception as e:
            logger.warning(f"[local-memory] setup failed: {e}")
            return False

    # ── Write operations ──────────────────────────────────────────────

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

    async def store_pipeline_state(self, project_id: str, stage: str, state_dict: dict) -> bool:
        """Save a pipeline stage snapshot under projects/{pid}/pipeline/."""
        try:
            ts = int(time.time() * 1000)
            pid = _safe_filename(project_id)
            stg = _safe_filename(stage)
            _write(
                _root() / "projects" / pid / "pipeline" / f"{stg}_{ts}.json",
                {"project_id": project_id, "stage": stage, "ts": ts, "state": state_dict},
            )
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_pipeline_state: {e}")
            return False

    async def store_blueprint(self, project_id: str, blueprint: dict) -> bool:
        """Save blueprint output under projects/{pid}/blueprint/."""
        try:
            pid = _safe_filename(project_id)
            ts = int(time.time() * 1000)
            _write(
                _root() / "projects" / pid / "blueprint" / f"blueprint_{ts}.json",
                blueprint,
            )
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_blueprint: {e}")
            return False

    async def store_legal(self, project_id: str, legal: dict) -> bool:
        """Save legal dossier output under projects/{pid}/legal/."""
        try:
            pid = _safe_filename(project_id)
            ts = int(time.time() * 1000)
            _write(
                _root() / "projects" / pid / "legal" / f"legal_{ts}.json",
                legal,
            )
            return True
        except Exception as e:
            logger.debug(f"[local-memory] store_legal: {e}")
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
            return filtered[-(limit + offset) :][-limit:] if limit else filtered
        except Exception:
            return []

    async def get_decisions(self, project_id: str) -> list[dict]:
        try:
            pid = _safe_filename(project_id)
            return _read_all(_root() / "decisions" / pid)
        except Exception:
            return []

    async def get_insights(self, operator_id: str) -> list[dict]:
        try:
            op = _safe_filename(operator_id)
            records = _read_all(_root() / "insights")
            return [r for r in records if r.get("operator_id") == operator_id]
        except Exception:
            return []

    # ── MemoryBackend contract ─────────────────────────────────────────

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
            return await self.store_pipeline_state(
                record.get("project_id", ""),
                record.get("stage", "unknown"),
                record,
            )
        if op == "store_blueprint":
            return await self.store_blueprint(record.get("project_id", ""), record)
        if op == "store_legal":
            return await self.store_legal(record.get("project_id", ""), record)
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
            return await self.get_insights(params.get("operator_id", ""))
        return []
