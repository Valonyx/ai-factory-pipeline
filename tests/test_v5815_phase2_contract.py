"""v5.8.15 Phase 2 (Issues 50 + 52) — unit-tier tests.

These tests use the unit marker so conftest autouse mocks apply. They
verify:

1. StageMetrics counters wire up the way pipeline_node expects.
2. The contract-bypass helper behaves correctly.
3. metrics_context ContextVar plumbing routes into the Pydantic field.
4. archive_project clears pipeline_aborted on the archived state
   (ghost-cancel regression guard).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit


# ── StageMetrics basics ──────────────────────────────────────────────


def test_stage_metrics_reset_and_record():
    from factory.core.state import StageMetrics

    m = StageMetrics()
    assert m.provider_calls_in_stage == 0
    assert m.provider_calls_total == 0

    m.record_provider_call(2)
    m.record_artifact(1)
    m.record_mm_write(3)
    assert m.provider_calls_in_stage == 2
    assert m.provider_calls_total == 2
    assert m.artifacts_produced_in_stage == 1
    assert m.mm_writes_in_stage == 3
    assert m.last_provider_call_at is not None

    m.reset_stage()
    assert m.provider_calls_in_stage == 0
    assert m.artifacts_produced_in_stage == 0
    assert m.mm_writes_in_stage == 0
    # Totals persist across reset
    assert m.provider_calls_total == 2
    assert m.artifacts_produced_total == 1
    assert m.mm_writes_total == 3


# ── metrics_context → StageMetrics plumbing ──────────────────────────


def test_metrics_context_bumps_flow_into_merge():
    from factory.core.state import StageMetrics
    from factory.core import metrics_context as mc
    from factory.orchestrator import _merge_stage_counters

    class _FakeState:
        metrics = StageMetrics()

    state = _FakeState()
    counters = mc.start_stage_metrics()
    try:
        mc.bump_provider_call(1)
        mc.bump_artifact(2)
        mc.bump_mm_write(1)
    finally:
        mc.clear_stage_metrics()

    _merge_stage_counters(state, dict(counters))
    assert state.metrics.provider_calls_in_stage == 1
    assert state.metrics.artifacts_produced_in_stage == 2
    assert state.metrics.mm_writes_in_stage == 1


# ── Contract bypass helper ───────────────────────────────────────────


def test_contract_bypass_respects_mock_provider(monkeypatch):
    from factory.core.state import PipelineState, Stage
    from factory.orchestrator import _contract_bypass_allowed

    state = PipelineState(project_id="p1", operator_id="op1")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    assert _contract_bypass_allowed(Stage.S1_LEGAL, state) is True


def test_contract_bypass_dry_run(monkeypatch):
    from factory.core.state import PipelineState, Stage
    from factory.orchestrator import _contract_bypass_allowed

    state = PipelineState(project_id="p1", operator_id="op1")
    monkeypatch.setenv("AI_PROVIDER", "")
    monkeypatch.setenv("DRY_RUN", "true")
    assert _contract_bypass_allowed(Stage.S4_CODEGEN, state) is True


def test_contract_bypass_handoff_stage(monkeypatch):
    from factory.core.state import PipelineState, Stage
    from factory.orchestrator import _contract_bypass_allowed

    state = PipelineState(project_id="p1", operator_id="op1")
    monkeypatch.setenv("AI_PROVIDER", "")
    monkeypatch.setenv("DRY_RUN", "")
    monkeypatch.setenv("AI_FACTORY_CONTRACT_BYPASS", "")
    assert _contract_bypass_allowed(Stage.S9_HANDOFF, state) is True


def test_contract_bypass_not_allowed_in_normal_run(monkeypatch):
    from factory.core.state import PipelineState, Stage
    from factory.orchestrator import _contract_bypass_allowed

    state = PipelineState(project_id="p1", operator_id="op1")
    monkeypatch.setenv("AI_PROVIDER", "")
    monkeypatch.setenv("DRY_RUN", "")
    monkeypatch.setenv("AI_FACTORY_CONTRACT_BYPASS", "")
    assert _contract_bypass_allowed(Stage.S1_LEGAL, state) is False


# ── STAGE_TRIVIAL_COMPLETION halt code exists ────────────────────────


def test_trivial_completion_halt_code_registered():
    from factory.core.halt import HaltCode

    assert HaltCode.STAGE_TRIVIAL_COMPLETION.value == "STAGE_TRIVIAL_COMPLETION"


# ── Ghost-cancel: archive_project clears pipeline_aborted ────────────


@pytest.mark.asyncio
async def test_archive_project_clears_pipeline_aborted(monkeypatch):
    from factory.core.state import PipelineState, Stage
    from factory.telegram import bot as bot_mod

    state = PipelineState(project_id="pghost", operator_id="op42")
    state.pipeline_aborted = True
    state.current_stage = Stage.S2_BLUEPRINT
    bot_mod._active_projects_fallback["op42"] = {
        "project_id": "pghost",
        "current_stage": state.current_stage.value,
        "state_json": state.model_dump(mode="json"),
    }

    captured: dict = {}

    async def _fake_archive(pid, st):
        captured["pid"] = pid
        captured["pipeline_aborted"] = st.pipeline_aborted
        captured["current_stage"] = st.current_stage

    monkeypatch.setattr(bot_mod, "_sb_archive", _fake_archive)
    monkeypatch.setattr(bot_mod, "cancel_project_task", lambda *_: None)

    await bot_mod.archive_project("pghost")

    assert captured["pipeline_aborted"] is False
    assert captured["current_stage"] == Stage.HALTED
    assert "op42" not in bot_mod._active_projects_fallback
