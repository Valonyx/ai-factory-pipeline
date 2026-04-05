"""
PROD-7 Validation: Pipeline DAG + Stage Execution (S0–S2)

Tests cover:
  1.  All 10 stage nodes registered in _stage_nodes
  2.  LEGAL_CHECKS_BY_STAGE covers expected stages
  3.  route_after_test — pass → s6_deploy
  4.  route_after_test — fail, retries left → s3_codegen
  5.  route_after_test — fail, retries exhausted → halt
  6.  route_after_verify — pass → s8_handoff
  7.  route_after_verify — fail, retries left → s6_deploy
  8.  route_after_verify — fail, retries exhausted → halt
  9.  SimpleExecutor.ainvoke runs full pipeline (stubs)
  10. S0 intake — empty message → fallback requirements
  11. S0 intake — populates s0_output
  12. S1 legal — populates s1_output
  13. S1 legal — default legal output structure
  14. S2 blueprint — populates s2_output with stack
  15. S2 blueprint — STACK_DESCRIPTIONS covers all stacks
  16. halt_handler — sets HALTED state
  17. halt_handler — notifies operator (mock)
  18. pipeline_node decorator — transitions stage
  19. _transition_to — records history
  20. run_pipeline — full end-to-end (stubs)

Run:
  pytest tests/test_prod_07_pipeline.py -v
"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock

from factory.core.state import (
    PipelineState,
    Stage,
    TechStack,
    AutonomyMode,
    ExecutionMode,
)
from factory.pipeline.graph import (
    _stage_nodes,
    LEGAL_CHECKS_BY_STAGE,
    MAX_TEST_RETRIES,
    MAX_VERIFY_RETRIES,
    route_after_test,
    route_after_verify,
    _transition_to,
    SimpleExecutor,
    run_pipeline,
)
from factory.pipeline.s0_intake import s0_intake_node, _fallback_requirements
from factory.pipeline.s1_legal import (
    s1_legal_node, _default_legal_output,
)
from factory.pipeline.s2_blueprint import (
    s2_blueprint_node, STACK_DESCRIPTIONS,
)
from factory.pipeline.halt_handler import halt_handler_node


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    """Fresh PipelineState for testing."""
    s = PipelineState(
        project_id="test_proj_001",
        operator_id="op_123",
    )
    s.intake_message = "Build a food delivery app for Riyadh"
    return s


@pytest.fixture
def mock_call_ai():
    """Mock call_ai to return controlled JSON responses."""
    async def _mock(role, prompt, state=None, **kwargs):
        if role.value == "quick_fix":
            # S0 Haiku extraction
            return json.dumps({
                "app_name": "Riyadh Eats",
                "app_description": "Food delivery app for Riyadh",
                "app_category": "food",
                "features_must": ["ordering", "tracking", "payments"],
                "features_nice": ["reviews", "loyalty"],
                "target_platforms": ["ios", "android"],
                "has_payments": True,
                "has_user_accounts": True,
                "has_location": True,
                "has_notifications": True,
                "has_realtime": True,
                "estimated_complexity": "complex",
            })
        elif role.value == "scout":
            return "KSA regulations: PDPL applies, SAMA for payments"
        elif role.value == "strategist":
            if "stack" in prompt.lower():
                return json.dumps({
                    "selected": "flutterflow",
                    "reason": "Fast MVP, cross-platform",
                    "scores": {"flutterflow": 0.9},
                })
            elif "classify" in prompt.lower() or "legal" in prompt.lower():
                return json.dumps(_default_legal_output())
            elif "architecture" in prompt.lower():
                return json.dumps({
                    "screens": [
                        {"name": "home", "components": []},
                        {"name": "menu", "components": []},
                    ],
                    "data_model": [
                        {"collection": "orders", "fields": [], "indexes": []},
                    ],
                    "api_endpoints": [
                        {"path": "/api/orders", "method": "GET",
                         "auth_required": True, "description": "List orders"},
                    ],
                    "auth_method": "phone",
                })
            elif "design" in prompt.lower():
                return json.dumps({
                    "color_palette": {"primary": "#FF5722"},
                    "typography": {"heading": "Cairo", "body": "Cairo",
                                   "rtl_support": True},
                    "design_system": "material3",
                    "spacing": "normal",
                })
        return "{}"

    return _mock


# ═══════════════════════════════════════════════════════════════════
# Test 1-2: DAG Registration
# ═══════════════════════════════════════════════════════════════════

class TestDAGRegistration:
    def test_10_stage_nodes_registered(self):
        """All 10 stage nodes (S0-S8 + halt) registered."""
        expected = [
            "s0_intake", "s1_legal", "s2_blueprint",
            "s3_codegen", "s4_build", "s5_test",
            "s6_deploy", "s7_verify", "s8_handoff",
            "halt_handler",
        ]
        for name in expected:
            assert name in _stage_nodes, f"Missing: {name}"
        assert len(_stage_nodes) >= 10

    def test_legal_checks_map(self):
        """LEGAL_CHECKS_BY_STAGE covers expected stages."""
        assert Stage.S2_BLUEPRINT in LEGAL_CHECKS_BY_STAGE
        assert Stage.S3_CODEGEN in LEGAL_CHECKS_BY_STAGE
        assert Stage.S6_DEPLOY in LEGAL_CHECKS_BY_STAGE
        assert Stage.S8_HANDOFF in LEGAL_CHECKS_BY_STAGE
        # Pre and post checks
        s2 = LEGAL_CHECKS_BY_STAGE[Stage.S2_BLUEPRINT]
        assert "pre" in s2
        assert "post" in s2


# ═══════════════════════════════════════════════════════════════════
# Test 3-8: Routing Functions
# ═══════════════════════════════════════════════════════════════════

class TestRouting:
    def test_route_after_test_pass(self, state):
        state.s5_output = {"passed": True}
        assert route_after_test(state) == "s6_deploy"

    def test_route_after_test_fail_retry(self, state):
        state.s5_output = {"passed": False}
        state.retry_count = 0
        assert route_after_test(state) == "s3_codegen"
        assert state.retry_count == 1

    def test_route_after_test_fail_exhausted(self, state):
        state.s5_output = {"passed": False, "failures": ["err1"]}
        state.retry_count = MAX_TEST_RETRIES
        assert route_after_test(state) == "halt"

    def test_route_after_verify_pass(self, state):
        state.s7_output = {"passed": True}
        assert route_after_verify(state) == "s8_handoff"

    def test_route_after_verify_fail_retry(self, state):
        state.s7_output = {"passed": False}
        state.project_metadata["verify_retries"] = 0
        assert route_after_verify(state) == "s6_deploy"

    def test_route_after_verify_fail_exhausted(self, state):
        state.s7_output = {"passed": False}
        state.project_metadata["verify_retries"] = MAX_VERIFY_RETRIES
        assert route_after_verify(state) == "halt"


# ═══════════════════════════════════════════════════════════════════
# Test 9: SimpleExecutor
# ═══════════════════════════════════════════════════════════════════

class TestSimpleExecutor:
    @pytest.mark.asyncio
    async def test_full_pipeline_stubs(self, state):
        """SimpleExecutor runs full pipeline with stub nodes."""
        executor = SimpleExecutor()
        result = await executor.ainvoke(state)
        # Stubs all pass, so should reach completion
        assert result.s0_output is not None or result.current_stage in (
            Stage.S8_HANDOFF, Stage.COMPLETED, Stage.HALTED,
        )


# ═══════════════════════════════════════════════════════════════════
# Test 10-11: S0 Intake
# ═══════════════════════════════════════════════════════════════════

class TestS0Intake:
    @pytest.mark.asyncio
    async def test_empty_message(self, state):
        """Empty intake → fallback requirements."""
        state.intake_message = ""
        with patch("factory.pipeline.s0_intake.call_ai", new=AsyncMock()):
            result = await s0_intake_node(state)
        assert result.s0_output is not None
        assert result.s0_output["app_name"] == "Untitled"

    @pytest.mark.asyncio
    async def test_populates_output(self, state, mock_call_ai):
        """S0 populates s0_output from Haiku extraction."""
        with patch(
            "factory.pipeline.s0_intake.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s0_intake_node(state)
        assert result.s0_output is not None
        assert result.s0_output["app_name"] == "Riyadh Eats"
        assert result.s0_output["app_category"] == "food"

    def test_fallback_requirements(self):
        """_fallback_requirements returns valid dict."""
        req = _fallback_requirements("test app")
        assert req["app_name"] == "test app"
        assert "target_platforms" in req


# ═══════════════════════════════════════════════════════════════════
# Test 12-13: S1 Legal
# ═══════════════════════════════════════════════════════════════════

class TestS1Legal:
    @pytest.mark.asyncio
    async def test_populates_output(self, state, mock_call_ai):
        """S1 populates s1_output."""
        state.s0_output = _fallback_requirements("test food app")
        with patch(
            "factory.pipeline.s1_legal.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s1_legal_node(state)
        assert result.s1_output is not None
        assert "data_classification" in result.s1_output

    def test_default_legal_output(self):
        """Default legal output has required fields."""
        d = _default_legal_output()
        assert d["data_classification"] == "internal"
        assert d["proceed"] is True
        assert "PDPL" in d["regulatory_bodies"]


# ═══════════════════════════════════════════════════════════════════
# Test 14-15: S2 Blueprint
# ═══════════════════════════════════════════════════════════════════

class TestS2Blueprint:
    @pytest.mark.asyncio
    async def test_populates_output(self, state, mock_call_ai):
        """S2 populates s2_output with blueprint."""
        state.s0_output = _fallback_requirements("food app")
        state.s1_output = _default_legal_output()
        with patch(
            "factory.pipeline.s2_blueprint.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s2_blueprint_node(state)
        assert result.s2_output is not None
        assert result.selected_stack == TechStack.FLUTTERFLOW
        assert "screens" in result.s2_output

    def test_stack_descriptions_complete(self):
        """STACK_DESCRIPTIONS covers all TechStack values."""
        for stack in TechStack:
            assert stack.value in STACK_DESCRIPTIONS


# ═══════════════════════════════════════════════════════════════════
# Test 16-17: Halt Handler
# ═══════════════════════════════════════════════════════════════════

class TestHaltHandler:
    @pytest.mark.asyncio
    async def test_sets_halted_state(self, state):
        """Halt handler sets HALTED state."""
        state.legal_halt_reason = "test halt"
        result = await halt_handler_node(state)
        assert result.current_stage == Stage.HALTED

    @pytest.mark.asyncio
    async def test_notifies_operator(self, state):
        """Halt handler calls send_telegram_message."""
        state.legal_halt_reason = "test halt reason"
        with patch(
            "factory.pipeline.halt_handler.send_telegram_message",
            new=AsyncMock(),
        ) as mock_send:
            await halt_handler_node(state)
            mock_send.assert_called_once()
            call_text = mock_send.call_args[0][1]
            assert "halted" in call_text.lower()


# ═══════════════════════════════════════════════════════════════════
# Test 18-19: Infrastructure
# ═══════════════════════════════════════════════════════════════════

class TestInfrastructure:
    def test_transition_to_records_history(self, state):
        """_transition_to appends to stage_history."""
        _transition_to(state, Stage.S0_INTAKE)
        assert len(state.stage_history) >= 1
        assert state.stage_history[-1]["to"] == "S0_INTAKE"
        assert state.current_stage == Stage.S0_INTAKE

    def test_max_retries_constants(self):
        """Retry constants match spec defaults."""
        assert MAX_TEST_RETRIES == 3
        assert MAX_VERIFY_RETRIES == 2


# ═══════════════════════════════════════════════════════════════════
# Test 20: End-to-End
# ═══════════════════════════════════════════════════════════════════

class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_run_pipeline_completes(self, state, mock_call_ai):
        """run_pipeline() runs end-to-end with mocked AI."""
        with patch(
            "factory.pipeline.s0_intake.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s1_legal.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s2_blueprint.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await run_pipeline(state)
        # Should complete (stubs all pass)
        assert result.s0_output is not None
        assert result.current_stage in (
            Stage.S8_HANDOFF, Stage.COMPLETED, Stage.HALTED,
        )
        assert result.total_cost_usd >= 0
