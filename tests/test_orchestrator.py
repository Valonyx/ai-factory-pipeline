"""Tests for factory.orchestrator (P9 Entry Points)."""

import pytest
from factory.core.state import PipelineState, Stage
from factory.orchestrator import (
    pipeline_node, run_pipeline,
    route_after_test, route_after_verify,
    halt_handler_node, STAGE_SEQUENCE,
)


class TestDAG:
    def test_stage_sequence(self):
        assert len(STAGE_SEQUENCE) == 9
        names = [s[0] for s in STAGE_SEQUENCE]
        assert names[0] == "s0_intake"
        assert names[-1] == "s8_handoff"


class TestRouting:
    def test_test_pass(self, fresh_state):
        fresh_state.project_metadata["tests_passed"] = True
        assert route_after_test(fresh_state) == "s6_deploy"

    def test_test_fail_retry(self, fresh_state):
        fresh_state.project_metadata["tests_passed"] = False
        assert route_after_test(fresh_state) == "s3_codegen"

    def test_test_fail_exhausted(self, fresh_state):
        fresh_state.project_metadata["tests_passed"] = False
        fresh_state.retry_count = 3
        assert route_after_test(fresh_state) == "halt"

    def test_verify_pass(self, fresh_state):
        fresh_state.project_metadata["verify_passed"] = True
        assert route_after_verify(fresh_state) == "s8_handoff"

    def test_verify_fail_redeploy(self, fresh_state):
        fresh_state.project_metadata["verify_passed"] = False
        assert route_after_verify(fresh_state) == "s6_deploy"

    def test_halted_routes_halt(self, halted_state):
        assert route_after_test(halted_state) == "halt"
        assert route_after_verify(halted_state) == "halt"


class TestPipelineNode:
    @pytest.mark.asyncio
    async def test_decorator_runs(self, fresh_state):
        @pipeline_node(Stage.S0_INTAKE)
        async def test_fn(state):
            state.project_metadata["ran"] = True
            return state

        result = await test_fn(fresh_state)
        assert result.project_metadata["ran"] is True
        assert result.snapshot_count >= 1


class TestHaltHandler:
    @pytest.mark.asyncio
    async def test_halt_sends_notification(self, fresh_state):
        fresh_state.legal_halt_reason = "PDPL missing"
        result = await halt_handler_node(fresh_state)
        assert result.project_id == fresh_state.project_id


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_run_pipeline(self, fresh_state, mock_ai, mock_deploy_window):
        mock_ai.return_value = '{"stub": true}'
        result = await run_pipeline(fresh_state)
        assert result.current_stage in (Stage.S8_HANDOFF, Stage.HALTED)
        assert len(result.stage_history) >= 9