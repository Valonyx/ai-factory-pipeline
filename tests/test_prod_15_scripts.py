"""
PROD-15 Validation: Database Migrations + Scripts

Tests cover:
  Supabase Migration (4 tests):
    1.  SUPABASE_SCHEMAS has 11 tables
    2.  SUPABASE_INDEXES has 7 indexes
    3.  get_schema_summary lists all expected tables
    4.  run_supabase_migration dry-run creates 11+7

  Neo4j Migration (4 tests):
    5.  NEO4J_INDEXES has 18 indexes
    6.  NEO4J_CONSTRAINTS has 1 constraint
    7.  get_neo4j_summary lists 12 node types
    8.  run_neo4j_migration dry-run creates 18+1

  Janitor Agent (4 tests):
    9.  JANITOR_SCHEDULE has 4 tasks
    10. janitor_clean_artifacts dry-run returns valid result
    11. janitor_prune_snapshots dry-run returns valid result
    12. janitor_run_all runs 4 tasks

  Setup Secrets (2 tests):
    13. SECRET_DEFINITIONS has 9 entries
    14. validate_secrets returns valid structure

  v3.6 Migration (2 tests):
    15. MIGRATION_STEPS has 5 steps
    16. migrate_v36_to_v54 dry-run completes 5/5

Run:
  pytest tests/test_prod_15_scripts.py -v
"""

from __future__ import annotations

import pytest
import asyncio

from scripts.migrate_supabase import (
    SUPABASE_SCHEMAS,
    SUPABASE_INDEXES,
    run_supabase_migration,
    get_schema_summary,
)
from scripts.migrate_neo4j import (
    NEO4J_INDEXES,
    NEO4J_CONSTRAINTS,
    run_neo4j_migration,
    get_neo4j_summary,
)
from scripts.janitor import (
    JANITOR_SCHEDULE,
    SNAPSHOT_RETENTION_COUNT,
    janitor_clean_artifacts,
    janitor_prune_snapshots,
    janitor_collect_memory_stats,
    janitor_update_graveyard,
    janitor_run_all,
)
from scripts.setup_secrets import (
    SECRET_DEFINITIONS,
    validate_secrets,
)
from scripts.migrate_v36_to_v54 import (
    MIGRATION_STEPS,
    migrate_v36_to_v54,
)


# ═══════════════════════════════════════════════════════════════════
# Tests 1-4: Supabase Migration
# ═══════════════════════════════════════════════════════════════════

class TestSupabaseMigration:
    def test_11_tables(self):
        """SUPABASE_SCHEMAS has at least 11 tables (15 after exa/analytics additions)."""
        assert len(SUPABASE_SCHEMAS) >= 11

    def test_7_indexes(self):
        """SUPABASE_INDEXES has at least 7 indexes (12 after exa/analytics additions)."""
        assert len(SUPABASE_INDEXES) >= 7

    def test_schema_summary(self):
        """get_schema_summary lists expected tables."""
        summary = get_schema_summary()
        assert summary["table_count"] >= 11
        assert summary["index_count"] >= 7
        assert "pipeline_states" in summary["tables"]
        assert "state_snapshots" in summary["tables"]
        assert "operator_whitelist" in summary["tables"]
        assert "decision_queue" in summary["tables"]
        assert "audit_log" in summary["tables"]
        assert "monthly_costs" in summary["tables"]
        assert "pipeline_metrics" in summary["tables"]
        assert "memory_stats" in summary["tables"]
        assert "temp_artifacts" in summary["tables"]

    @pytest.mark.asyncio
    async def test_dry_run(self):
        """Dry-run creates ≥11 tables + ≥7 indexes (schema expanded beyond original spec)."""
        result = await run_supabase_migration()
        assert result["tables_created"] >= 11
        assert result["indexes_created"] >= 7
        assert result["errors"] == []


# ═══════════════════════════════════════════════════════════════════
# Tests 5-8: Neo4j Migration
# ═══════════════════════════════════════════════════════════════════

class TestNeo4jMigration:
    def test_18_indexes(self):
        """NEO4J_INDEXES has 18 indexes."""
        assert len(NEO4J_INDEXES) == 18

    def test_1_constraint(self):
        """NEO4J_CONSTRAINTS has 1 constraint."""
        assert len(NEO4J_CONSTRAINTS) == 1
        assert "Project" in NEO4J_CONSTRAINTS[0]

    def test_12_node_types(self):
        """get_neo4j_summary lists 12 node types."""
        summary = get_neo4j_summary()
        assert len(summary["node_types"]) == 12
        for nt in [
            "StackPattern", "Component", "DesignDNA",
            "HandoffDoc", "Graveyard", "WarRoomEvent",
            "Project",
        ]:
            assert nt in summary["node_types"], (
                f"Missing: {nt}"
            )

    @pytest.mark.asyncio
    async def test_dry_run(self):
        """Dry-run creates 18 indexes + 1 constraint."""
        result = await run_neo4j_migration()
        assert result["indexes_created"] == 18
        assert result["constraints_created"] == 1
        assert result["errors"] == []


# ═══════════════════════════════════════════════════════════════════
# Tests 9-12: Janitor Agent
# ═══════════════════════════════════════════════════════════════════

class TestJanitor:
    def test_schedule(self):
        """JANITOR_SCHEDULE has 4 tasks."""
        assert len(JANITOR_SCHEDULE) == 4
        assert "janitor_clean" in JANITOR_SCHEDULE
        assert "snapshot_prune" in JANITOR_SCHEDULE
        assert "memory_stats" in JANITOR_SCHEDULE
        assert "graveyard_update" in JANITOR_SCHEDULE
        assert SNAPSHOT_RETENTION_COUNT == 50

    @pytest.mark.asyncio
    async def test_clean_dry_run(self):
        """janitor_clean_artifacts dry-run."""
        result = await janitor_clean_artifacts()
        assert "expired_found" in result
        assert "deleted" in result

    @pytest.mark.asyncio
    async def test_prune_dry_run(self):
        """janitor_prune_snapshots dry-run."""
        result = await janitor_prune_snapshots()
        assert "projects_checked" in result

    @pytest.mark.asyncio
    async def test_run_all(self):
        """janitor_run_all runs 4 tasks."""
        result = await janitor_run_all()
        assert "clean" in result
        assert "prune" in result
        assert "stats" in result
        assert "graveyard" in result


# ═══════════════════════════════════════════════════════════════════
# Tests 13-14: Setup Secrets
# ═══════════════════════════════════════════════════════════════════

class TestSetupSecrets:
    def test_9_definitions(self):
        """SECRET_DEFINITIONS has 9 entries."""
        assert len(SECRET_DEFINITIONS) == 9
        names = [s["name"] for s in SECRET_DEFINITIONS]
        assert "ANTHROPIC_API_KEY" in names
        assert "TELEGRAM_BOT_TOKEN" in names
        assert "GCP_PROJECT_ID" in names

    def test_validate_structure(self):
        """validate_secrets returns valid structure."""
        result = validate_secrets()
        assert "valid" in result
        assert "present" in result
        assert "missing" in result
        assert "warnings" in result
        assert isinstance(result["present"], list)
        assert isinstance(result["missing"], list)


# ═══════════════════════════════════════════════════════════════════
# Tests 15-16: v3.6 Migration
# ═══════════════════════════════════════════════════════════════════

class TestV36Migration:
    def test_5_steps(self):
        """MIGRATION_STEPS has 5 steps."""
        assert len(MIGRATION_STEPS) == 5
        names = [s["name"] for s in MIGRATION_STEPS]
        assert "Rename legacy tables" in names
        assert "Create new schema" in names
        assert "Migrate pipeline states" in names

    @pytest.mark.asyncio
    async def test_dry_run(self):
        """Dry-run completes 5/5 steps."""
        result = await migrate_v36_to_v54(dry_run=True)
        assert result["steps_completed"] == 5
        assert result["total_steps"] == 5
        assert result["errors"] == []
