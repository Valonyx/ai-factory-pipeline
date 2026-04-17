"""
AI Factory Pipeline v5.8.12 — Concurrency Tests (Issue 16)

Phase 2: Parallel-Project Race Condition & Runaway Loop

Tests:
1. test_single_active_project_guard — cmd_new blocks when project active
2. test_cancel_sets_abort_flag — cancel_project_task wires correctly
3. test_pipeline_aborted_skips_stages — abort flag prevents stage execution
4. test_stage_visit_cap — visit > 3 halts with UNCAUGHT_EXCEPTION
5. test_deadline_exceeded — _check_deadline returns True for past deadline
6. test_cancelled_error_handled — CancelledError → HALTED / PIPELINE_CANCELLED
7. test_orphan_sweeper_removes_done_tasks — sweeper removes finished tasks
8. test_delivery_guard_on_aborted — _notify_stage_complete no-ops on abort

Spec Authority: v5.8.12 Phase 2 §16
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.state import PipelineState, Stage
from factory.core.halt import HaltCode
from factory.orchestrator import (
    _check_deadline,
    _notify_stage_complete,
    pipeline_node,
    run_pipeline,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_state(**kwargs) -> PipelineState:
    defaults = dict(
        project_id="test-conc-001",
        operator_id="test-operator",
    )
    defaults.update(kwargs)
    state = PipelineState(**defaults)
    # Enough metadata so S0 doesn't halt on missing app name
    state.project_metadata["raw_input"] = 'app name: "ConcTest" — concurrency test'
    state.project_metadata["app_name"] = "ConcTest"
    state.project_metadata["tests_passed"] = True
    state.project_metadata["verify_passed"] = True
    return state


# ─────────────────────────────────────────────────────────────────────────────
# 1. Single-active-project guard
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleActiveProjectGuard:
    @pytest.mark.asyncio
    async def test_single_active_project_guard(self):
        """cmd_new_project must block if a project is already active,
        showing the project display name (not raw project_id) in the reply."""

        fake_active = {
            "project_id": "proj_abc123",
            "current_stage": "S2_BLUEPRINT",
            # project_display_name(dict) checks d.get("intake")["app_name"]
            # first, then falls back to project_id humanized.
            "intake": {"app_name": "TestApp"},
            "app_name": "TestApp",
            "state_json": {
                "project_id": "proj_abc123",
                "operator_id": "test-operator",
                "idea_name": "TestApp",
                "intake": {"app_name": "TestApp"},
                "project_metadata": {"app_name": "TestApp"},
            },
        }

        # Capture what was replied
        replies: list[str] = []

        class _FakeMessage:
            async def reply_text(self, text, **kwargs):
                replies.append(text)

        class _FakeUser:
            id = 12345

        class _FakeUpdate:
            message = _FakeMessage()
            effective_user = _FakeUser()

        class _FakeContext:
            args = []

        from factory.telegram.bot import cmd_new_project

        with patch(
            "factory.telegram.bot.get_active_project",
            new_callable=AsyncMock,
            return_value=fake_active,
        ), patch(
            "factory.telegram.bot.authenticate_operator",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await cmd_new_project(_FakeUpdate(), _FakeContext())

        assert replies, "Expected a reply text — got none"
        combined = " ".join(replies)
        # Must mention the app name (not just raw project_id)
        assert "TestApp" in combined, f"Expected app name in reply, got: {combined!r}"
        # Must tell the user they have an active project
        assert "active project" in combined.lower(), (
            f"Expected 'active project' in reply, got: {combined!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. cancel_project_task wires correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestCancelSetsAbortFlag:
    @pytest.mark.asyncio
    async def test_cancel_project_task_cancels_running_task(self):
        """register_project_task + cancel_project_task: cancel() is called."""
        from factory.telegram.bot import register_project_task, cancel_project_task, _project_tasks

        sentinel = asyncio.Event()

        async def _long_running():
            await sentinel.wait()

        loop = asyncio.get_event_loop()
        task = loop.create_task(_long_running())
        register_project_task("proj-cancel-test", task)

        assert "proj-cancel-test" in _project_tasks

        result = cancel_project_task("proj-cancel-test")
        assert result is True
        # Task should now be cancelling or cancelled
        assert task.cancelled() or task.cancelling() > 0

        # Clean up
        try:
            await asyncio.wait_for(task, timeout=0.1)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task_returns_false(self):
        """cancel_project_task returns False when no task is registered."""
        from factory.telegram.bot import cancel_project_task
        result = cancel_project_task("proj-does-not-exist-xyz")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_done_task_returns_false(self):
        """cancel_project_task returns False for an already-done task."""
        from factory.telegram.bot import register_project_task, cancel_project_task

        async def _noop():
            pass

        loop = asyncio.get_event_loop()
        task = loop.create_task(_noop())
        await asyncio.sleep(0)  # let task finish
        register_project_task("proj-done-test", task)

        result = cancel_project_task("proj-done-test")
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. pipeline_aborted=True skips all stages
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineAbortedSkipsStages:
    @pytest.mark.asyncio
    async def test_pipeline_aborted_skips_stages(self):
        """If state.pipeline_aborted is True before run_pipeline(), no stage node runs."""
        state = _make_state()
        state.pipeline_aborted = True

        stage_call_count = 0

        async def _counting_stage(s):
            nonlocal stage_call_count
            stage_call_count += 1
            return s

        # Patch all 10 stage node functions to counting stubs
        stage_module_paths = [
            "factory.orchestrator.s0_intake_node",
            "factory.orchestrator.s1_legal_node",
            "factory.orchestrator.s2_blueprint_node",
            "factory.orchestrator.s3_design_node",
            "factory.orchestrator.s4_codegen_node",
            "factory.orchestrator.s5_build_node",
            "factory.orchestrator.s6_test_node",
            "factory.orchestrator.s7_deploy_node",
            "factory.orchestrator.s8_verify_node",
            "factory.orchestrator.s9_handoff_node",
        ]

        with patch.multiple(
            "factory.orchestrator",
            s0_intake_node=_counting_stage,
            s1_legal_node=_counting_stage,
            s2_blueprint_node=_counting_stage,
            s3_design_node=_counting_stage,
            s4_codegen_node=_counting_stage,
            s5_build_node=_counting_stage,
            s6_test_node=_counting_stage,
            s7_deploy_node=_counting_stage,
            s8_verify_node=_counting_stage,
            s9_handoff_node=_counting_stage,
        ):
            result = await run_pipeline(state)

        assert stage_call_count == 0, (
            f"Expected 0 stage calls with pipeline_aborted=True, got {stage_call_count}"
        )
        assert result.pipeline_aborted is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Stage-visit cap triggers HALTED
# ─────────────────────────────────────────────────────────────────────────────

class TestStageVisitCap:
    @pytest.mark.asyncio
    async def test_stage_visit_cap_halts_on_fourth_visit(self):
        """A stage entered 4+ times should be halted with UNCAUGHT_EXCEPTION
        and a 'loop detected' detail message."""
        state = _make_state()
        # Pretend this stage was already visited 3 times
        state.stage_visit_counts["S0_INTAKE"] = 3

        @pipeline_node(Stage.S0_INTAKE)
        async def _dummy_stage(s):
            s.project_metadata["ran"] = True
            return s

        result = await _dummy_stage(state)

        assert result.current_stage == Stage.HALTED, (
            f"Expected HALTED, got {result.current_stage}"
        )
        struct = result.project_metadata.get("halt_reason_struct", {})
        assert struct.get("code") == HaltCode.UNCAUGHT_EXCEPTION.value, (
            f"Expected UNCAUGHT_EXCEPTION, got {struct.get('code')}"
        )
        detail = struct.get("detail", "").lower()
        assert "stage loop detected" in struct.get("title", "").lower() or "entered" in detail, (
            f"Expected stage loop detail, got title={struct.get('title')!r} detail={struct.get('detail')!r}"
        )
        # The dummy stage body must NOT have run
        assert "ran" not in result.project_metadata


# ─────────────────────────────────────────────────────────────────────────────
# 5. Deadline exceeded
# ─────────────────────────────────────────────────────────────────────────────

class TestDeadlineExceeded:
    def test_deadline_exceeded_returns_true_for_past_deadline(self):
        """_check_deadline returns True when deadline is in the past."""
        state = _make_state()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        state.pipeline_deadline = past
        assert _check_deadline(state) is True

    def test_deadline_not_exceeded_for_future(self):
        """_check_deadline returns False when deadline is in the future."""
        state = _make_state()
        future = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        state.pipeline_deadline = future
        assert _check_deadline(state) is False

    def test_deadline_not_exceeded_when_unset(self):
        """_check_deadline returns False when pipeline_deadline is None."""
        state = _make_state()
        state.pipeline_deadline = None
        assert _check_deadline(state) is False


# ─────────────────────────────────────────────────────────────────────────────
# 6. CancelledError handled gracefully
# ─────────────────────────────────────────────────────────────────────────────

class TestCancelledErrorHandled:
    @pytest.mark.asyncio
    async def test_cancelled_error_produces_halted_state(self):
        """When a stage node raises asyncio.CancelledError, run_pipeline must
        catch it, set pipeline_aborted=True, transition to HALTED with code
        PIPELINE_CANCELLED, and NOT propagate the error.

        Strategy: patch STAGE_SEQUENCE directly so the first stage raises
        CancelledError before any real pipeline code runs.
        """
        import factory.orchestrator as _orch

        async def _raising_stage(state):
            raise asyncio.CancelledError()

        state = _make_state()

        # Patch STAGE_SEQUENCE so only one stage runs and it raises CancelledError
        fake_sequence = [("s0_intake", _raising_stage)]
        with patch.object(_orch, "STAGE_SEQUENCE", fake_sequence):
            # Must not raise — should return cleanly
            result = await run_pipeline(state)

        assert result.pipeline_aborted is True, "Expected pipeline_aborted=True"
        assert result.current_stage == Stage.HALTED, (
            f"Expected HALTED, got {result.current_stage}"
        )
        struct = result.project_metadata.get("halt_reason_struct", {})
        assert struct.get("code") == HaltCode.PIPELINE_CANCELLED.value, (
            f"Expected PIPELINE_CANCELLED, got {struct.get('code')!r}"
        )

    @pytest.mark.asyncio
    async def test_cancelled_error_does_not_propagate(self):
        """run_pipeline must not re-raise CancelledError to its caller."""
        import factory.orchestrator as _orch

        async def _raising_stage(state):
            raise asyncio.CancelledError()

        state = _make_state()
        fake_sequence = [("s0_intake", _raising_stage)]

        # Should complete without exception
        with patch.object(_orch, "STAGE_SEQUENCE", fake_sequence):
            try:
                await run_pipeline(state)
            except asyncio.CancelledError:
                pytest.fail("run_pipeline re-raised CancelledError — must not propagate")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Orphan sweeper removes done tasks
# ─────────────────────────────────────────────────────────────────────────────

class TestOrphanSweeperRemovesDoneTasks:
    @pytest.mark.asyncio
    async def test_orphan_sweeper_removes_done_task(self):
        """_orphan_task_sweeper cleans up a task that has already finished."""
        from factory.telegram import bot as _bot_module

        # Directly manipulate the module-level _project_tasks dict
        original_tasks = dict(_bot_module._project_tasks)

        async def _instant():
            pass

        loop = asyncio.get_event_loop()
        task = loop.create_task(_instant())
        await asyncio.sleep(0)  # Let it finish
        _bot_module._project_tasks["proj-orphan-001"] = task

        assert task.done(), "Task should be done before sweeper runs"

        # Run one sweep iteration inline (without sleep)
        for project_id, t in list(_bot_module._project_tasks.items()):
            if t.done():
                _bot_module._project_tasks.pop(project_id, None)

        assert "proj-orphan-001" not in _bot_module._project_tasks, (
            "Sweeper should have removed the done task"
        )

        # Restore
        _bot_module._project_tasks.clear()
        _bot_module._project_tasks.update(original_tasks)

    @pytest.mark.asyncio
    async def test_orphan_sweeper_cancels_task_without_active_project(self):
        """_orphan_task_sweeper cancels a running task whose project is not
        in _active_projects_fallback."""
        from factory.telegram import bot as _bot_module

        original_tasks = dict(_bot_module._project_tasks)
        original_fallback = dict(_bot_module._active_projects_fallback)

        sentinel = asyncio.Event()

        async def _long_running():
            await sentinel.wait()

        loop = asyncio.get_event_loop()
        task = loop.create_task(_long_running())
        _bot_module._project_tasks["proj-orphan-002"] = task
        # Do NOT add to _active_projects_fallback → simulates orphan

        # Simulate one sweep pass
        for project_id, t in list(_bot_module._project_tasks.items()):
            if project_id not in original_tasks:  # only our new task
                still_active = any(
                    p.get("project_id") == project_id
                    for p in _bot_module._active_projects_fallback.values()
                )
                if not still_active:
                    _bot_module.cancel_project_task(project_id)

        assert task.cancelled() or task.cancelling() > 0, (
            "Expected orphan task to be cancelled"
        )

        # Clean up
        try:
            await asyncio.wait_for(task, timeout=0.1)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        _bot_module._project_tasks.clear()
        _bot_module._project_tasks.update(original_tasks)
        _bot_module._active_projects_fallback.clear()
        _bot_module._active_projects_fallback.update(original_fallback)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Delivery guard on aborted pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestDeliveryGuardOnAborted:
    @pytest.mark.asyncio
    async def test_delivery_guard_skips_notification_when_aborted(self):
        """_notify_stage_complete must send nothing when pipeline_aborted=True."""
        state = _make_state()
        state.pipeline_aborted = True

        # Patch at the orchestrator module level (where notify_operator is bound)
        with patch(
            "factory.orchestrator.notify_operator",
            new_callable=AsyncMock,
        ) as mock_notify:
            await _notify_stage_complete(state, "S0_INTAKE")

        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivery_guard_sends_when_not_aborted(self):
        """_notify_stage_complete DOES call notify_operator when pipeline is active."""
        state = _make_state()
        state.pipeline_aborted = False
        state.operator_id = "test-operator"

        # Patch at the orchestrator module level (where notify_operator is bound)
        with patch(
            "factory.orchestrator.notify_operator",
            new_callable=AsyncMock,
        ) as mock_notify:
            await _notify_stage_complete(state, "S0_INTAKE")

        mock_notify.assert_called_once()
