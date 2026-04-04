"""Tests for factory.pipeline (P2 Pipeline Stages S0-S8)."""

import pytest
from factory.core.state import PipelineState, Stage
from factory.pipeline.s0_intake import s0_intake_node as s0_intake
from factory.pipeline.s1_legal import s1_legal_node as s1_legal_gate
from factory.pipeline.s2_blueprint import s2_blueprint_node as s2_blueprint
from factory.pipeline.s3_codegen import s3_codegen_node as s3_codegen
from factory.pipeline.s4_build import s4_build_node as s4_build
from factory.pipeline.s5_test import s5_test_node as s5_test
from factory.pipeline.s6_deploy import s6_deploy_node as s6_deploy
from factory.pipeline.s7_verify import s7_verify_node as s7_verify
from factory.pipeline.s8_handoff import s8_handoff_node as s8_handoff


class TestS0Intake:
    @pytest.mark.asyncio
    async def test_intake_stub(self, fresh_state, mock_ai):
        result = await s0_intake(fresh_state)
        assert isinstance(result, PipelineState)
        assert result.s0_output is not None or result.project_metadata.get("raw_input")


class TestS1Legal:
    @pytest.mark.asyncio
    async def test_legal_gate_stub(self, fresh_state, mock_ai):
        fresh_state.s0_output = {
            "app_category": "e-commerce",
            "has_payments": True,
            "has_user_accounts": True,
        }
        result = await s1_legal_gate(fresh_state)
        assert isinstance(result, PipelineState)


class TestS3Codegen:
    @pytest.mark.asyncio
    async def test_codegen_stub(self, fresh_state, mock_ai):
        fresh_state.s2_output = {"screens": [], "data_model": []}
        result = await s3_codegen(fresh_state)
        assert isinstance(result, PipelineState)


class TestS4Build:
    @pytest.mark.asyncio
    async def test_build_stub(self, fresh_state, mock_ai):
        result = await s4_build(fresh_state)
        assert isinstance(result, PipelineState)


class TestS5Test:
    @pytest.mark.asyncio
    async def test_test_stub(self, fresh_state, mock_ai):
        fresh_state.s3_output = {"generated_files": {"test_app.py": "def test_main(): pass"}}
        result = await s5_test(fresh_state)
        assert isinstance(result, PipelineState)


class TestS6Deploy:
    @pytest.mark.asyncio
    async def test_deploy_stub(self, fresh_state, mock_ai):
        result = await s6_deploy(fresh_state)
        assert isinstance(result, PipelineState)


class TestS7Verify:
    @pytest.mark.asyncio
    async def test_verify_stub(self, fresh_state, mock_ai):
        result = await s7_verify(fresh_state)
        assert isinstance(result, PipelineState)


class TestS8Handoff:
    @pytest.mark.asyncio
    async def test_handoff_stub(self, fresh_state, mock_ai):
        result = await s8_handoff(fresh_state)
        assert isinstance(result, PipelineState)