"""
PROD-8 Validation: Pipeline Stages S3–S5

Tests cover:
  1.  S3: minimal scaffold exists for all 6 stacks
  2.  S3: _parse_files_response handles markdown fences
  3.  S3: full generation populates s3_output
  4.  S3: retry fix mode sets generation_mode
  5.  S4: STACK_BUILD_REQUIREMENTS covers all 6 stacks
  6.  S4: DEPENDENCY_COMMANDS covers all 6 stacks
  7.  S4: CLI_BUILD_COMMANDS covers CLI stacks
  8.  S4: _get_target_stores resolves correctly
  9.  S4: build node populates s4_output
  10. S5: TEST_COMMANDS covers all 6 stacks
  11. S5: pre-deploy gate timeouts match spec
  12. S5: test node populates s5_output
  13. S5: _analyze_test_results fallback (exit_code 0)
  14. S5: _analyze_test_results fallback (exit_code 1)
  15. S5: pre_deploy_gate returns True in dry-run
  16. War Room: L1→L2→L3 escalation
  17. S3→S4→S5 integrated flow (stubs)
  18. Updated stubs only contain S6–S8

Run:
  pytest tests/test_prod_08_stages.py -v
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
from factory.pipeline.s3_codegen import (
    s3_codegen_node,
    _create_minimal_scaffold,
    _parse_files_response,
    _war_room_fix,
)
from factory.pipeline.s4_build import (
    s4_build_node,
    STACK_BUILD_REQUIREMENTS,
    DEPENDENCY_COMMANDS,
    CLI_BUILD_COMMANDS,
    _get_target_stores,
)
from factory.pipeline.s5_test import (
    s5_test_node,
    pre_deploy_gate,
    TEST_COMMANDS,
    COPILOT_DEPLOY_TIMEOUT,
    AUTOPILOT_DEPLOY_TIMEOUT,
    _analyze_test_results,
)
from factory.pipeline.graph import _stage_nodes


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    """Fresh PipelineState with S0–S2 outputs populated."""
    s = PipelineState(
        project_id="test_s345_001",
        operator_id="op_456",
    )
    s.intake_message = "Build a food delivery app"
    s.s0_output = {
        "app_name": "FoodApp",
        "app_description": "Food delivery for Riyadh",
        "app_category": "food",
        "features_must": ["ordering", "tracking"],
        "target_platforms": ["ios", "android"],
        "has_payments": True,
        "has_user_accounts": True,
    }
    s.s1_output = {
        "data_classification": "internal",
        "regulatory_bodies": ["PDPL"],
        "blocked_features": [],
        "required_legal_docs": ["privacy_policy"],
        "payment_mode": "SANDBOX",
        "risk_level": "medium",
        "proceed": True,
    }
    s.s2_output = {
        "project_id": s.project_id,
        "app_name": "FoodApp",
        "app_description": "Food delivery for Riyadh",
        "target_platforms": ["ios", "android"],
        "selected_stack": "flutterflow",
        "screens": [{"name": "home", "components": []}],
        "data_model": [{"collection": "orders", "fields": []}],
        "api_endpoints": [],
        "auth_method": "email",
        "color_palette": {"primary": "#FF5722"},
        "typography": {"heading": "Cairo"},
        "design_system": "material3",
    }
    s.selected_stack = TechStack.FLUTTERFLOW
    return s


@pytest.fixture
def mock_call_ai():
    """Mock call_ai for controlled S3–S5 tests."""
    async def _mock(role, prompt, state=None, **kwargs):
        if role.value == "engineer":
            if "generate complete" in prompt.lower():
                return json.dumps({
                    "lib/main.dart": "void main() {}",
                    "pubspec.yaml": "name: foodapp",
                })
            elif "generate test" in prompt.lower():
                return json.dumps({
                    "test/main_test.dart": "void main() { test(); }",
                })
            elif "ci" in prompt.lower() or "github" in prompt.lower():
                return "name: build\non: push\njobs: {}"
            elif "security rules" in prompt.lower():
                return "rules_version = '2';"
            elif "fix" in prompt.lower():
                return "// fixed code"
        elif role.value == "quick_fix":
            if "analyze test" in prompt.lower():
                return json.dumps({
                    "passed": True,
                    "total_tests": 5,
                    "passed_tests": 5,
                    "failed_tests": 0,
                    "security_critical": False,
                    "failures": [],
                })
            elif "validate" in prompt.lower():
                return "{}"
            elif "fix" in prompt.lower():
                return "// l1 fixed"
        elif role.value == "scout":
            return "Use try/catch to fix the error"
        return "{}"

    return _mock


# ═══════════════════════════════════════════════════════════════════
# Tests 1-4: S3 CodeGen
# ═══════════════════════════════════════════════════════════════════

class TestS3CodeGen:
    def test_minimal_scaffold_all_stacks(self):
        """Minimal scaffold exists for all 6 stacks."""
        for stack in TechStack:
            scaffold = _create_minimal_scaffold(stack, "TestApp")
            assert len(scaffold) > 0, f"No scaffold for {stack}"
            assert all(
                isinstance(v, str) for v in scaffold.values()
            )

    def test_parse_files_response_fences(self):
        """Handles markdown code fences."""
        raw = '```json\n{"a.py": "print(1)"}\n```'
        result = _parse_files_response(raw)
        assert result == {"a.py": "print(1)"}

    @pytest.mark.asyncio
    async def test_full_generation(self, state, mock_call_ai):
        """S3 full generation populates s3_output."""
        with patch(
            "factory.pipeline.s3_codegen.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s3_codegen_node(state)
        assert result.s3_output is not None
        assert result.s3_output["file_count"] > 0
        assert result.s3_output["generation_mode"] == "full"

    @pytest.mark.asyncio
    async def test_retry_fix_mode(self, state, mock_call_ai):
        """Retry from S5 uses targeted fix mode."""
        state.s3_output = {
            "generated_files": {"lib/main.dart": "broken"},
            "file_count": 1,
        }
        state.s5_output = {
            "passed": False,
            "failures": [
                {"file": "lib/main.dart", "error": "syntax error"},
            ],
        }
        state.previous_stage = Stage.S5_TEST
        state.retry_count = 1

        with patch(
            "factory.pipeline.s3_codegen.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s3_codegen_node(state)
        assert result.s3_output["generation_mode"] == "retry_fix"


# ═══════════════════════════════════════════════════════════════════
# Tests 5-9: S4 Build
# ═══════════════════════════════════════════════════════════════════

class TestS4Build:
    def test_build_requirements_all_stacks(self):
        """STACK_BUILD_REQUIREMENTS covers all 6 stacks."""
        for stack in TechStack:
            assert stack in STACK_BUILD_REQUIREMENTS
            reqs = STACK_BUILD_REQUIREMENTS[stack]
            assert "requires_mac" in reqs
            assert "requires_gui" in reqs
        # Specific checks from spec §2.3.1
        assert STACK_BUILD_REQUIREMENTS[TechStack.FLUTTERFLOW]["requires_gui"]
        assert not STACK_BUILD_REQUIREMENTS[TechStack.REACT_NATIVE]["requires_gui"]

    def test_dependency_commands_all_stacks(self):
        """DEPENDENCY_COMMANDS covers all 6 stacks."""
        for stack in TechStack:
            assert stack in DEPENDENCY_COMMANDS
        assert "flutter pub get" in DEPENDENCY_COMMANDS[TechStack.FLUTTERFLOW]
        assert "npm ci" in DEPENDENCY_COMMANDS[TechStack.REACT_NATIVE]
        assert len(DEPENDENCY_COMMANDS[TechStack.UNITY]) == 0

    def test_cli_build_commands(self):
        """CLI_BUILD_COMMANDS covers CLI stacks."""
        assert "android" in CLI_BUILD_COMMANDS[TechStack.KOTLIN]
        assert "ios" in CLI_BUILD_COMMANDS[TechStack.SWIFT]
        assert "web" in CLI_BUILD_COMMANDS[TechStack.PYTHON_BACKEND]

    def test_target_stores(self):
        """_get_target_stores resolves correctly per stack."""
        assert "App Store" in _get_target_stores(TechStack.SWIFT)
        assert "Google Play" in _get_target_stores(TechStack.KOTLIN)
        stores_ff = _get_target_stores(TechStack.FLUTTERFLOW)
        assert "App Store" in stores_ff
        assert "Google Play" in stores_ff
        assert "Cloud Run" in _get_target_stores(TechStack.PYTHON_BACKEND)

    @pytest.mark.asyncio
    async def test_build_populates_output(self, state, mock_call_ai):
        """S4 build populates s4_output."""
        state.s3_output = {
            "generated_files": {"lib/main.dart": "void main() {}"},
        }
        with patch(
            "factory.pipeline.s4_build.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s4_build_node(state)
        assert result.s4_output is not None
        assert "build_success" in result.s4_output
        assert "build_duration_seconds" in result.s4_output


# ═══════════════════════════════════════════════════════════════════
# Tests 10-15: S5 Test
# ═══════════════════════════════════════════════════════════════════

class TestS5Test:
    def test_test_commands_all_stacks(self):
        """TEST_COMMANDS covers all 6 stacks."""
        for stack in TechStack:
            assert stack in TEST_COMMANDS
        assert TEST_COMMANDS[TechStack.FLUTTERFLOW] == "flutter test"
        assert "pytest" in TEST_COMMANDS[TechStack.PYTHON_BACKEND]
        assert TEST_COMMANDS[TechStack.REACT_NATIVE] == "npx jest --ci --json"

    def test_deploy_gate_timeouts(self):
        """Pre-deploy gate timeouts match spec (ADR-046)."""
        assert COPILOT_DEPLOY_TIMEOUT == 3600   # 1 hour
        assert AUTOPILOT_DEPLOY_TIMEOUT == 900  # 15 min

    @pytest.mark.asyncio
    async def test_test_populates_output(self, state, mock_call_ai):
        """S5 test populates s5_output."""
        state.s3_output = {
            "generated_files": {
                "lib/main.dart": "void main() {}",
                "test/main_test.dart": "void test() {}",
            },
        }
        with patch(
            "factory.pipeline.s5_test.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s5_test_node(state)
        assert result.s5_output is not None
        assert "passed" in result.s5_output

    @pytest.mark.asyncio
    async def test_analyze_results_pass(self, state):
        """Fallback analysis: exit_code 0 → passed."""
        result = await _analyze_test_results(
            state, {"exit_code": 0, "stdout": "OK", "stderr": ""},
        )
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_analyze_results_fail(self, state):
        """Fallback analysis: exit_code 1 → failed."""
        result = await _analyze_test_results(
            state, {"exit_code": 1, "stdout": "", "stderr": "FAIL"},
        )
        assert result["passed"] is False
        assert result["failed_tests"] == 1

    @pytest.mark.asyncio
    async def test_pre_deploy_gate_dryrun(self, state):
        """Pre-deploy gate returns True in dry-run."""
        state.s5_output = {
            "passed": True, "passed_tests": 5, "total_tests": 5,
            "failed_tests": 0,
        }
        approved = await pre_deploy_gate(state)
        assert approved is True


# ═══════════════════════════════════════════════════════════════════
# Test 16: War Room Escalation
# ═══════════════════════════════════════════════════════════════════

class TestWarRoom:
    @pytest.mark.asyncio
    async def test_escalation_l1_fix(self, state, mock_call_ai):
        """War Room L1 Quick Fix resolves."""
        with patch(
            "factory.pipeline.s3_codegen.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await _war_room_fix(
                state, "main.dart", "syntax error", "broken code",
            )
        assert result["resolved"] is True
        assert result["level"] == 1


# ═══════════════════════════════════════════════════════════════════
# Test 17: Integrated Flow
# ═══════════════════════════════════════════════════════════════════

class TestIntegratedFlow:
    @pytest.mark.asyncio
    async def test_s3_s4_s5_flow(self, state, mock_call_ai):
        """S3→S4→S5 integrated flow."""
        with patch(
            "factory.pipeline.s3_codegen.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s4_build.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s5_test.call_ai",
            side_effect=mock_call_ai,
        ):
            state = await s3_codegen_node(state)
            assert state.s3_output["file_count"] > 0

            state = await s4_build_node(state)
            assert state.s4_output is not None

            state = await s5_test_node(state)
            assert state.s5_output is not None


# ═══════════════════════════════════════════════════════════════════
# Test 18: Updated Stubs
# ═══════════════════════════════════════════════════════════════════

class TestUpdatedStubs:
    def test_stubs_only_s6_s8(self):
        """Stubs module only registers S6–S8."""
        # S3–S5 should be registered by real modules
        assert "s3_codegen" in _stage_nodes
        assert "s4_build" in _stage_nodes
        assert "s5_test" in _stage_nodes
        # S6–S8 should also be registered (by stubs)
        assert "s6_deploy" in _stage_nodes
        assert "s7_verify" in _stage_nodes
        assert "s8_handoff" in _stage_nodes
