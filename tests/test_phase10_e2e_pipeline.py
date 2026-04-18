"""
AI Factory Pipeline v5.8.12 — Phase 10: End-to-End Dry-Run Pipeline Tests

Verifies the full pipeline runs from S0_INTAKE through S9_HANDOFF and reaches
Stage.COMPLETED in dry-run mode (AI_PROVIDER=mock, DRY_RUN=true).

Fixes exercised here:
  - cst_time_of_day_restrictions bypassed in DRY_RUN
  - generate_visual_mocks called with correct signature
  - _to_disk import removed from _generate_icon_set
  - orchestrator transitions to Stage.COMPLETED after S9

8 tests:
  1.  Full pipeline reaches Stage.COMPLETED
  2.  All 10 stages produce output (s0_output … s9_output all non-None)
  3.  Stage history contains all 10 stage transitions + COMPLETED
  4.  No legal_halt on success path
  5.  total_cost_usd is numeric and ≥ 0
  6.  s0_output contains app_name
  7.  s9_output['delivered'] is True
  8.  Pipeline HALTS (not crashes) when s0 AI is forced to fail with no app_name hint
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, patch

from factory.core.state import PipelineState, Stage


# ─── helpers ──────────────────────────────────────────────────────────────────

def _e2e_state(project_id: str = "e2e-test-001") -> PipelineState:
    return PipelineState(
        project_id=project_id,
        operator_id="op-e2e",
        project_metadata={"raw_input": "app name: E2EApp\nA simple productivity app"},
    )


def _patches():
    """Context managers that suppress external side-effects."""
    return (
        patch("factory.telegram.notifications.send_telegram_message", new=AsyncMock()),
        patch("factory.telegram.notifications.notify_operator", new=AsyncMock()),
        patch("factory.integrations.supabase.upsert_pipeline_state", new=AsyncMock()),
        patch("factory.monitoring.budget_governor.BudgetGovernor.check", new=AsyncMock()),
        patch("factory.monitoring.budget_governor.BudgetGovernor.set_spend_source"),
    )


async def _run(state: PipelineState) -> PipelineState:
    p = _patches()
    for ctx in p:
        ctx.__enter__()
    try:
        from factory.orchestrator import run_pipeline
        return await run_pipeline(state)
    finally:
        for ctx in reversed(p):
            ctx.__exit__(None, None, None)


# ─── env fixture ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def dry_run_env(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("SCOUT_PROVIDER", "mock")
    monkeypatch.setenv("SKIP_CREDENTIAL_PREFLIGHT", "true")
    monkeypatch.setenv("PIPELINE_ENV", "ci")
    monkeypatch.setenv("TELEGRAM_POLLING", "false")


# ═══════════════════════════════════════════════════════════════════
# Test 1: full pipeline reaches COMPLETED
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_full_pipeline_reaches_completed():
    """run_pipeline must return state.current_stage == Stage.COMPLETED."""
    state = _e2e_state("e2e-t1")
    result = await _run(state)
    assert result.current_stage == Stage.COMPLETED, (
        f"Expected COMPLETED, got {result.current_stage}. "
        f"halt_reason={result.project_metadata.get('halt_reason_struct')}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 2: all 10 stages produce output
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_stages_produce_output():
    """s0_output through s9_output must all be non-None dicts."""
    state = _e2e_state("e2e-t2")
    result = await _run(state)
    for i in range(10):
        out = getattr(result, f"s{i}_output", None)
        assert isinstance(out, dict), (
            f"s{i}_output is {type(out).__name__}, expected dict"
        )
        assert len(out) > 0, f"s{i}_output is empty"


# ═══════════════════════════════════════════════════════════════════
# Test 3: stage history contains all transitions + COMPLETED
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stage_history_contains_all_stages():
    """stage_history must include every stage S0–S9 and COMPLETED."""
    state = _e2e_state("e2e-t3")
    result = await _run(state)
    visited = {h["to"] for h in result.stage_history}
    required = {
        "S0_INTAKE", "S1_LEGAL", "S2_BLUEPRINT", "S3_DESIGN",
        "S4_CODEGEN", "S5_BUILD", "S6_TEST", "S7_DEPLOY",
        "S8_VERIFY", "S9_HANDOFF", "COMPLETED",
    }
    missing = required - visited
    assert not missing, f"Stage history missing: {missing}"


# ═══════════════════════════════════════════════════════════════════
# Test 4: no legal_halt on success path
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_legal_halt_on_success():
    """legal_halt must be False when pipeline completes successfully."""
    state = _e2e_state("e2e-t4")
    result = await _run(state)
    assert result.legal_halt is False


# ═══════════════════════════════════════════════════════════════════
# Test 5: cost tracking is numeric
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cost_tracking_is_numeric():
    """total_cost_usd must be a float ≥ 0 after pipeline completion."""
    state = _e2e_state("e2e-t5")
    result = await _run(state)
    assert isinstance(result.total_cost_usd, float)
    assert result.total_cost_usd >= 0.0


# ═══════════════════════════════════════════════════════════════════
# Test 6: s0_output has app_name
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_s0_output_has_app_name():
    """s0_output must contain a non-empty app_name."""
    state = _e2e_state("e2e-t6")
    result = await _run(state)
    app_name = (result.s0_output or {}).get("app_name", "")
    assert isinstance(app_name, str) and app_name, (
        f"s0_output['app_name'] is empty or missing: {result.s0_output}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 7: s9_output delivered is True
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_s9_output_delivered():
    """s9_output['delivered'] must be True on successful completion."""
    state = _e2e_state("e2e-t7")
    result = await _run(state)
    assert (result.s9_output or {}).get("delivered") is True


# ═══════════════════════════════════════════════════════════════════
# Test 8: pipeline halts cleanly when S0 AI fails + no app name
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_halts_cleanly_on_s0_ai_failure():
    """When S0 AI fails AND no app name in raw input, pipeline halts with APP_NAME_MISSING."""
    state = PipelineState(
        project_id="e2e-t8-halt",
        operator_id="op-e2e",
        project_metadata={"raw_input": "build me something cool"},  # no 'app name:'
    )
    with patch("factory.core.roles.call_ai", new=AsyncMock(side_effect=Exception("AI down"))):
        result = await _run(state)

    assert result.current_stage == Stage.HALTED
    struct = result.project_metadata.get("halt_reason_struct") or {}
    assert struct.get("code") == "APP_NAME_MISSING", (
        f"Expected APP_NAME_MISSING halt, got: {struct}"
    )
