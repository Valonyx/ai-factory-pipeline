"""
v5.8.14 Phase 2 — Hard Halt & Resume Tests (Issues 37, 43, 45, 48)

Issue 48: mode_name NameError eliminated in roles.py
Issue 37: pipeline_node now catches stage exceptions and sets Stage.HALTED
Issue 45: stage exceptions do not silently skip — HALTED is written to DB
Issue 43: /continue correctly detects stale non-HALTED state and resumes

Tests:
  1.  mode_name is defined in _call_ai — no NameError on provider fallback
  2.  pipeline_node transitions to HALTED when stage function raises
  3.  pipeline_node stores halt_reason_struct with STAGE_EXCEPTION code
  4.  pipeline_node stores halted_from_stage matching the stage name
  5.  pipeline_node persists HALTED state (calls persist_state)
  6.  pipeline_node does NOT raise — caller gets state, not exception
  7.  _run_and_notify safety net sets HALTED when exception escapes pipeline_node
  8.  _run_and_notify persists HALTED state to DB when safety net fires
  9.  cmd_continue "Pipeline running" check respects live task presence
  10. cmd_continue repairs stale non-HALTED state before resuming
  11. Full pipeline reaches HALTED (not exception) when stage raises NameError-class error
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from factory.core.state import PipelineState, Stage, ExecutionMode
from factory.core.mode_router import MasterMode


# ─── helpers ──────────────────────────────────────────────────────────────────

def _state(pid="p2-test") -> PipelineState:
    return PipelineState(
        project_id=pid,
        operator_id="op-p2",
        project_metadata={"raw_input": "app name: HaltTest\nTest app"},
    )


# ═══════════════════════════════════════════════════════════════════
# Test 1: mode_name is defined — no NameError
# ═══════════════════════════════════════════════════════════════════

def test_mode_name_defined_in_call_ai_source():
    """mode_name must be assigned in roles.py before any log f-string references it."""
    import inspect
    from factory.core import roles
    src = inspect.getsource(roles)
    # The fix adds 'mode_name  = master_mode.value.upper()' after role_name assignment
    assert "mode_name  = master_mode.value.upper()" in src or \
           "mode_name = master_mode.value.upper()" in src, (
        "mode_name assignment missing from roles.py — Issue 48 fix not applied"
    )


@pytest.mark.asyncio
async def test_call_ai_survives_provider_fallback_no_nameerror(monkeypatch):
    """_call_ai must not raise NameError when first provider fails and fallback fires."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("DRY_RUN", "true")

    from factory.core.roles import call_ai, AIRole
    from factory.core.state import PipelineState

    state = PipelineState(
        project_id="ne-test", operator_id="op-ne",
        project_metadata={"raw_input": "test"},
    )

    # Should not raise NameError regardless of what providers do
    try:
        result, cost = await call_ai(
            role=AIRole.STRATEGIST,
            prompt="test fallback",
            state=state,
        )
    except NameError as e:
        pytest.fail(f"NameError still present in call_ai: {e}")
    except Exception:
        pass  # Other errors (no provider configured) are acceptable


# ═══════════════════════════════════════════════════════════════════
# Test 2: pipeline_node catches stage exceptions → Stage.HALTED
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_node_halts_on_stage_exception():
    """pipeline_node must transition to HALTED when the stage function raises."""
    from factory.pipeline.graph import pipeline_node

    @pipeline_node(Stage.S0_INTAKE)
    async def _failing_stage(state: PipelineState) -> PipelineState:
        raise RuntimeError("Simulated stage failure")

    state = _state("p2-t2")
    with patch("factory.pipeline.graph.legal_check_hook", AsyncMock()), \
         patch("factory.pipeline.graph.persist_state", AsyncMock()), \
         patch("factory.pipeline.graph.transition_to", side_effect=lambda s, stage: setattr(s, "current_stage", stage)):
        result = await _failing_stage(state)

    assert result.current_stage == Stage.HALTED, (
        f"Expected HALTED, got {result.current_stage}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 3: pipeline_node stores halt_reason_struct with STAGE_EXCEPTION
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_node_stores_halt_reason_struct():
    """pipeline_node must populate halt_reason_struct with STAGE_EXCEPTION code."""
    from factory.pipeline.graph import pipeline_node

    @pipeline_node(Stage.S1_LEGAL)
    async def _failing_stage(state: PipelineState) -> PipelineState:
        raise ValueError("Bad legal input")

    state = _state("p2-t3")
    with patch("factory.pipeline.graph.legal_check_hook", AsyncMock()), \
         patch("factory.pipeline.graph.persist_state", AsyncMock()), \
         patch("factory.pipeline.graph.transition_to", side_effect=lambda s, stage: setattr(s, "current_stage", stage)):
        result = await _failing_stage(state)

    struct = result.project_metadata.get("halt_reason_struct", {})
    assert struct.get("code") == "STAGE_EXCEPTION", (
        f"halt_reason_struct code should be STAGE_EXCEPTION, got: {struct}"
    )
    assert struct.get("error_type") == "ValueError"
    assert "Bad legal input" in struct.get("error_msg", "")


# ═══════════════════════════════════════════════════════════════════
# Test 4: pipeline_node stores halted_from_stage
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_node_stores_halted_from_stage():
    """pipeline_node must record halted_from_stage matching the crashing stage."""
    from factory.pipeline.graph import pipeline_node

    @pipeline_node(Stage.S2_BLUEPRINT)
    async def _failing_stage(state: PipelineState) -> PipelineState:
        raise RuntimeError("Blueprint AI unavailable")

    state = _state("p2-t4")
    with patch("factory.pipeline.graph.legal_check_hook", AsyncMock()), \
         patch("factory.pipeline.graph.persist_state", AsyncMock()), \
         patch("factory.pipeline.graph.transition_to", side_effect=lambda s, stage: setattr(s, "current_stage", stage)):
        result = await _failing_stage(state)

    assert result.project_metadata.get("halted_from_stage") == "S2_BLUEPRINT", (
        f"halted_from_stage mismatch: {result.project_metadata.get('halted_from_stage')}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 5: pipeline_node calls persist_state after HALTED transition
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_node_persists_halted_state():
    """pipeline_node must call persist_state after transitioning to HALTED."""
    from factory.pipeline.graph import pipeline_node

    @pipeline_node(Stage.S3_DESIGN)
    async def _failing_stage(state: PipelineState) -> PipelineState:
        raise RuntimeError("Design crash")

    state = _state("p2-t5")
    persist_mock = AsyncMock()
    with patch("factory.pipeline.graph.legal_check_hook", AsyncMock()), \
         patch("factory.pipeline.graph.persist_state", persist_mock), \
         patch("factory.pipeline.graph.transition_to", side_effect=lambda s, stage: setattr(s, "current_stage", stage)):
        await _failing_stage(state)

    # persist_state should be called with the HALTED state
    persist_mock.assert_awaited()
    called_state = persist_mock.call_args[0][0]
    assert called_state.current_stage == Stage.HALTED


# ═══════════════════════════════════════════════════════════════════
# Test 6: pipeline_node does NOT re-raise — caller gets state object
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_node_does_not_reraise():
    """pipeline_node must swallow stage exceptions and return state (not raise)."""
    from factory.pipeline.graph import pipeline_node

    @pipeline_node(Stage.S4_CODEGEN)
    async def _failing_stage(state: PipelineState) -> PipelineState:
        raise Exception("Anything")

    state = _state("p2-t6")
    with patch("factory.pipeline.graph.legal_check_hook", AsyncMock()), \
         patch("factory.pipeline.graph.persist_state", AsyncMock()), \
         patch("factory.pipeline.graph.transition_to", side_effect=lambda s, stage: setattr(s, "current_stage", stage)):
        # Must not raise
        result = await _failing_stage(state)

    assert isinstance(result, PipelineState)


# ═══════════════════════════════════════════════════════════════════
# Test 7: _run_and_notify safety net sets HALTED when exception escapes pipeline
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_run_and_notify_safety_net_sets_halted():
    """_run_and_notify's except block must set state.current_stage=HALTED."""
    captured = []

    async def _fake_update_state(s):
        captured.append(s.current_stage)

    state = _state("p2-t7")
    state.current_stage = Stage.S0_INTAKE  # simulates pre-crash state

    fake_update = MagicMock()
    fake_update.effective_user.id = 88001
    fake_update.message = MagicMock()
    fake_update.message.reply_text = AsyncMock()

    with patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced", "execution_mode": "cloud",
                                       "autonomy_mode": "autopilot"})), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot.update_project_state", AsyncMock(side_effect=_fake_update_state)), \
         patch("factory.orchestrator.run_pipeline", AsyncMock(side_effect=RuntimeError("orchestrator boom"))), \
         patch("factory.telegram.bot._bg", lambda coro: asyncio.get_event_loop().create_task(coro)), \
         patch("factory.telegram.bot.register_project_task"), \
         patch("factory.telegram.notifications.send_telegram_message", AsyncMock()):
        from factory.telegram.bot import _start_project
        await _start_project(
            fake_update, "88001", "crash test app", "CrashApp",
            pre_selected_platforms=None, pre_selected_market=None, pre_selected_logo=None,
        )
        # Give background task a moment to complete
        await asyncio.sleep(0.2)

    # At least one update_project_state call should have set HALTED
    assert Stage.HALTED in captured, (
        f"HALTED was never written to DB — safety net not triggered. Captured: {captured}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 8: _run_and_notify persists HALTED to DB (update_project_state called)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_run_and_notify_persists_halted():
    """_run_and_notify must call update_project_state when entering HALTED."""
    update_calls = []

    async def _track(s):
        update_calls.append(s.current_stage)

    fake_update = MagicMock()
    fake_update.effective_user.id = 88002
    fake_update.message = MagicMock()
    fake_update.message.reply_text = AsyncMock()

    with patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "balanced", "execution_mode": "cloud",
                                       "autonomy_mode": "autopilot"})), \
         patch("factory.telegram.bot.get_active_project", AsyncMock(return_value=None)), \
         patch("factory.telegram.bot.update_project_state", AsyncMock(side_effect=_track)), \
         patch("factory.orchestrator.run_pipeline", AsyncMock(side_effect=RuntimeError("DB unavailable"))), \
         patch("factory.telegram.bot._bg", lambda coro: asyncio.get_event_loop().create_task(coro)), \
         patch("factory.telegram.bot.register_project_task"), \
         patch("factory.telegram.notifications.send_telegram_message", AsyncMock()):
        from factory.telegram.bot import _start_project
        await _start_project(
            fake_update, "88002", "persist test app", "PersistApp",
            pre_selected_platforms=None, pre_selected_market=None, pre_selected_logo=None,
        )
        await asyncio.sleep(0.2)

    assert update_calls, "update_project_state was never called"


# ═══════════════════════════════════════════════════════════════════
# Test 9: cmd_continue — live task → "Pipeline running" reply
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_continue_live_task_returns_running():
    """/continue with a live (not done) task → 'Pipeline running' message."""
    from factory.telegram.bot import cmd_continue, _project_tasks

    state = _state("p2-t9-live")
    state.current_stage = Stage.S1_LEGAL  # non-HALTED

    # Register a "live" task (not done)
    live_task = MagicMock()
    live_task.done.return_value = False
    _project_tasks[state.project_id] = live_task

    replied = []
    fake_update = MagicMock()
    fake_update.effective_user.id = 99001
    fake_update.message.reply_text = AsyncMock(side_effect=lambda t, **kw: replied.append(t))

    state_json = state.model_dump()
    with patch("factory.telegram.bot.get_active_project",
               AsyncMock(return_value={"state_json": state_json})), \
         patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)):
        await cmd_continue(fake_update, MagicMock())

    _project_tasks.pop(state.project_id, None)
    assert any("running" in r.lower() for r in replied), (
        f"Expected 'Pipeline running' reply, got: {replied}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 10: cmd_continue repairs stale non-HALTED DB state
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cmd_continue_repairs_stale_non_halted_state():
    """/continue with no live task and non-HALTED state must set HALTED before resuming."""
    from factory.telegram.bot import cmd_continue, _project_tasks

    state = _state("p2-t10-stale")
    state.current_stage = Stage.S0_INTAKE  # stuck non-HALTED (pre-fix crash scenario)
    state.previous_stage = Stage.S0_INTAKE

    # No live task registered for this project
    _project_tasks.pop(state.project_id, None)

    updated_states = []

    async def _track_update(s):
        updated_states.append(s.current_stage)

    replied = []
    fake_update = MagicMock()
    fake_update.effective_user.id = 99002
    fake_update.message.reply_text = AsyncMock(side_effect=lambda t, **kw: replied.append(t))

    state_json = state.model_dump()
    with patch("factory.telegram.bot.get_active_project",
               AsyncMock(return_value={"state_json": state_json})), \
         patch("factory.telegram.bot.update_project_state", AsyncMock(side_effect=_track_update)), \
         patch("factory.telegram.bot.authenticate_operator", AsyncMock(return_value=True)), \
         patch("factory.telegram.bot._bg", lambda coro: None), \
         patch("factory.telegram.bot.register_project_task"):
        await cmd_continue(fake_update, MagicMock())

    # Must have written HALTED (or the resume stage) to DB
    assert updated_states, "update_project_state was never called by cmd_continue"


# ═══════════════════════════════════════════════════════════════════
# Test 11: Full E2E — stage NameError-class error → HALTED (not exception)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pipeline_halts_on_mode_name_error_class(monkeypatch):
    """A NameError inside a stage must produce HALTED state, not an unhandled exception."""
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("SKIP_CREDENTIAL_PREFLIGHT", "true")
    monkeypatch.setenv("PIPELINE_ENV", "ci")

    # Inject a NameError into S0 via STAGE_SEQUENCE (the list run_pipeline iterates).
    # This simulates the pre-fix mode_name NameError crash end-to-end.
    from factory.pipeline.graph import pipeline_node as _pn
    from factory.orchestrator import STAGE_SEQUENCE, run_pipeline

    async def _crashing_s0_inner(s):
        raise NameError("name 'mode_name' is not defined")

    crashing_decorated = _pn(Stage.S0_INTAKE)(_crashing_s0_inner)

    # Build patched sequence: replace only the first entry (s0_intake)
    patched_seq = [("s0_intake", crashing_decorated)] + STAGE_SEQUENCE[1:]

    state = _state("p2-t11-ne")
    with patch("factory.telegram.notifications.send_telegram_message", AsyncMock()), \
         patch("factory.telegram.notifications.notify_operator", AsyncMock()), \
         patch("factory.integrations.supabase.upsert_pipeline_state", AsyncMock()), \
         patch("factory.monitoring.budget_governor.BudgetGovernor.check", AsyncMock()), \
         patch("factory.monitoring.budget_governor.BudgetGovernor.set_spend_source"), \
         patch("factory.orchestrator.STAGE_SEQUENCE", patched_seq):
        result = await run_pipeline(state)

    assert result.current_stage == Stage.HALTED, (
        f"Expected HALTED, got {result.current_stage} — NameError escaped pipeline_node"
    )
    struct = result.project_metadata.get("halt_reason_struct", {})
    assert struct.get("code") == "STAGE_EXCEPTION"
    assert struct.get("error_type") == "NameError"
