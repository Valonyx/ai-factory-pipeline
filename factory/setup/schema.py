"""
AI Factory Pipeline v5.6 — Schema Initialization

Implements §7.1.3: Database schema setup.

Supabase tables (11):
  1. operator_whitelist
  2. active_projects
  3. pipeline_states
  4. state_snapshots
  5. monthly_costs
  6. audit_log
  7. temp_artifacts
  8. build_results
  9. compliance_results
 10. operator_sessions
 11. war_room_incidents

Neo4j indexes (18) per §2.10.1:
  - StackPattern, Component, DesignDNA, BugPattern,
    APIContract, UserStory, TechDebt, LegalConstraint,
    PostSnapshot, HandoffDoc + relationship indexes

Spec Authority: v5.6 §7.1.3, §2.10.1
"""

from __future__ import annotations

import logging
from typing import Any

from factory.integrations.supabase import get_supabase_client, SupabaseFallback
from factory.integrations.neo4j import neo4j_run

logger = logging.getLogger("factory.setup.schema")


# ═══════════════════════════════════════════════════════════════════
# Supabase DDL (11 tables)
# ═══════════════════════════════════════════════════════════════════

SUPABASE_TABLES: list[dict] = [
    {
        "name": "operator_whitelist",
        "ddl": """
            CREATE TABLE IF NOT EXISTS operator_whitelist (
                telegram_id TEXT PRIMARY KEY,
                added_at TIMESTAMPTZ DEFAULT NOW(),
                added_by TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                permissions JSONB DEFAULT '{}'::jsonb
            );
        """,
    },
    {
        "name": "active_projects",
        "ddl": """
            CREATE TABLE IF NOT EXISTS active_projects (
                operator_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                state_json JSONB NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_active_projects_project_id
                ON active_projects(project_id);
        """,
    },
    {
        "name": "pipeline_states",
        "ddl": """
            CREATE TABLE IF NOT EXISTS pipeline_states (
                project_id TEXT PRIMARY KEY,
                state_json JSONB NOT NULL,
                checksum TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
    },
    {
        "name": "state_snapshots",
        "ddl": """
            CREATE TABLE IF NOT EXISTS state_snapshots (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                snapshot_number INTEGER NOT NULL,
                stage TEXT NOT NULL,
                state_json JSONB NOT NULL,
                checksum TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_project_num
                ON state_snapshots(project_id, snapshot_number);
            CREATE INDEX IF NOT EXISTS idx_snapshots_project_id
                ON state_snapshots(project_id);
        """,
    },
    {
        "name": "monthly_costs",
        "ddl": """
            CREATE TABLE IF NOT EXISTS monthly_costs (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                operator_id TEXT NOT NULL,
                month TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT NOT NULL,
                token_cost NUMERIC(10, 6) DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(project_id, month, role)
            );
            CREATE INDEX IF NOT EXISTS idx_monthly_costs_operator
                ON monthly_costs(operator_id, month);
        """,
    },
    {
        "name": "audit_log",
        "ddl": """
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                operator_id TEXT,
                event_type TEXT NOT NULL,
                stage TEXT,
                details JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_audit_log_project_id
                ON audit_log(project_id);
            CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
                ON audit_log(created_at);
        """,
    },
    {
        "name": "temp_artifacts",
        "ddl": """
            CREATE TABLE IF NOT EXISTS temp_artifacts (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                object_key TEXT NOT NULL,
                bucket TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                size_bytes BIGINT DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_temp_artifacts_expires
                ON temp_artifacts(expires_at);
            CREATE INDEX IF NOT EXISTS idx_temp_artifacts_project
                ON temp_artifacts(project_id);
        """,
    },
    {
        "name": "build_results",
        "ddl": """
            CREATE TABLE IF NOT EXISTS build_results (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                artifacts JSONB DEFAULT '[]'::jsonb,
                error_log TEXT,
                duration_seconds NUMERIC(10, 2),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_build_results_project
                ON build_results(project_id);
        """,
    },
    {
        "name": "compliance_results",
        "ddl": """
            CREATE TABLE IF NOT EXISTS compliance_results (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                check_type TEXT NOT NULL,
                passed BOOLEAN NOT NULL,
                confidence NUMERIC(4, 3),
                details JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_compliance_project
                ON compliance_results(project_id);
        """,
    },
    {
        "name": "operator_sessions",
        "ddl": """
            CREATE TABLE IF NOT EXISTS operator_sessions (
                telegram_id TEXT PRIMARY KEY,
                state TEXT,
                preferences JSONB DEFAULT '{}'::jsonb,
                last_active TIMESTAMPTZ DEFAULT NOW()
            );
        """,
    },
    {
        "name": "war_room_incidents",
        "ddl": """
            CREATE TABLE IF NOT EXISTS war_room_incidents (
                id BIGSERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                level TEXT NOT NULL,
                trigger TEXT NOT NULL,
                message TEXT NOT NULL,
                resolved BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                resolved_at TIMESTAMPTZ
            );
            CREATE INDEX IF NOT EXISTS idx_war_room_project
                ON war_room_incidents(project_id);
            CREATE INDEX IF NOT EXISTS idx_war_room_resolved
                ON war_room_incidents(resolved);
        """,
    },
]


# ═══════════════════════════════════════════════════════════════════
# Neo4j Indexes (18) — §2.10.1
# ═══════════════════════════════════════════════════════════════════

NEO4J_INDEXES: list[dict] = [
    # Node indexes
    {"name": "idx_stack_pattern_id",   "cypher": "CREATE INDEX idx_stack_pattern_id IF NOT EXISTS FOR (n:StackPattern) ON (n.id)"},
    {"name": "idx_stack_pattern_stack","cypher": "CREATE INDEX idx_stack_pattern_stack IF NOT EXISTS FOR (n:StackPattern) ON (n.stack)"},
    {"name": "idx_component_id",       "cypher": "CREATE INDEX idx_component_id IF NOT EXISTS FOR (n:Component) ON (n.id)"},
    {"name": "idx_component_type",     "cypher": "CREATE INDEX idx_component_type IF NOT EXISTS FOR (n:Component) ON (n.type)"},
    {"name": "idx_design_dna_id",      "cypher": "CREATE INDEX idx_design_dna_id IF NOT EXISTS FOR (n:DesignDNA) ON (n.id)"},
    {"name": "idx_bug_pattern_id",     "cypher": "CREATE INDEX idx_bug_pattern_id IF NOT EXISTS FOR (n:BugPattern) ON (n.id)"},
    {"name": "idx_bug_pattern_stage",  "cypher": "CREATE INDEX idx_bug_pattern_stage IF NOT EXISTS FOR (n:BugPattern) ON (n.stage)"},
    {"name": "idx_api_contract_id",    "cypher": "CREATE INDEX idx_api_contract_id IF NOT EXISTS FOR (n:APIContract) ON (n.id)"},
    {"name": "idx_user_story_id",      "cypher": "CREATE INDEX idx_user_story_id IF NOT EXISTS FOR (n:UserStory) ON (n.id)"},
    {"name": "idx_tech_debt_id",       "cypher": "CREATE INDEX idx_tech_debt_id IF NOT EXISTS FOR (n:TechDebt) ON (n.id)"},
    {"name": "idx_legal_constraint_id","cypher": "CREATE INDEX idx_legal_constraint_id IF NOT EXISTS FOR (n:LegalConstraint) ON (n.id)"},
    {"name": "idx_legal_constraint_body","cypher": "CREATE INDEX idx_legal_constraint_body IF NOT EXISTS FOR (n:LegalConstraint) ON (n.regulatory_body)"},
    {"name": "idx_post_snapshot_id",   "cypher": "CREATE INDEX idx_post_snapshot_id IF NOT EXISTS FOR (n:PostSnapshot) ON (n.id)"},
    {"name": "idx_post_snapshot_project","cypher": "CREATE INDEX idx_post_snapshot_project IF NOT EXISTS FOR (n:PostSnapshot) ON (n.project_id)"},
    {"name": "idx_handoff_doc_id",     "cypher": "CREATE INDEX idx_handoff_doc_id IF NOT EXISTS FOR (n:HandoffDoc) ON (n.id)"},
    {"name": "idx_handoff_doc_project","cypher": "CREATE INDEX idx_handoff_doc_project IF NOT EXISTS FOR (n:HandoffDoc) ON (n.project_id)"},
    # Relationship property indexes
    {"name": "idx_rel_used_at",        "cypher": "CREATE INDEX idx_rel_used_at IF NOT EXISTS FOR ()-[r:USED_IN]-() ON (r.used_at)"},
    {"name": "idx_rel_solved_at",      "cypher": "CREATE INDEX idx_rel_solved_at IF NOT EXISTS FOR ()-[r:SOLVES]-() ON (r.solved_at)"},
]


# ═══════════════════════════════════════════════════════════════════
# Initialization Runner
# ═══════════════════════════════════════════════════════════════════


async def initialize_schema() -> dict[str, Any]:
    """Initialize all database schemas.

    Spec: §7.1.3

    Creates Supabase tables and Neo4j indexes if they don't already exist.
    Safe to re-run (all DDL uses IF NOT EXISTS).

    Returns:
        {"supabase_tables": int, "neo4j_indexes": int, "errors": list}
    """
    result: dict[str, Any] = {
        "supabase_tables": 0,
        "neo4j_indexes": 0,
        "errors": [],
    }

    # ── Supabase tables ──────────────────────────────────────────────
    try:
        client = get_supabase_client()

        if isinstance(client, SupabaseFallback):
            logger.warning("[Schema] Supabase not configured — skipping table creation")
        else:
            for table_spec in SUPABASE_TABLES:
                try:
                    # Use Supabase RPC to execute DDL
                    client.rpc("execute_sql", {
                        "query": table_spec["ddl"].strip(),
                        "params": [],
                    }).execute()
                    result["supabase_tables"] += 1
                    logger.debug(f"[Schema] Table {table_spec['name']}: OK")
                except Exception as e:
                    # Table likely already exists — not an error
                    err_str = str(e).lower()
                    if "already exists" in err_str or "duplicate" in err_str:
                        result["supabase_tables"] += 1
                    else:
                        logger.warning(f"[Schema] Table {table_spec['name']}: {e}")
                        result["errors"].append(f"supabase:{table_spec['name']}: {e}")

    except ImportError as e:
        result["errors"].append(f"supabase:import: {e}")

    # ── Neo4j indexes ────────────────────────────────────────────────
    try:
        for idx in NEO4J_INDEXES:
            try:
                await neo4j_run(idx["cypher"])
                result["neo4j_indexes"] += 1
                logger.debug(f"[Schema] Neo4j index {idx['name']}: OK")
            except Exception as e:
                err_str = str(e).lower()
                if "already exists" in err_str or "equivalent index" in err_str:
                    result["neo4j_indexes"] += 1
                else:
                    logger.warning(f"[Schema] Neo4j {idx['name']}: {e}")
                    result["errors"].append(f"neo4j:{idx['name']}: {e}")

    except ImportError as e:
        result["errors"].append(f"neo4j:import: {e}")
    except Exception as e:
        # neo4j_run raises ImportError when not configured
        logger.info(f"[Schema] Neo4j not configured: {e}")

    logger.info(
        f"[Schema] Init done: {result['supabase_tables']} tables, "
        f"{result['neo4j_indexes']} Neo4j indexes, "
        f"{len(result['errors'])} errors"
    )
    return result
