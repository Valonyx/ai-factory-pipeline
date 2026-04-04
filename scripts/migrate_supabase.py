"""
AI Factory Pipeline v5.6 — Supabase Schema Migration

Implements:
  - §5.6 Session Schema (6 tables)
  - §8.3.1 Supabase Schema (pipeline_states, state_snapshots, audit_log,
    pipeline_metrics, memory_stats, temp_artifacts)

Idempotent — all CREATE TABLE use IF NOT EXISTS.
Run: python -m scripts.migrate_supabase

Spec Authority: v5.6 §5.6, §8.3.1
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("factory.migrate.supabase")

# ═══════════════════════════════════════════════════════════════════
# Schema Definitions
# ═══════════════════════════════════════════════════════════════════

SUPABASE_SCHEMAS = [
    # ── §8.3.1 Pipeline core ──
    """CREATE TABLE IF NOT EXISTS pipeline_states (
        id              BIGSERIAL PRIMARY KEY,
        project_id      TEXT UNIQUE NOT NULL,
        operator_id     TEXT NOT NULL,
        current_stage   TEXT NOT NULL DEFAULT 'IDLE',
        state_json      JSONB NOT NULL DEFAULT '{}',
        snapshot_id     INTEGER DEFAULT 0,
        selected_stack  TEXT DEFAULT 'flutterflow',
        execution_mode  TEXT DEFAULT 'cloud',
        autonomy_mode   TEXT DEFAULT 'autopilot',
        project_metadata JSONB DEFAULT '{}',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )""",

    """CREATE TABLE IF NOT EXISTS state_snapshots (
        id              BIGSERIAL PRIMARY KEY,
        project_id      TEXT NOT NULL,
        snapshot_id     INTEGER NOT NULL,
        stage           TEXT NOT NULL,
        state_json      JSONB NOT NULL,
        git_commit_hash TEXT,
        checksum        TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(project_id, snapshot_id)
    )""",

    # ── §5.6 Operator management ──
    """CREATE TABLE IF NOT EXISTS operator_whitelist (
        telegram_id     TEXT PRIMARY KEY,
        name            TEXT,
        invite_code     TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        preferences     JSONB DEFAULT '{}'
    )""",

    """CREATE TABLE IF NOT EXISTS operator_state (
        telegram_id     TEXT PRIMARY KEY,
        state           TEXT,
        context         JSONB DEFAULT '{}',
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )""",

    """CREATE TABLE IF NOT EXISTS active_projects (
        operator_id     TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL,
        current_stage   TEXT,
        state_json      JSONB NOT NULL,
        started_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    )""",

    """CREATE TABLE IF NOT EXISTS archived_projects (
        id              BIGSERIAL PRIMARY KEY,
        project_id      TEXT UNIQUE,
        operator_id     TEXT,
        final_stage     TEXT,
        total_cost_usd  REAL,
        state_json      JSONB NOT NULL,
        archived_at     TIMESTAMPTZ DEFAULT NOW()
    )""",

    """CREATE TABLE IF NOT EXISTS monthly_costs (
        id              BIGSERIAL PRIMARY KEY,
        operator_id     TEXT,
        month           TEXT,
        project_count   INT DEFAULT 0,
        ai_total_usd    REAL DEFAULT 0,
        infra_total_usd REAL DEFAULT 0,
        UNIQUE(operator_id, month)
    )""",

    # ── §8.3.1 Observability ──
    """CREATE TABLE IF NOT EXISTS audit_log (
        id              BIGSERIAL PRIMARY KEY,
        operator_id     TEXT,
        project_id      TEXT,
        action          TEXT NOT NULL,
        details         JSONB DEFAULT '{}',
        timestamp       TIMESTAMPTZ DEFAULT NOW()
    )""",

    """CREATE TABLE IF NOT EXISTS pipeline_metrics (
        id              BIGSERIAL PRIMARY KEY,
        project_id      TEXT,
        stack           TEXT,
        completed       BOOLEAN,
        total_cost_usd  REAL,
        duration_seconds INTEGER,
        war_room_count  INTEGER DEFAULT 0,
        timestamp       TIMESTAMPTZ DEFAULT NOW()
    )""",

    """CREATE TABLE IF NOT EXISTS memory_stats (
        id              BIGSERIAL PRIMARY KEY,
        stats           JSONB NOT NULL,
        collected_at    TIMESTAMPTZ DEFAULT NOW()
    )""",

    # ── §7.5 [C3] Temp artifacts (Janitor cleanup target) ──
    """CREATE TABLE IF NOT EXISTS temp_artifacts (
        id              BIGSERIAL PRIMARY KEY,
        project_id      TEXT NOT NULL,
        object_key      TEXT NOT NULL,
        bucket          TEXT NOT NULL DEFAULT 'build-artifacts',
        size_bytes      BIGINT DEFAULT 0,
        expires_at      TIMESTAMPTZ NOT NULL,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    )""",
]

# Indexes for performance
SUPABASE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_snapshots_project ON state_snapshots(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_created ON state_snapshots(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_log(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_metrics_project ON pipeline_metrics(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_temp_artifacts_expires ON temp_artifacts(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_monthly_costs_month ON monthly_costs(month)",
]


# ═══════════════════════════════════════════════════════════════════
# Migration Runner
# ═══════════════════════════════════════════════════════════════════


async def run_supabase_migration(supabase_client=None) -> dict:
    """Execute all Supabase schema migrations.

    Returns: {"tables_created": int, "indexes_created": int, "errors": []}
    """
    result = {"tables_created": 0, "indexes_created": 0, "errors": []}

    if not supabase_client:
        logger.info("No Supabase client — running in dry-run mode")
        for sql in SUPABASE_SCHEMAS:
            table_name = sql.split("IF NOT EXISTS")[1].split("(")[0].strip()
            logger.info(f"  [DRY-RUN] Would create: {table_name}")
            result["tables_created"] += 1
        for sql in SUPABASE_INDEXES:
            idx_name = sql.split("IF NOT EXISTS")[1].split(" ON")[0].strip()
            logger.info(f"  [DRY-RUN] Would create index: {idx_name}")
            result["indexes_created"] += 1
        return result

    # Create tables
    for sql in SUPABASE_SCHEMAS:
        try:
            await supabase_client.rpc("exec_sql", {"query": sql}).execute()
            result["tables_created"] += 1
        except Exception as e:
            result["errors"].append(str(e)[:200])
            logger.error(f"Table creation error: {e}")

    # Create indexes
    for sql in SUPABASE_INDEXES:
        try:
            await supabase_client.rpc("exec_sql", {"query": sql}).execute()
            result["indexes_created"] += 1
        except Exception as e:
            result["errors"].append(str(e)[:200])

    logger.info(
        f"Supabase migration: {result['tables_created']} tables, "
        f"{result['indexes_created']} indexes, "
        f"{len(result['errors'])} errors"
    )
    return result


def get_schema_summary() -> dict:
    """Return summary of expected Supabase schema."""
    tables = []
    for sql in SUPABASE_SCHEMAS:
        name = sql.split("IF NOT EXISTS")[1].split("(")[0].strip()
        tables.append(name)
    return {
        "tables": tables,
        "table_count": len(tables),
        "index_count": len(SUPABASE_INDEXES),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("AI Factory Pipeline v5.6 — Supabase Migration")
    print("=" * 50)
    result = asyncio.run(run_supabase_migration())
    print(f"\nTables: {result['tables_created']}")
    print(f"Indexes: {result['indexes_created']}")
    if result["errors"]:
        print(f"Errors: {len(result['errors'])}")