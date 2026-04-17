"""
AI Factory Pipeline v5.8.12 — Phase 6 Tests
Issues 1 (Stage Regression), 2 (Time Travel), 3 (Per-Stage File Delivery),
4 (Deploy-less Delivery)

10 tests covering:
  1. resolve_stage aliases
  2. analyze_regression_impact
  3. analyze_regression_impact bad stage
  4. diff_snapshots — Supabase returns empty
  5. diff_snapshots — both found, delta computed
  6. _STAGE_ARTIFACTS_DELIVERY covers key stages
  7. deploy-less skip_store_upload flag
  8. _persist_snapshot calls upsert_pipeline_state
  9. request_regression — no snapshots → None
 10. cmd_rerun — unknown stage reply
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.state import PipelineState, Stage


# ═══════════════════════════════════════════════════════════════════
# Test 1: resolve_stage aliases
# ═══════════════════════════════════════════════════════════════════

def test_resolve_stage_aliases():
    from factory.pipeline.stage_regression import resolve_stage
    assert resolve_stage("s4") == "S4_CODEGEN"
    assert resolve_stage("deploy") == "S7_DEPLOY"
    assert resolve_stage("S7_DEPLOY") == "S7_DEPLOY"
    assert resolve_stage("codegen") == "S4_CODEGEN"
    assert resolve_stage("garbage") is None
    assert resolve_stage("  s1  ") == "S1_LEGAL"


# ═══════════════════════════════════════════════════════════════════
# Test 2: analyze_regression_impact
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_analyze_regression_impact():
    from factory.pipeline.stage_regression import analyze_regression_impact
    result = await analyze_regression_impact("S7_DEPLOY", "S4_CODEGEN")
    assert result["rerun_count"] == 4
    assert result["stages_to_rerun"][0] == "S4_CODEGEN"
    assert "S7_DEPLOY" in result["stages_to_rerun"]
    assert "warning" in result


# ═══════════════════════════════════════════════════════════════════
# Test 3: analyze_regression_impact — bad stage
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_analyze_regression_bad_stage():
    from factory.pipeline.stage_regression import analyze_regression_impact
    result = await analyze_regression_impact("S7_DEPLOY", "BADSTAGE")
    assert "error" in result


# ═══════════════════════════════════════════════════════════════════
# Test 4: diff_snapshots — Supabase returns empty
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_diff_snapshots_missing():
    from factory.integrations.supabase import diff_snapshots

    mock_resp = MagicMock()
    mock_resp.data = []
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = mock_resp

    with patch("factory.integrations.supabase.get_supabase_client", return_value=mock_client):
        result = await diff_snapshots("test-proj", 1, 2)

    assert "error" in result


# ═══════════════════════════════════════════════════════════════════
# Test 5: diff_snapshots — both found, delta computed
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_diff_snapshots_both_found():
    from factory.integrations.supabase import diff_snapshots

    mock_resp = MagicMock()
    mock_resp.data = [
        {
            "snapshot_id": 1,
            "stage": "S1_LEGAL",
            "state_json": {
                "total_cost_usd": 0.10,
                "current_stage": "s1_legal",
                "selected_stack": "flutterflow",
                "pipeline_mode": "build",
                "autonomy_mode": "autopilot",
            },
            "created_at": "2026-04-18T10:00:00",
        },
        {
            "snapshot_id": 3,
            "stage": "S3_DESIGN",
            "state_json": {
                "total_cost_usd": 0.45,
                "current_stage": "s3_design",
                "selected_stack": "flutterflow",
                "pipeline_mode": "build",
                "autonomy_mode": "autopilot",
            },
            "created_at": "2026-04-18T10:30:00",
        },
    ]
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = mock_resp

    with patch("factory.integrations.supabase.get_supabase_client", return_value=mock_client):
        result = await diff_snapshots("test-proj", 1, 3)

    assert "error" not in result
    assert result["stage_a"] == "S1_LEGAL"
    assert result["stage_b"] == "S3_DESIGN"
    assert abs(result["cost_delta"] - 0.35) < 0.001
    # current_stage changed → should be in fields_changed
    assert any("current_stage" in c for c in result["fields_changed"])


# ═══════════════════════════════════════════════════════════════════
# Test 6: _STAGE_ARTIFACTS_DELIVERY covers all required stages
# ═══════════════════════════════════════════════════════════════════

def test_stage_delivery_map_covers_all_stages():
    from factory.orchestrator import _STAGE_ARTIFACTS_DELIVERY
    assert "S1_LEGAL" in _STAGE_ARTIFACTS_DELIVERY
    assert "S4_CODEGEN" in _STAGE_ARTIFACTS_DELIVERY
    assert "S9_HANDOFF" in _STAGE_ARTIFACTS_DELIVERY
    # Each entry is a list of (key, label) tuples
    for stage, specs in _STAGE_ARTIFACTS_DELIVERY.items():
        assert isinstance(specs, list)
        for spec in specs:
            assert len(spec) == 2, f"Spec for {stage} must be (key, label) tuple"


# ═══════════════════════════════════════════════════════════════════
# Test 7: deploy-less skip_store_upload flag set when creds missing
# ═══════════════════════════════════════════════════════════════════

def test_deploy_less_skip_flag():
    """When iOS is targeted but APPLE_ID is not set, skip_store_upload must be True."""
    from factory.core.state import PipelineState

    state = PipelineState(project_id="deploy-test", operator_id="op-1")
    state.project_metadata["platforms"] = ["ios"]

    # Strip creds from env
    env_patch = {k: v for k, v in os.environ.items()
                 if k not in ("APPLE_ID", "APP_SPECIFIC_PASSWORD")}

    with patch.dict(os.environ, env_patch, clear=True):
        _has_apple = bool(os.environ.get("APPLE_ID") and os.environ.get("APP_SPECIFIC_PASSWORD"))
        _has_google = bool(
            os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT")
            or os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        )

        from factory.core.platform_targets import resolve_deploy_targets
        mapping = resolve_deploy_targets(["ios"])
        store_targets = mapping.get("store_targets", [])

        _needs_apple = any(t in store_targets for t in ("app_store", "testflight"))
        _skip_to_airlock = _needs_apple and not _has_apple

        if _skip_to_airlock:
            state.project_metadata["skip_store_upload"] = True

    assert state.project_metadata.get("skip_store_upload") is True


# ═══════════════════════════════════════════════════════════════════
# Test 8: _persist_snapshot calls upsert_pipeline_state
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_persist_snapshot_calls_supabase():
    from factory.orchestrator import _persist_snapshot
    from factory.core.state import PipelineState

    state = PipelineState(project_id="snap-test", operator_id="op-1")
    state.snapshot_id = 0

    mock_upsert = AsyncMock()
    with patch("factory.integrations.supabase.upsert_pipeline_state", mock_upsert):
        await _persist_snapshot(state)

    mock_upsert.assert_called_once()
    call_args = mock_upsert.call_args
    assert call_args[0][0] == "snap-test"  # first positional arg = project_id
    assert state.snapshot_id == 1


# ═══════════════════════════════════════════════════════════════════
# Test 9: request_regression — no snapshots → returns None
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_request_regression_no_snapshots():
    from factory.pipeline.stage_regression import request_regression

    messages = []

    async def _notify(msg: str):
        messages.append(msg)

    with patch("factory.integrations.supabase.list_snapshots", AsyncMock(return_value=[])):
        result = await request_regression("proj-001", "s4", "op-1", notify_fn=_notify)

    assert result is None
    assert any("No snapshots" in m or "⚠️" in m for m in messages)


# ═══════════════════════════════════════════════════════════════════
# Test 10: cmd_rerun — unknown stage → reply contains "Unknown stage"
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rerun_command_unknown_stage():
    from factory.telegram.bot import cmd_rerun

    reply_texts = []

    async def _reply(text, **kwargs):
        reply_texts.append(text)

    mock_update = MagicMock()
    mock_update.effective_user.id = "999"
    mock_update.message.reply_text = AsyncMock(side_effect=_reply)

    mock_context = MagicMock()
    mock_context.args = ["banana"]

    mock_active = {"project_id": "test-proj", "stage": "S7_DEPLOY"}

    with patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=mock_active)):
        await cmd_rerun(mock_update, mock_context)

    assert any("Unknown stage" in t or "unknown stage" in t.lower() for t in reply_texts)
