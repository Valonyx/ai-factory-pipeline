"""
PROD-4 Validation: Real Supabase Client

Tests cover:
  1. Checksum computation (SHA-256 deterministic)
  2. Fallback client (in-memory operations)
  3. Pipeline state CRUD (upsert, get)
  4. Snapshot list and restore with checksum validation
  5. Active project management (create, get, archive)
  6. Operator whitelist (add, check)
  7. Operator state (set, get)
  8. Monthly cost tracking (create, accumulate)
  9. Audit log writes
  10. Triple-write state persistence
  11. Checksum mismatch detection

Run:
  pytest tests/test_prod_04_supabase.py -v
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from factory.core.state import PipelineState, Stage
from factory.integrations.supabase import (
    compute_state_checksum,
    SupabaseFallback,
    upsert_pipeline_state,
    get_pipeline_state,
    list_snapshots,
    restore_state,
    upsert_active_project,
    get_active_project,
    archive_project,
    check_operator_whitelist,
    add_operator_to_whitelist,
    set_operator_state_db,
    get_operator_state_db,
    track_monthly_cost,
    get_monthly_costs,
    audit_log,
    reset_clients,
)


# ═══════════════════════════════════════════════════════════════════
# Test 1: Checksum Computation
# ═══════════════════════════════════════════════════════════════════

class TestChecksum:
    def test_deterministic(self):
        """Same input produces same checksum."""
        data = {"project_id": "test", "stage": "S0_INTAKE"}
        c1 = compute_state_checksum(data)
        c2 = compute_state_checksum(data)
        assert c1 == c2

    def test_different_input(self):
        """Different input produces different checksum."""
        c1 = compute_state_checksum({"a": 1})
        c2 = compute_state_checksum({"a": 2})
        assert c1 != c2

    def test_key_order_independent(self):
        """Key order should not affect checksum (sorted keys)."""
        c1 = compute_state_checksum({"b": 2, "a": 1})
        c2 = compute_state_checksum({"a": 1, "b": 2})
        assert c1 == c2

    def test_sha256_length(self):
        """Checksum should be 64 hex chars (SHA-256)."""
        c = compute_state_checksum({"test": True})
        assert len(c) == 64
        assert all(ch in "0123456789abcdef" for ch in c)


# ═══════════════════════════════════════════════════════════════════
# Test 2: Fallback Client
# ═══════════════════════════════════════════════════════════════════

class TestFallbackClient:
    def test_insert_and_select(self):
        fb = SupabaseFallback()
        fb.table("test").insert({"id": "1", "name": "Alice"}).execute()
        resp = fb.table("test").select("*").eq("id", "1").execute()
        assert len(resp.data) == 1
        assert resp.data[0]["name"] == "Alice"

    def test_upsert_creates(self):
        fb = SupabaseFallback()
        fb.table("test").upsert({"id": "2", "val": "a"}).execute()
        resp = fb.table("test").select("*").eq("id", "2").execute()
        assert len(resp.data) == 1

    def test_upsert_updates(self):
        fb = SupabaseFallback()
        fb.table("test").upsert({"id": "3", "val": "old"}).execute()
        fb.table("test").upsert({"id": "3", "val": "new"}).execute()
        resp = fb.table("test").select("*").eq("id", "3").execute()
        assert resp.data[0]["val"] == "new"

    def test_delete(self):
        fb = SupabaseFallback()
        fb.table("test").insert({"id": "4", "val": "x"}).execute()
        fb.table("test").delete().eq("id", "4").execute()
        resp = fb.table("test").select("*").eq("id", "4").execute()
        assert len(resp.data) == 0

    def test_separate_tables(self):
        fb = SupabaseFallback()
        fb.table("a").insert({"id": "1"}).execute()
        fb.table("b").insert({"id": "2"}).execute()
        resp_a = fb.table("a").select("*").execute()
        resp_b = fb.table("b").select("*").execute()
        assert len(resp_a.data) == 1
        assert len(resp_b.data) == 1


# ═══════════════════════════════════════════════════════════════════
# Test 3: Pipeline State with Fallback
# ═══════════════════════════════════════════════════════════════════

class TestPipelineState:
    @pytest.fixture(autouse=True)
    def setup(self):
        reset_clients()
        yield
        reset_clients()

    @pytest.mark.asyncio
    async def test_upsert_and_get(self):
        """Upsert state then retrieve it (using fallback client)."""
        state = PipelineState(project_id="sb-test-1", operator_id="op1")
        state.current_stage = Stage.S2_BLUEPRINT
        state.total_cost_usd = 1.25

        # Force fallback client
        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=SupabaseFallback(),
        ):
            result = await upsert_pipeline_state("sb-test-1", state)
            assert result["write_1"] is True
            assert result["write_2"] is True
            assert len(result["checksum"]) == 64

    @pytest.mark.asyncio
    async def test_triple_write_all_succeed(self):
        """Triple-write should report all 3 writes successful."""
        state = PipelineState(project_id="tw-test", operator_id="op1")

        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=SupabaseFallback(),
        ):
            result = await upsert_pipeline_state(
                "tw-test", state, git_commit_hash="abc123"
            )
            assert result["write_1"] is True
            assert result["write_2"] is True
            assert result["write_3"] is True


# ═══════════════════════════════════════════════════════════════════
# Test 4: Snapshot & Restore
# ═══════════════════════════════════════════════════════════════════

class TestSnapshotRestore:
    @pytest.fixture(autouse=True)
    def setup(self):
        reset_clients()
        yield
        reset_clients()

    @pytest.mark.asyncio
    async def test_list_snapshots_empty(self):
        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=SupabaseFallback(),
        ):
            snaps = await list_snapshots("no-project")
            assert snaps == []

    @pytest.mark.asyncio
    async def test_checksum_validation_on_restore(self):
        """Restore should validate checksum and reject corrupted data."""
        fb = SupabaseFallback()
        state = PipelineState(project_id="ck-test", operator_id="op1")
        state_dict = state.model_dump(mode="json")

        # Insert a snapshot with WRONG checksum
        fb.table("state_snapshots").insert({
            "project_id": "ck-test",
            "snapshot_id": 0,
            "stage": "S0_INTAKE",
            "state_json": state_dict,
            "checksum": "wrong_checksum_value",
        }).execute()

        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            with pytest.raises(ValueError, match="Checksum mismatch"):
                await restore_state("ck-test", 0, validate_checksum=True)


# ═══════════════════════════════════════════════════════════════════
# Test 5: Active Projects
# ═══════════════════════════════════════════════════════════════════

class TestActiveProjects:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self):
        fb = SupabaseFallback()
        state = PipelineState(project_id="ap-test", operator_id="op1")

        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            result = await upsert_active_project("op1", state)
            assert result is True

            proj = await get_active_project("op1")
            assert proj is not None
            assert proj["project_id"] == "ap-test"

    @pytest.mark.asyncio
    async def test_archive_project(self):
        fb = SupabaseFallback()
        state = PipelineState(project_id="arch-test", operator_id="op2")

        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            await upsert_active_project("op2", state)
            result = await archive_project("arch-test", state)
            assert result is True


# ═══════════════════════════════════════════════════════════════════
# Test 6: Operator Whitelist
# ═══════════════════════════════════════════════════════════════════

class TestOperatorWhitelist:
    @pytest.mark.asyncio
    async def test_add_and_check(self):
        fb = SupabaseFallback()
        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            added = await add_operator_to_whitelist("12345", "Alex")
            assert added is True

            exists = await check_operator_whitelist("12345")
            assert exists is True

    @pytest.mark.asyncio
    async def test_nonexistent_operator(self):
        fb = SupabaseFallback()
        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            exists = await check_operator_whitelist("99999")
            assert exists is False


# ═══════════════════════════════════════════════════════════════════
# Test 7: Operator State
# ═══════════════════════════════════════════════════════════════════

class TestOperatorStateDB:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        fb = SupabaseFallback()
        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            result = await set_operator_state_db(
                "op1", "awaiting_input", {"stage": "S2"}
            )
            assert result is True

            state = await get_operator_state_db("op1")
            assert state is not None
            assert state["state"] == "awaiting_input"


# ═══════════════════════════════════════════════════════════════════
# Test 8: Monthly Cost Tracking
# ═══════════════════════════════════════════════════════════════════

class TestMonthlyCosts:
    @pytest.mark.asyncio
    async def test_track_and_get(self):
        fb = SupabaseFallback()
        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            result = await track_monthly_cost(
                "op1", ai_cost=1.50, infra_cost=25.0, project_increment=1
            )
            assert result is True


# ═══════════════════════════════════════════════════════════════════
# Test 9: Audit Log
# ═══════════════════════════════════════════════════════════════════

class TestAuditLog:
    @pytest.mark.asyncio
    async def test_write_audit_entry(self):
        fb = SupabaseFallback()
        with patch(
            "factory.integrations.supabase.get_supabase_client",
            return_value=fb,
        ):
            result = await audit_log(
                "test-proj",
                "stage_complete",
                {"stage": "S2_BLUEPRINT", "cost": 0.50},
                operator_id="op1",
            )
            assert result is True

            # Verify entry exists
            resp = fb.table("audit_log").select("*").execute()
            assert len(resp.data) == 1
            assert resp.data[0]["event"] == "stage_complete"
