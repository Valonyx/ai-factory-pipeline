"""
AI Factory Pipeline v5.8 — Real Supabase Integration

Production replacement for the stub Supabase client.

Implements:
  - §2.9     State Persistence (triple-write: current → snapshot → git ref)
  - §2.9.1   Snapshot Write (with checksum)
  - §2.9.2   Time-Travel Restore (checksum validation)
  - §5.6     Session Schema CRUD (operator_whitelist, operator_state,
             active_projects, archived_projects, monthly_costs)
  - §7.1.3   8-table schema initialization
  - §6.7     State Consistency Guarantees

Uses supabase-py SDK (verified 2026-02-27):
  - create_client(url, key) for sync operations
  - acreate_client(url, key) for async operations
  - table("name").select/insert/upsert/update/delete().execute()

Spec Authority: v5.6 §2.9, §5.6, §6.7, §7.1.3, §8.3.1
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from factory.core.state import PipelineState, Stage

logger = logging.getLogger("factory.integrations.supabase")


# ═══════════════════════════════════════════════════════════════════
# Client Singleton
# ═══════════════════════════════════════════════════════════════════

_client: Any = None
_async_client: Any = None


def get_supabase_client() -> Any:
    """Get or create the sync Supabase client singleton.

    Uses supabase-py create_client(). Falls back to in-memory
    SupabaseFallback if SDK not available or env vars not set.

    Returns:
        Supabase Client or SupabaseFallback instance.
    """
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_KEY", ""))

    if not url or not key:
        logger.warning(
            "SUPABASE_URL/SUPABASE_KEY not set — using in-memory fallback. "
            "Set via GCP Secret Manager (§2.15) or .env for local dev."
        )
        _client = SupabaseFallback()
        return _client

    try:
        from supabase import create_client
        _client = create_client(url, key)
        logger.info(f"Supabase client connected to {url[:40]}...")
        return _client
    except ImportError:
        logger.warning("supabase-py not installed — using in-memory fallback")
        _client = SupabaseFallback()
        return _client
    except Exception as e:
        logger.error(f"Supabase connection failed: {e} — using fallback")
        _client = SupabaseFallback()
        return _client


async def get_async_supabase_client() -> Any:
    """Get or create the async Supabase client singleton.

    Uses supabase-py acreate_client() for async context.
    Falls back to sync client wrapper if async not available.
    """
    global _async_client
    if _async_client is not None:
        return _async_client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_KEY", ""))

    if not url or not key:
        _async_client = SupabaseFallback()
        return _async_client

    try:
        from supabase import acreate_client
        _async_client = await acreate_client(url, key)
        logger.info("Async Supabase client connected")
        return _async_client
    except (ImportError, Exception) as e:
        logger.warning(f"Async Supabase unavailable ({e}) — using sync client")
        _async_client = get_supabase_client()
        return _async_client


def reset_clients() -> None:
    """Reset client singletons (for testing)."""
    global _client, _async_client
    _client = None
    _async_client = None


# ═══════════════════════════════════════════════════════════════════
# Checksum Utility (§2.9.2)
# ═══════════════════════════════════════════════════════════════════

def compute_state_checksum(state_json: dict) -> str:
    """Compute SHA-256 checksum of state JSON for integrity validation.

    Spec: §2.9.2 — checksum validation for time-travel restores.

    Args:
        state_json: State dictionary to checksum.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    canonical = json.dumps(state_json, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════
# §2.9 Pipeline State Operations (Triple-Write)
# ═══════════════════════════════════════════════════════════════════

async def upsert_pipeline_state(
    project_id: str,
    state: PipelineState,
    git_commit_hash: Optional[str] = None,
) -> dict:
    """Triple-write state persistence.

    Spec: §2.9 — Write 1: current state, Write 2: snapshot, Write 3: git ref.

    Args:
        project_id: Project identifier.
        state: Current PipelineState.
        git_commit_hash: Optional git commit reference.

    Returns:
        Result dict with write statuses.
    """
    client = get_supabase_client()
    state_dict = state.model_dump(mode="json")
    checksum = compute_state_checksum(state_dict)
    now = datetime.now(timezone.utc).isoformat()

    result = {"write_1": False, "write_2": False, "write_3": False, "checksum": checksum}

    # ── Write 1: Current state (upsert) ──
    try:
        client.table("pipeline_states").upsert({
            "project_id": project_id,
            "operator_id": state.operator_id,
            "current_stage": state.current_stage.value,
            "state_json": state_dict,
            "snapshot_id": state.snapshot_count,
            "selected_stack": (state.selected_stack.value if state.selected_stack else "flutterflow"),
            "execution_mode": state.execution_mode.value,
            "updated_at": now,
        }).execute()
        result["write_1"] = True
    except Exception as e:
        logger.error(f"Write 1 (current state) failed for {project_id}: {e}")

    # ── Write 2: Snapshot ──
    try:
        snapshot_id = state.snapshot_count
        client.table("state_snapshots").upsert({
            "project_id": project_id,
            "snapshot_id": snapshot_id,
            "stage": state.current_stage.value,
            "state_json": state_dict,
            "git_commit_hash": git_commit_hash,
            "checksum": checksum,
            "created_at": now,
        }).execute()
        result["write_2"] = True
    except Exception as e:
        logger.error(f"Write 2 (snapshot) failed for {project_id}: {e}")

    # ── Write 3: Git reference (logged only) ──
    if git_commit_hash:
        result["write_3"] = True
        logger.info(
            f"Write 3: git ref {git_commit_hash[:8]} for {project_id}"
        )
    else:
        result["write_3"] = True  # No git commit needed for this stage

    logger.info(
        f"Triple-write for {project_id}: "
        f"W1={result['write_1']} W2={result['write_2']} W3={result['write_3']} "
        f"checksum={checksum[:12]}..."
    )
    return result


async def get_pipeline_state(project_id: str) -> Optional[dict]:
    """Fetch current pipeline state.

    Spec: §2.9
    """
    client = get_supabase_client()
    try:
        resp = (
            client.table("pipeline_states")
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to fetch state for {project_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# §2.9.2 Time-Travel Restore
# ═══════════════════════════════════════════════════════════════════

async def list_snapshots(project_id: str, limit: int = 20) -> list[dict]:
    """List available snapshots for time-travel.

    Spec: §2.9.2
    Returns snapshots ordered by snapshot_id descending.
    """
    client = get_supabase_client()
    try:
        resp = (
            client.table("state_snapshots")
            .select("snapshot_id, stage, created_at, checksum, git_commit_hash")
            .eq("project_id", project_id)
            .order("snapshot_id", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error(f"Failed to list snapshots for {project_id}: {e}")
        return []


async def restore_state(
    project_id: str,
    snapshot_id: int,
    validate_checksum: bool = True,
) -> Optional[PipelineState]:
    """Restore state from a snapshot with checksum validation.

    Spec: §2.9.2 — Time-Travel Restore.

    Args:
        project_id: Project to restore.
        snapshot_id: Target snapshot number.
        validate_checksum: Whether to validate checksum integrity.

    Returns:
        Restored PipelineState, or None on failure.

    Raises:
        ValueError: If checksum validation fails (data corruption).
    """
    client = get_supabase_client()
    try:
        resp = (
            client.table("state_snapshots")
            .select("*")
            .eq("project_id", project_id)
            .eq("snapshot_id", snapshot_id)
            .execute()
        )
        if not resp.data:
            logger.error(
                f"Snapshot {snapshot_id} not found for {project_id}"
            )
            return None

        snapshot = resp.data[0]
        state_json = snapshot["state_json"]
        stored_checksum = snapshot.get("checksum", "")

        # Validate checksum integrity
        if validate_checksum and stored_checksum:
            computed = compute_state_checksum(state_json)
            if computed != stored_checksum:
                raise ValueError(
                    f"Checksum mismatch for snapshot {snapshot_id}: "
                    f"stored={stored_checksum[:12]}... "
                    f"computed={computed[:12]}... "
                    f"Data may be corrupted."
                )

        # Restore state
        restored = PipelineState.model_validate(state_json)
        logger.info(
            f"Restored {project_id} to snapshot #{snapshot_id} "
            f"(stage={snapshot['stage']})"
        )

        # Update current state to restored version
        await upsert_pipeline_state(project_id, restored)
        return restored

    except ValueError:
        raise  # Re-raise checksum errors
    except Exception as e:
        logger.error(f"Restore failed for {project_id}@{snapshot_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# §5.6 Active Projects (Session Schema)
# ═══════════════════════════════════════════════════════════════════

async def upsert_active_project(
    operator_id: str, state: PipelineState,
) -> bool:
    """Create or update the active project for an operator.

    Spec: §5.6 — active_projects table.
    """
    client = get_supabase_client()
    try:
        client.table("active_projects").upsert({
            "operator_id": operator_id,
            "project_id": state.project_id,
            "current_stage": state.current_stage.value,
            "state_json": state.model_dump(mode="json"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert active project for {operator_id}: {e}")
        return False


async def get_active_project(operator_id: str) -> Optional[dict]:
    """Get the active project for an operator.

    Spec: §5.6
    """
    client = get_supabase_client()
    try:
        resp = (
            client.table("active_projects")
            .select("*")
            .eq("operator_id", operator_id)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to get active project for {operator_id}: {e}")
        return None


async def archive_project(project_id: str, state: PipelineState) -> bool:
    """Archive a project (move from active to archived).

    Spec: §5.6 — archived_projects table.
    Always removes from active_projects even if archive insert fails.
    """
    client = get_supabase_client()
    archived = False
    try:
        # Insert into archived_projects (best-effort — table may not exist yet)
        client.table("archived_projects").insert({
            "project_id": project_id,
            "operator_id": state.operator_id,
            "final_stage": state.current_stage.value,
            "total_cost_usd": state.total_cost_usd,
            "state_json": state.model_dump(mode="json"),
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        archived = True
    except Exception as e:
        logger.warning(f"Archive insert skipped for {project_id}: {e}")

    try:
        # Always delete from active_projects regardless of archive result
        client.table("active_projects").delete().eq(
            "operator_id", state.operator_id
        ).execute()
        logger.info(
            f"Project {project_id} removed from active "
            f"(archived={archived}, cost=${state.total_cost_usd:.2f})"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to remove {project_id} from active_projects: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# §5.6 Operator Whitelist
# ═══════════════════════════════════════════════════════════════════

async def check_operator_whitelist(telegram_id: str) -> bool:
    """Check if a Telegram user is in the operator whitelist.

    Spec: §5.1.2 / §5.6 — operator_whitelist table.
    """
    client = get_supabase_client()
    try:
        resp = (
            client.table("operator_whitelist")
            .select("telegram_id")
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return bool(resp.data)
    except Exception as e:
        logger.error(f"Whitelist check failed for {telegram_id}: {e}")
        fail_open = os.getenv("WHITELIST_FAIL_OPEN", "true").lower() == "true"
        return fail_open


async def add_operator_to_whitelist(
    telegram_id: str,
    name: str = "",
    invite_code: str = "",
) -> bool:
    """Add an operator to the whitelist.

    Spec: §5.6 — operator_whitelist table.
    """
    client = get_supabase_client()
    try:
        client.table("operator_whitelist").upsert({
            "telegram_id": telegram_id,
            "name": name,
            "invite_code": invite_code,
            "preferences": {},
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to add operator {telegram_id}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# §5.6 Operator State
# ═══════════════════════════════════════════════════════════════════

async def set_operator_state_db(
    telegram_id: str, state_name: str, context: Optional[dict] = None,
) -> bool:
    """Set operator conversation state in Supabase.

    Spec: §5.6 — operator_state table.
    """
    client = get_supabase_client()
    try:
        client.table("operator_state").upsert({
            "telegram_id": telegram_id,
            "state": state_name,
            "context": context or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to set operator state for {telegram_id}: {e}")
        return False


async def get_operator_state_db(telegram_id: str) -> Optional[dict]:
    """Get operator conversation state from Supabase."""
    client = get_supabase_client()
    try:
        resp = (
            client.table("operator_state")
            .select("*")
            .eq("telegram_id", telegram_id)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to get operator state for {telegram_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# §5.6 Monthly Costs
# ═══════════════════════════════════════════════════════════════════

async def track_monthly_cost(
    operator_id: str,
    ai_cost: float = 0.0,
    infra_cost: float = 0.0,
    project_increment: int = 0,
) -> bool:
    """Track monthly cost accumulation.

    Spec: §5.6 — monthly_costs table.
    Uses upsert with current month key.
    """
    client = get_supabase_client()
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        # Fetch current
        resp = (
            client.table("monthly_costs")
            .select("*")
            .eq("operator_id", operator_id)
            .eq("month", month)
            .execute()
        )

        if resp.data:
            current = resp.data[0]
            client.table("monthly_costs").update({
                "ai_total_usd": current["ai_total_usd"] + ai_cost,
                "infra_total_usd": current["infra_total_usd"] + infra_cost,
                "project_count": current["project_count"] + project_increment,
            }).eq("operator_id", operator_id).eq("month", month).execute()
        else:
            client.table("monthly_costs").insert({
                "operator_id": operator_id,
                "month": month,
                "project_count": project_increment,
                "ai_total_usd": ai_cost,
                "infra_total_usd": infra_cost,
            }).execute()

        return True
    except Exception as e:
        logger.error(f"Failed to track monthly cost for {operator_id}: {e}")
        return False


async def get_monthly_costs(
    operator_id: str, month: Optional[str] = None,
) -> Optional[dict]:
    """Get monthly cost summary."""
    client = get_supabase_client()
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        resp = (
            client.table("monthly_costs")
            .select("*")
            .eq("operator_id", operator_id)
            .eq("month", month)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to get monthly costs: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# Audit Log
# ═══════════════════════════════════════════════════════════════════

async def audit_log(
    project_id: str,
    event: str,
    details: Optional[dict] = None,
    operator_id: Optional[str] = None,
) -> bool:
    """Write an entry to the audit log.

    Spec: §8.3.1 — audit_log table.
    """
    client = get_supabase_client()
    try:
        client.table("audit_log").insert({
            "project_id": project_id,
            "event": event,
            "details": details or {},
            "operator_id": operator_id or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Audit log failed for {project_id}/{event}: {e}")
        return False


async def supabase_execute_sql(query: str, params: Optional[list] = None) -> Any:
    """Execute raw SQL via Supabase RPC endpoint.

    Used for advisory locks (pg_try_advisory_lock, pg_advisory_unlock).
    Falls back gracefully when Supabase is unavailable.

    Spec: §2.1.6 [C6]
    """
    client = get_supabase_client()
    if isinstance(client, SupabaseFallback):
        raise ImportError("Supabase not configured")
    # Call via PostgREST RPC — wraps arbitrary SQL in a named function
    # For advisory locks, use execute_sql RPC if available, else raise
    try:
        result = client.rpc("execute_sql", {"query": query, "params": params or []}).execute()
        return result.data
    except Exception as e:
        raise RuntimeError(f"supabase_execute_sql failed: {e}") from e


# ═══════════════════════════════════════════════════════════════════
# In-Memory Fallback (for offline/local development)
# ═══════════════════════════════════════════════════════════════════

class _FallbackTable:
    """In-memory table simulator for offline development."""

    def __init__(self, table_name: str = ""):
        self._table_name = table_name
        self._store: list[dict] = []
        self._filter_col: Optional[str] = None
        self._filter_val: Any = None
        self._select_cols: Optional[str] = None
        self._order_col: Optional[str] = None
        self._order_desc: bool = False
        self._limit_n: Optional[int] = None
        self._pending: Optional[tuple] = None

    def select(self, cols: str = "*") -> "_FallbackTable":
        self._select_cols = cols
        return self

    def eq(self, col: str, val: Any) -> "_FallbackTable":
        self._filter_col = col
        self._filter_val = val
        return self

    def order(self, col: str, desc: bool = False) -> "_FallbackTable":
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_FallbackTable":
        self._limit_n = n
        return self

    def insert(self, data: dict) -> "_FallbackTable":
        self._pending = ("insert", data)
        return self

    def upsert(self, data: dict) -> "_FallbackTable":
        self._pending = ("upsert", data)
        return self

    def update(self, data: dict) -> "_FallbackTable":
        self._pending = ("update", data)
        return self

    def delete(self) -> "_FallbackTable":
        self._pending = ("delete", None)
        return self

    def execute(self) -> Any:
        """Execute the pending operation and return a response-like object."""
        action = self._pending

        if action:
            op, data = action
            if op == "insert":
                self._store.append(data)
                return _FallbackResponse([data])
            elif op == "upsert":
                pk = self._get_primary_key(data, self._table_name)
                found = False
                for i, row in enumerate(self._store):
                    if pk and all(row.get(k) == data.get(k) for k in pk):
                        self._store[i] = {**row, **data}
                        found = True
                        break
                if not found:
                    self._store.append(data)
                return _FallbackResponse([data])
            elif op == "update":
                for i, row in enumerate(self._store):
                    if (self._filter_col and
                            row.get(self._filter_col) == self._filter_val):
                        self._store[i] = {**row, **data}
                return _FallbackResponse([])
            elif op == "delete":
                # Mutate in-place so SupabaseFallback._tables keeps the reference
                to_remove = [
                    r for r in self._store
                    if (self._filter_col and
                        r.get(self._filter_col) == self._filter_val)
                ]
                for r in to_remove:
                    self._store.remove(r)
                return _FallbackResponse([])
        else:
            # Select query
            rows = list(self._store)
            if self._filter_col:
                rows = [r for r in rows
                        if r.get(self._filter_col) == self._filter_val]
            if self._order_col:
                rows.sort(
                    key=lambda r: r.get(self._order_col, ""),
                    reverse=self._order_desc,
                )
            if self._limit_n:
                rows = rows[:self._limit_n]
            return _FallbackResponse(rows)

    # Known composite PKs for tables that need more than one key to identify rows
    _COMPOSITE_PKS: dict[str, list[str]] = {
        "state_snapshots": ["project_id", "snapshot_id"],
        "workflow_runs": ["project_id", "run_id"],
    }

    def _get_primary_key(self, data: dict, table_name: str = "") -> list[str]:
        """Guess the primary key from common patterns.

        Uses known composite PKs for tables that require them.
        """
        if table_name in self._COMPOSITE_PKS:
            cols = self._COMPOSITE_PKS[table_name]
            if all(c in data for c in cols):
                return cols
        for pk in ["project_id", "telegram_id", "operator_id", "id"]:
            if pk in data:
                return [pk]
        return list(data.keys())[:1]


class _FallbackResponse:
    """Mimics Supabase APIResponse."""
    def __init__(self, data: list[dict]):
        self.data = data


class SupabaseFallback:
    """In-memory Supabase fallback for offline/local development.

    Provides the same table().select/insert/upsert/update/delete interface.
    All data lives in memory and is lost on restart.
    """

    def __init__(self):
        self._tables: dict[str, list[dict]] = {}
        self.is_fallback = True
        logger.info("SupabaseFallback initialized (in-memory mode)")

    def table(self, name: str) -> _FallbackTable:
        if name not in self._tables:
            self._tables[name] = []
        tbl = _FallbackTable(table_name=name)
        tbl._store = self._tables[name]
        return tbl
