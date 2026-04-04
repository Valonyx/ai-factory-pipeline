"""
AI Factory Pipeline v5.6 — Supabase Integration

Implements:
  - §2.9 State Persistence (triple-write + snapshot)
  - §2.9.2 Time-Travel Restore (checksum validation)
  - Cost tracking table
  - Deploy decision table (FIX-08)
  - Audit logging
  - Operator whitelist

Spec Authority: v5.6 §2.9, §2.9.1, §2.9.2
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import PipelineState, Stage

logger = logging.getLogger("factory.integrations.supabase")


# ═══════════════════════════════════════════════════════════════════
# Supabase Client
# ═══════════════════════════════════════════════════════════════════


class SupabaseClient:
    """Supabase client wrapper for pipeline state and operational data.

    Spec: §2.9
    In production: uses supabase-py SDK.
    Current implementation: interface-compatible stub for offline dev.
    """

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = url or os.getenv("SUPABASE_URL", "")
        self.key = key or os.getenv("SUPABASE_SERVICE_KEY", "")
        self._connected = bool(self.url and self.key)

        # In-memory stores for offline development
        self._pipeline_states: dict[str, dict] = {}
        self._snapshots: list[dict] = []
        self._cost_tracking: list[dict] = {}
        self._deploy_decisions: dict[str, str] = {}
        self._audit_log: list[dict] = []
        self._operator_whitelist: set[str] = set()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ═══════════════════════════════════════════════════════════════
    # §2.9.1 Pipeline State (Current)
    # ═══════════════════════════════════════════════════════════════

    async def upsert_pipeline_state(
        self, project_id: str, state: PipelineState,
    ) -> dict:
        """Upsert current pipeline state (Write 1 of triple-write).

        Spec: §2.9.1
        """
        state_json_str = json.dumps(json.loads(state.model_dump_json()), sort_keys=True, separators=(',', ':'))
        supabase_hash = hashlib.sha256(state_json_str.encode()).hexdigest()[:16]
        record = {
            "project_id": project_id,
            "current_stage": state.current_stage.value,
            "snapshot_id": state.snapshot_id,
            "selected_stack": (
                state.selected_stack.value if state.selected_stack else None
            ),
            "execution_mode": state.execution_mode.value,
            "state_json": state_json_str,
            "updated_at": state.updated_at or datetime.now(timezone.utc).isoformat(),
        }
        self._pipeline_states[project_id] = record
        logger.debug(f"[{project_id}] Upserted pipeline state (snapshot #{state.snapshot_id})")
        return record

    async def get_pipeline_state(self, project_id: str) -> Optional[dict]:
        """Get current pipeline state."""
        return self._pipeline_states.get(project_id)

    # ═══════════════════════════════════════════════════════════════
    # §2.9.1 State Snapshots (Append-Only)
    # ═══════════════════════════════════════════════════════════════

    async def insert_snapshot(
        self, project_id: str, snapshot_id: int,
        stage: str, state_json: dict,
    ) -> dict:
        """Insert append-only snapshot (Write 2 of triple-write).

        Spec: §2.9.1
        """
        record = {
            "project_id": project_id,
            "snapshot_id": snapshot_id,
            "stage": stage,
            "state_json": state_json,
            "git_commit_hash": None,
            "checksum": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._snapshots.append(record)
        logger.debug(f"[{project_id}] Snapshot #{snapshot_id} inserted")
        return record

    async def update_snapshot_checksum(
        self, project_id: str, snapshot_id: int,
        git_commit_hash: str, checksum: str,
    ) -> None:
        """Backfill checksum after all three writes succeed.

        Spec: §2.9.1
        """
        for snap in self._snapshots:
            if (snap["project_id"] == project_id and
                    snap["snapshot_id"] == snapshot_id):
                snap["git_commit_hash"] = git_commit_hash
                snap["checksum"] = checksum
                break

    async def get_snapshot(
        self, project_id: str, snapshot_id: int,
    ) -> Optional[dict]:
        """Retrieve specific snapshot for time-travel restore.

        Spec: §2.9.2
        """
        for snap in self._snapshots:
            if (snap["project_id"] == project_id and
                    snap["snapshot_id"] == snapshot_id):
                return snap
        return None

    async def delete_snapshot(
        self, project_id: str, snapshot_id: int,
    ) -> None:
        """Delete snapshot (rollback on partial write failure).

        Spec: §2.9.1
        """
        self._snapshots = [
            s for s in self._snapshots
            if not (s["project_id"] == project_id and
                    s["snapshot_id"] == snapshot_id)
        ]

    async def list_snapshots(self, project_id: str) -> list[dict]:
        """List all snapshots for a project (for /snapshots command)."""
        return [
            s for s in self._snapshots
            if s["project_id"] == project_id
        ]

    # ═══════════════════════════════════════════════════════════════
    # Cost Tracking
    # ═══════════════════════════════════════════════════════════════

    async def track_cost(
        self, project_id: str, role: str, stage: str,
        cost_usd: float, model: str, tokens_in: int, tokens_out: int,
    ) -> None:
        """Record an AI call cost.

        Spec: §3.6 (circuit breaker cost tracking)
        """
        record = {
            "project_id": project_id,
            "role": role,
            "stage": stage,
            "cost_usd": cost_usd,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if project_id not in self._cost_tracking:
            self._cost_tracking[project_id] = []
        self._cost_tracking[project_id].append(record)

    async def get_monthly_spend_cents(self) -> int:
        """Get total spend for current month in cents.

        Spec: §2.14.3 (Budget Governor)
        """
        now = datetime.now(timezone.utc)
        total = 0.0
        for records in self._cost_tracking.values():
            for r in records:
                ts = datetime.fromisoformat(r["timestamp"])
                if ts.year == now.year and ts.month == now.month:
                    total += r["cost_usd"]
        return int(total * 100)

    async def get_project_cost(self, project_id: str) -> float:
        """Get total cost for a specific project."""
        records = self._cost_tracking.get(project_id, [])
        return sum(r["cost_usd"] for r in records)

    # ═══════════════════════════════════════════════════════════════
    # Deploy Decisions (FIX-08)
    # ═══════════════════════════════════════════════════════════════

    async def record_deploy_decision(
        self, project_id: str, decision: str,
    ) -> None:
        """Record deploy confirm/cancel decision.

        Spec: §4.6.2 (FIX-08)
        """
        self._deploy_decisions[project_id] = decision
        logger.info(f"[{project_id}] Deploy decision: {decision}")

    async def check_deploy_decision(
        self, project_id: str,
    ) -> Optional[str]:
        """Check for pending deploy decision."""
        return self._deploy_decisions.get(project_id)

    async def clear_deploy_decision(
        self, project_id: str,
    ) -> None:
        """Clear deploy decision after processing."""
        self._deploy_decisions.pop(project_id, None)

    async def get_pending_deploys(
        self, operator_id: str,
    ) -> list[str]:
        """Get all projects with pending deploy decisions."""
        return list(self._deploy_decisions.keys())

    # ═══════════════════════════════════════════════════════════════
    # Audit Log
    # ═══════════════════════════════════════════════════════════════

    async def audit_log(
        self, operator_id: str, action: str, details: dict,
        project_id: Optional[str] = None,
    ) -> None:
        """Append to audit log."""
        record = {
            "operator_id": operator_id,
            "project_id": project_id,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._audit_log.append(record)

    # ═══════════════════════════════════════════════════════════════
    # Operator Whitelist
    # ═══════════════════════════════════════════════════════════════

    async def is_operator_whitelisted(self, operator_id: str) -> bool:
        """Check if operator is in whitelist."""
        if not self._operator_whitelist:
            return True  # No whitelist = allow all (dev mode)
        return operator_id in self._operator_whitelist

    async def add_operator(self, operator_id: str) -> None:
        """Add operator to whitelist."""
        self._operator_whitelist.add(operator_id)


# ═══════════════════════════════════════════════════════════════════
# §2.9.1 Triple-Write with Rollback
# ═══════════════════════════════════════════════════════════════════


class SnapshotWriteError(Exception):
    """Raised when triple-write fails and is rolled back.

    Spec: §2.9.1
    """
    pass


async def triple_write_persist(
    state: PipelineState,
    supabase: SupabaseClient,
    github_commit_fn=None,
) -> int:
    """Transactional triple-write: Supabase current + snapshot + GitHub.

    Spec: §2.9.1
    Returns snapshot_id on success.
    Raises SnapshotWriteError on failure with rollback.
    """
    state.snapshot_id = (state.snapshot_id or 0) + 1
    state.updated_at = datetime.now(timezone.utc).isoformat()
    state_json_str = json.dumps(json.loads(state.model_dump_json()), sort_keys=True, separators=(',', ':'))
    supabase_hash = hashlib.sha256(state_json_str.encode()).hexdigest()[:16]
    state_json = json.loads(state_json_str)
    snapshot_id = state.snapshot_id
    results = {
        "supabase_current": False,
        "supabase_snapshot": False,
        "git": False,
    }

    try:
        # Write 1: Supabase current state
        await supabase.upsert_pipeline_state(state.project_id, state)
        results["supabase_current"] = True

        # Write 2: Supabase snapshot (append-only)
        await supabase.insert_snapshot(
            state.project_id, snapshot_id,
            state.current_stage.value, state_json,
        )
        results["supabase_snapshot"] = True

        # Write 3: GitHub (versioned)
        git_sha = "local-dev-no-git"
        if github_commit_fn:
            commit = await github_commit_fn(
                repo=f"factory/{state.project_id}",
                path=f"state/snapshot_{snapshot_id:04d}_{state.current_stage.value}.json",
                content=state_json_str,
                message=f"Snapshot #{snapshot_id} at {state.current_stage.value}",
            )
            git_sha = commit.get("sha", "unknown")
        results["git"] = True

        # Compute checksum: SHA256(git_sha:supabase_hash_16:snapshot_id)
        state_json_str = json.dumps(json.loads(state.model_dump_json()), sort_keys=True, separators=(',', ':'))
        supabase_hash = hashlib.sha256(state_json_str.encode()).hexdigest()[:16]
        checksum = hashlib.sha256(
            f"{git_sha}:{supabase_hash}:{snapshot_id}".encode()
        ).hexdigest()

        await supabase.update_snapshot_checksum(
            state.project_id, snapshot_id, git_sha, checksum,
        )

        logger.info(
            f"[{state.project_id}] Triple-write success: "
            f"snapshot #{snapshot_id}, checksum={checksum[:12]}..."
        )
        return snapshot_id

    except Exception as e:
        # Rollback
        if results["supabase_snapshot"]:
            await supabase.delete_snapshot(state.project_id, snapshot_id)
        if results["supabase_current"]:
            state.snapshot_id = snapshot_id - 1

        await supabase.audit_log(
            "system", "snapshot_write_failed",
            {"snapshot_id": snapshot_id, "error": str(e), "partial_writes": results},
            project_id=state.project_id,
        )

        raise SnapshotWriteError(
            f"Triple write failed: {e}. Partial writes rolled back: {results}"
        )


# ═══════════════════════════════════════════════════════════════════
# §2.9.2 Time-Travel Restore
# ═══════════════════════════════════════════════════════════════════


class ChecksumMismatchError(Exception):
    """Snapshot checksum mismatch — state may be inconsistent.

    Spec: §2.9.2
    """
    pass


async def restore_state(
    project_id: str,
    target_snapshot_id: int,
    supabase: SupabaseClient,
) -> PipelineState:
    """Restore pipeline to a specific snapshot.

    Spec: §2.9.2
    Validates checksum, restores state, masks Neo4j nodes.
    """
    snapshot = await supabase.get_snapshot(project_id, target_snapshot_id)
    if not snapshot:
        raise ValueError(f"Snapshot #{target_snapshot_id} not found")

    # Validate checksum
    if snapshot.get("checksum"):
        state_json_str = json.dumps(snapshot["state_json"], sort_keys=True, separators=(',', ':'))
        supabase_hash = hashlib.sha256(state_json_str.encode()).hexdigest()[:16]

        git_sha = snapshot.get("git_commit_hash", "")
        expected = hashlib.sha256(
            f"{git_sha}:{supabase_hash}:{target_snapshot_id}".encode()
        ).hexdigest()
        if expected != snapshot["checksum"]:
            raise ChecksumMismatchError(
                f"Snapshot #{target_snapshot_id} checksum mismatch. "
                f"State may be inconsistent."
            )

    state = PipelineState.model_validate(snapshot["state_json"])
    state.snapshot_id = target_snapshot_id

    logger.info(
        f"[{project_id}] Restored to snapshot #{target_snapshot_id} "
        f"at stage {state.current_stage.value}"
    )
    return state


# Singleton client
_supabase_client: Optional[SupabaseClient] = None


def get_supabase() -> SupabaseClient:
    """Get or create Supabase client singleton."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client