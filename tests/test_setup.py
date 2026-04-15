"""
AI Factory Pipeline v5.8 — Setup Wizard + Schema Tests (PROD-15)

Tests:
  - Setup wizard step collection and service verification
  - Schema initialization (11 tables, 18 Neo4j indexes)
  - Service verifiers (dry-run / mocked)
  - Operator whitelist (Supabase fallback)
  - Supabase execute_sql (SupabaseFallback path)
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════════
# Setup Wizard Tests
# ═══════════════════════════════════════════════════════════════════


class TestSetupWizard:
    @pytest.mark.asyncio
    async def test_wizard_skip_all(self):
        """Wizard with all SKIP responses completes gracefully."""
        from factory.setup.wizard import run_setup_wizard

        messages: list[str] = []

        async def capture(text: str):
            messages.append(text)

        with patch(
            "factory.setup.wizard.wait_for_operator_reply",
            new_callable=AsyncMock,
            return_value="SKIP",
        ):
            results = await run_setup_wizard("op_001", capture)

        assert "anthropic" in results
        assert "perplexity" in results
        assert "supabase" in results
        assert "neo4j" in results
        assert "github" in results
        # All skipped
        assert all(r.get("skipped") for r in results.values())
        assert len(messages) > 0  # At least intro message sent

    @pytest.mark.asyncio
    async def test_wizard_single_key_stored(self):
        """Wizard stores a key and attempts verification."""
        from factory.setup.wizard import _collect_single_key

        messages: list[str] = []

        async def capture(text: str):
            messages.append(text)

        mock_verify_result = {
            "service": "GitHub",
            "status": "connected",
            "latency_ms": 42.0,
            "detail": "Token valid",
        }

        with (
            patch("factory.setup.wizard.wait_for_operator_reply",
                  new_callable=AsyncMock, return_value="ghp_test_token"),
            patch("factory.setup.wizard.verify_github",
                  new_callable=AsyncMock, return_value=mock_verify_result),
            patch("factory.setup.wizard.store_secret"),
        ):
            result = await _collect_single_key(
                operator_id="op_001",
                send_message=capture,
                prompt="Enter GitHub token",
                secret_name="GITHUB_TOKEN",
                verifier_name="github",
            )

        assert result["stored"] is True
        assert result["verified"] is True
        assert result["skipped"] is False

    @pytest.mark.asyncio
    async def test_wizard_verification_failure_stored_but_unverified(self):
        """Key is stored even when verification fails."""
        from factory.setup.wizard import _collect_single_key

        async def capture(text):
            pass

        with (
            patch("factory.setup.wizard.wait_for_operator_reply",
                  new_callable=AsyncMock, return_value="sk-ant-badkey"),
            patch("factory.setup.wizard.verify_anthropic",
                  new_callable=AsyncMock, side_effect=ConnectionError("bad key")),
            patch("factory.setup.wizard.store_secret"),
        ):
            result = await _collect_single_key(
                operator_id="op_001",
                send_message=capture,
                prompt="Enter Anthropic key",
                secret_name="ANTHROPIC_API_KEY",
                verifier_name="anthropic",
            )

        assert result["stored"] is True
        assert result["verified"] is False
        assert result["skipped"] is False


# ═══════════════════════════════════════════════════════════════════
# Schema Initialization Tests
# ═══════════════════════════════════════════════════════════════════


class TestSchemaInit:
    def test_schema_constants(self):
        """Schema module has 11 tables and 18 Neo4j indexes."""
        from factory.setup.schema import SUPABASE_TABLES, NEO4J_INDEXES

        assert len(SUPABASE_TABLES) == 11
        assert len(NEO4J_INDEXES) == 18

    def test_table_names(self):
        """All expected table names are present."""
        from factory.setup.schema import SUPABASE_TABLES

        names = {t["name"] for t in SUPABASE_TABLES}
        required = {
            "operator_whitelist", "active_projects", "pipeline_states",
            "state_snapshots", "monthly_costs", "audit_log",
            "temp_artifacts", "build_results", "compliance_results",
            "operator_sessions", "war_room_incidents",
        }
        assert required == names

    def test_neo4j_index_names(self):
        """All Neo4j indexes have unique names."""
        from factory.setup.schema import NEO4J_INDEXES

        names = [idx["name"] for idx in NEO4J_INDEXES]
        assert len(names) == len(set(names)), "Duplicate Neo4j index names"

    def test_all_tables_have_ddl(self):
        """Every table spec has a non-empty DDL statement."""
        from factory.setup.schema import SUPABASE_TABLES

        for t in SUPABASE_TABLES:
            assert t.get("ddl", "").strip(), f"{t['name']} has empty DDL"
            assert "CREATE TABLE IF NOT EXISTS" in t["ddl"]

    @pytest.mark.asyncio
    async def test_initialize_schema_fallback(self):
        """Schema init with SupabaseFallback logs warning and continues."""
        from factory.setup.schema import initialize_schema
        from factory.integrations.supabase import SupabaseFallback

        with (
            patch("factory.setup.schema.get_supabase_client",
                  return_value=SupabaseFallback()),
            patch("factory.setup.schema.neo4j_run",
                  new_callable=AsyncMock, return_value=[]),
        ):
            result = await initialize_schema()

        # Supabase was skipped (fallback), Neo4j ran
        assert result["supabase_tables"] == 0
        assert result["neo4j_indexes"] == 18
        assert isinstance(result["errors"], list)

    @pytest.mark.asyncio
    async def test_initialize_schema_neo4j_error_graceful(self):
        """Neo4j index errors are collected, not raised."""
        from factory.setup.schema import initialize_schema
        from factory.integrations.supabase import SupabaseFallback

        call_count = 0

        async def flaky_neo4j(query, params=None):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                raise RuntimeError("Neo4j transient error")
            return []

        with (
            patch("factory.setup.schema.get_supabase_client",
                  return_value=SupabaseFallback()),
            patch("factory.setup.schema.neo4j_run", side_effect=flaky_neo4j),
        ):
            result = await initialize_schema()

        # Some succeeded, some errored — none raised
        assert result["neo4j_indexes"] + len(result["errors"]) == 18


# ═══════════════════════════════════════════════════════════════════
# Service Verifier Tests
# ═══════════════════════════════════════════════════════════════════


class TestVerifiers:
    @pytest.mark.asyncio
    async def test_verify_anthropic_no_key_raises(self):
        """verify_anthropic() raises EnvironmentError without key."""
        from factory.setup.verify import verify_anthropic

        with patch("factory.setup.verify.get_secret", return_value=None):
            with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                await verify_anthropic()

    @pytest.mark.asyncio
    async def test_verify_github_no_key_raises(self):
        """verify_github() raises EnvironmentError without token."""
        from factory.setup.verify import verify_github

        with patch("factory.setup.verify.get_secret", return_value=None):
            with pytest.raises(EnvironmentError, match="GITHUB_TOKEN"):
                await verify_github()

    @pytest.mark.asyncio
    async def test_verify_supabase_no_creds_raises(self):
        """verify_supabase() raises when URL or key absent."""
        from factory.setup.verify import verify_supabase

        with patch("factory.setup.verify.get_secret", return_value=None):
            with pytest.raises(EnvironmentError):
                await verify_supabase()

    @pytest.mark.asyncio
    async def test_verify_all_services_collects_errors(self):
        """verify_all_services() collects failures without raising."""
        from factory.setup.verify import verify_all_services

        with patch("factory.setup.verify.get_secret", return_value=None):
            results = await verify_all_services()

        assert isinstance(results, dict)
        assert len(results) == 5
        for name, r in results.items():
            assert r["status"] in ("connected", "failed")


# ═══════════════════════════════════════════════════════════════════
# Supabase Integration Tests (SupabaseFallback)
# ═══════════════════════════════════════════════════════════════════


class TestSupabaseFallback:
    def test_fallback_table_insert_select(self):
        """SupabaseFallback supports insert + select cycle."""
        from factory.integrations.supabase import SupabaseFallback

        sb = SupabaseFallback()
        # Insert
        sb.table("test_table").insert({"id": "row1", "value": "hello"}).execute()
        # Select
        resp = sb.table("test_table").select("*").execute()
        assert len(resp.data) >= 1

    def test_fallback_upsert(self):
        """SupabaseFallback upsert stores or updates rows."""
        from factory.integrations.supabase import SupabaseFallback

        sb = SupabaseFallback()
        sb.table("t").upsert({"id": "r1", "val": 1}).execute()
        sb.table("t").upsert({"id": "r1", "val": 2}).execute()

        resp = sb.table("t").select("*").eq("id", "r1").execute()
        # Should have one row (upserted)
        assert len(resp.data) >= 1

    def test_supabase_execute_sql_fallback_raises_import_error(self):
        """supabase_execute_sql raises ImportError when SupabaseFallback used."""
        from factory.integrations.supabase import supabase_execute_sql, SupabaseFallback

        async def run():
            with patch(
                "factory.integrations.supabase.get_supabase_client",
                return_value=SupabaseFallback(),
            ):
                await supabase_execute_sql("SELECT 1")

        with pytest.raises(ImportError, match="not configured"):
            asyncio.get_event_loop().run_until_complete(run())


# ═══════════════════════════════════════════════════════════════════
# UserSpace Tests
# ═══════════════════════════════════════════════════════════════════


class TestUserSpace:
    def test_prohibited_patterns_count(self):
        """PROHIBITED_PATTERNS has exactly 22 entries per spec §2.5."""
        from factory.core.user_space import PROHIBITED_PATTERNS
        assert len(PROHIBITED_PATTERNS) == 22

    def test_sudo_blocked(self):
        """sudo commands are blocked."""
        from factory.core.user_space import enforce_user_space
        from factory.core.state import UserSpaceViolation

        with pytest.raises(UserSpaceViolation):
            enforce_user_space("sudo apt-get install curl")

    def test_chmod_777_blocked(self):
        """chmod 777 is blocked."""
        from factory.core.user_space import enforce_user_space
        from factory.core.state import UserSpaceViolation

        with pytest.raises(UserSpaceViolation):
            enforce_user_space("chmod 777 /app/data")

    def test_rm_rf_blocked(self):
        """rm -rf / is blocked."""
        from factory.core.user_space import enforce_user_space
        from factory.core.state import UserSpaceViolation

        with pytest.raises(UserSpaceViolation):
            enforce_user_space("rm -rf /usr")

    def test_safe_command_passes(self):
        """Regular commands pass without modification."""
        from factory.core.user_space import enforce_user_space

        result = enforce_user_space("echo hello world")
        assert "hello world" in result

    def test_pip_install_rewritten(self):
        """pip install is rewritten to --user."""
        from factory.core.user_space import enforce_user_space

        result = enforce_user_space("pip install requests")
        assert "--user" in result
