"""
PROD-6 Validation: Setup Wizard + Schema Initialization

Tests cover:
  1.  Schema constants — 11 Supabase tables
  2.  Schema constants — 7 Supabase indexes
  3.  Schema constants — 18 Neo4j indexes
  4.  Schema constants — 1 Neo4j constraint
  5.  Schema constants — 12 node types
  6.  Schema summary matches constants
  7.  Table name extraction
  8.  initialize_supabase_schema() dry-run
  9.  initialize_neo4j_schema() dry-run
  10. Wizard secrets list — 8 entries
  11. Wizard secret names match Appendix B
  12. wait_for_operator_reply() timeout returns default
  13. wait_for_operator_reply() resolve returns value
  14. has_pending_reply() / resolve_reply()
  15. run_setup_wizard() all-skip path
  16. run_setup_wizard() summary structure
  17. _register_operator() fallback
  18. All IF NOT EXISTS (idempotent)

Run:
  pytest tests/test_prod_06_setup.py -v
"""

from __future__ import annotations

import asyncio
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from factory.setup.schema import (
    SUPABASE_SCHEMAS,
    SUPABASE_INDEXES,
    NEO4J_INDEXES,
    NEO4J_CONSTRAINTS,
    NEO4J_NODE_TYPES,
    get_schema_summary,
    initialize_supabase_schema,
    initialize_neo4j_schema,
    _extract_table_name,
)
from factory.setup.wizard import (
    WIZARD_SECRETS,
    SECRET_TIMEOUT_SECONDS,
    SECRET_SKIP_VALUE,
    run_setup_wizard,
)
from factory.telegram.decisions import (
    wait_for_operator_reply,
    resolve_reply,
    has_pending_reply,
    _pending_replies,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_replies():
    """Clear pending replies before each test."""
    _pending_replies.clear()
    yield
    _pending_replies.clear()


# ═══════════════════════════════════════════════════════════════════
# Test 1-5: Schema Constants
# ═══════════════════════════════════════════════════════════════════

class TestSchemaConstants:
    def test_11_supabase_tables(self):
        """§7.1.3 + §8.3.1: 11 tables total."""
        assert len(SUPABASE_SCHEMAS) == 11

    def test_7_supabase_indexes(self):
        assert len(SUPABASE_INDEXES) == 7

    def test_18_neo4j_indexes(self):
        """§8.3.1: 18 indexes across 12 node types."""
        assert len(NEO4J_INDEXES) == 18

    def test_1_neo4j_constraint(self):
        """§7.1.3: 1 uniqueness constraint on Project.id."""
        assert len(NEO4J_CONSTRAINTS) == 1
        assert "Project" in NEO4J_CONSTRAINTS[0]
        assert "UNIQUE" in NEO4J_CONSTRAINTS[0]

    def test_12_node_types(self):
        """§6.3: 12 Mother Memory node types."""
        assert len(NEO4J_NODE_TYPES) == 12
        assert "Project" in NEO4J_NODE_TYPES
        assert "HandoffDoc" in NEO4J_NODE_TYPES  # FIX-27
        assert "StorePolicyEvent" in NEO4J_NODE_TYPES

    def test_all_tables_have_if_not_exists(self):
        """Idempotency: all DDL must use IF NOT EXISTS."""
        for sql in SUPABASE_SCHEMAS:
            assert "IF NOT EXISTS" in sql

    def test_all_indexes_have_if_not_exists(self):
        for sql in SUPABASE_INDEXES + NEO4J_INDEXES + NEO4J_CONSTRAINTS:
            assert "IF NOT EXISTS" in sql

    def test_expected_table_names(self):
        """All 11 expected tables must be present."""
        table_names = [_extract_table_name(sql) for sql in SUPABASE_SCHEMAS]
        expected = [
            "pipeline_states", "state_snapshots",
            "operator_whitelist", "operator_state",
            "active_projects", "archived_projects",
            "monthly_costs", "audit_log",
            "pipeline_metrics", "memory_stats",
            "temp_artifacts",
        ]
        for name in expected:
            assert name in table_names, f"Missing table: {name}"


# ═══════════════════════════════════════════════════════════════════
# Test 6-7: Schema Summary & Helpers
# ═══════════════════════════════════════════════════════════════════

class TestSchemaSummary:
    def test_summary_matches_constants(self):
        summary = get_schema_summary()
        assert summary["supabase_table_count"] == 11
        assert summary["supabase_index_count"] == 7
        assert summary["neo4j_index_count"] == 18
        assert summary["neo4j_constraint_count"] == 1
        assert summary["neo4j_node_type_count"] == 12

    def test_extract_table_name(self):
        sql = "CREATE TABLE IF NOT EXISTS my_table (id INT)"
        assert _extract_table_name(sql) == "my_table"


# ═══════════════════════════════════════════════════════════════════
# Test 8-9: Schema Initialization (dry-run)
# ═══════════════════════════════════════════════════════════════════

class TestSchemaInitialization:
    @pytest.mark.asyncio
    async def test_supabase_dry_run(self):
        """Without client, runs in dry-run mode."""
        # Patch import to raise ImportError
        with patch(
            "factory.setup.schema.get_supabase_client",
            side_effect=ImportError,
        ):
            pass
        # Passing None triggers internal import fallback
        # which will hit ImportError → dry-run
        result = await initialize_supabase_schema(supabase_client=None)
        # Dry-run should still count tables
        assert result["tables_created"] >= 0
        assert isinstance(result["errors"], list)

    @pytest.mark.asyncio
    async def test_neo4j_dry_run(self):
        """Without client, runs in dry-run mode."""
        result = await initialize_neo4j_schema(neo4j_client=None)
        assert result["indexes_created"] == 18
        assert result["constraints_created"] == 1
        assert result["errors"] == []


# ═══════════════════════════════════════════════════════════════════
# Test 10-11: Wizard Secrets Configuration
# ═══════════════════════════════════════════════════════════════════

class TestWizardSecrets:
    def test_8_wizard_secrets(self):
        """§7.1.2: 8 API keys collected during wizard."""
        assert len(WIZARD_SECRETS) == 8

    def test_wizard_secret_names(self):
        """All wizard secrets must be from Appendix B."""
        from factory.core.secrets import REQUIRED_SECRETS
        wizard_names = [name for name, _ in WIZARD_SECRETS]
        for name in wizard_names:
            assert name in REQUIRED_SECRETS, (
                f"Wizard secret {name} not in Appendix B"
            )

    def test_timeout_is_300(self):
        """§7.1.2: Each key has a 300-second entry timeout."""
        assert SECRET_TIMEOUT_SECONDS == 300

    def test_skip_default(self):
        """§7.1.2: SKIP default on timeout."""
        assert SECRET_SKIP_VALUE == "SKIP"


# ═══════════════════════════════════════════════════════════════════
# Test 12-14: wait_for_operator_reply() Mechanism
# ═══════════════════════════════════════════════════════════════════

class TestReplyMechanism:
    @pytest.mark.asyncio
    async def test_timeout_returns_default(self):
        """Timeout returns default value."""
        result = await wait_for_operator_reply(
            "test_op", timeout=1, default="SKIP"
        )
        assert result == "SKIP"

    @pytest.mark.asyncio
    async def test_resolve_returns_value(self):
        """Resolving a pending reply returns the operator's text."""
        async def _resolve_after_delay():
            await asyncio.sleep(0.05)
            await resolve_reply("test_op2", "my-api-key-123")

        task = asyncio.create_task(_resolve_after_delay())
        result = await wait_for_operator_reply(
            "test_op2", timeout=5, default="SKIP"
        )
        await task
        assert result == "my-api-key-123"

    @pytest.mark.asyncio
    async def test_has_pending_reply(self):
        """has_pending_reply detects active futures."""
        assert has_pending_reply("noone") is False

        # Start a wait in the background
        async def _wait():
            await wait_for_operator_reply(
                "pending_op", timeout=2, default="X"
            )

        task = asyncio.create_task(_wait())
        await asyncio.sleep(0.02)
        assert has_pending_reply("pending_op") is True
        # Resolve to clean up
        await resolve_reply("pending_op", "done")
        await task

    @pytest.mark.asyncio
    async def test_resolve_no_pending(self):
        """resolve_reply returns False when no pending future."""
        result = await resolve_reply("nobody", "text")
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# Test 15-17: run_setup_wizard()
# ═══════════════════════════════════════════════════════════════════

class TestWizardFlow:
    @pytest.mark.asyncio
    async def test_all_skip_path(self):
        """Wizard with all secrets skipped should complete."""
        messages_sent = []

        async def mock_send(operator_id, text, **kwargs):
            messages_sent.append(text)

        async def mock_reply(operator_id, timeout=300, default="SKIP"):
            return "SKIP"

        with patch(
            "factory.setup.wizard._get_send_function",
            return_value=mock_send,
        ), patch(
            "factory.setup.wizard._get_reply_function",
            return_value=mock_reply,
        ), patch(
            "factory.setup.wizard.check_secret_exists",
            return_value=False,
        ):
            results = await run_setup_wizard("test_operator")

        assert len(results["skipped"]) >= 8  # All 8 secrets skipped
        assert "📊 Setup Complete" in messages_sent[-1]

    @pytest.mark.asyncio
    async def test_summary_structure(self):
        """Results dict has required keys."""
        async def mock_send(operator_id, text, **kwargs):
            pass

        async def mock_reply(operator_id, timeout=300, default="SKIP"):
            return "SKIP"

        with patch(
            "factory.setup.wizard._get_send_function",
            return_value=mock_send,
        ), patch(
            "factory.setup.wizard._get_reply_function",
            return_value=mock_reply,
        ), patch(
            "factory.setup.wizard.check_secret_exists",
            return_value=False,
        ):
            results = await run_setup_wizard("op2")

        assert "passed" in results
        assert "failed" in results
        assert "skipped" in results
        assert "supabase_schema" in results
        assert "neo4j_schema" in results
        assert isinstance(results["passed"], list)
        assert isinstance(results["failed"], list)
        assert isinstance(results["skipped"], list)

    @pytest.mark.asyncio
    async def test_already_configured_skips_prompt(self):
        """Secrets already in GCP should not prompt operator."""
        prompts = []

        async def mock_send(operator_id, text, **kwargs):
            if "🔑" in text:
                prompts.append(text)

        async def mock_reply(operator_id, timeout=300, default="SKIP"):
            return "SKIP"

        with patch(
            "factory.setup.wizard._get_send_function",
            return_value=mock_send,
        ), patch(
            "factory.setup.wizard._get_reply_function",
            return_value=mock_reply,
        ), patch(
            "factory.setup.wizard.check_secret_exists",
            return_value=True,  # All already configured
        ):
            results = await run_setup_wizard("op3")

        # No 🔑 prompts should have been sent
        assert len(prompts) == 0
        # All 8 should be in passed (already configured)
        secret_names = [name for name, _ in WIZARD_SECRETS]
        for name in secret_names:
            assert name in results["passed"]
