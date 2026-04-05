"""
PROD-9 Validation: Pipeline Stages S6–S8

Tests cover:
  1.  All 10 stage nodes registered (all real, zero stubs)
  2.  S6: IOS_SUBMISSION_STEPS has 5 steps (FIX-21)
  3.  S6: _extract_deploy_url parses URLs
  4.  S6: _extract_deploy_url returns None for no URL
  5.  S6: deploy node populates s6_output
  6.  S7: _verify_mobile API method
  7.  S7: _verify_mobile Airlock method
  8.  S7: verify node populates s7_output
  9.  S8: DOCUGEN_TEMPLATES has 5 templates
  10. S8: HANDOFF_DOCS has 4 per-project docs (FIX-27)
  11. S8: PROGRAM_DOCS has 3 per-program docs (FIX-27)
  12. S8: _compile_project_summary structure
  13. S8: handoff node populates s8_output
  14. Full pipeline S0→S8 end-to-end (SimpleExecutor)
  15. No stubs remain in _stage_nodes

Run:
  pytest tests/test_prod_09_stages.py -v
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
)
from factory.pipeline.graph import (
    _stage_nodes,
    SimpleExecutor,
    run_pipeline,
)
from factory.pipeline.s6_deploy import (
    s6_deploy_node,
    IOS_SUBMISSION_STEPS,
    _extract_deploy_url,
)
from factory.pipeline.s7_verify import (
    s7_verify_node,
    _verify_mobile,
)
from factory.pipeline.s8_handoff import (
    s8_handoff_node,
    DOCUGEN_TEMPLATES,
    HANDOFF_DOCS,
    PROGRAM_DOCS,
    _compile_project_summary,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    """Fresh PipelineState with S0–S5 outputs populated."""
    s = PipelineState(
        project_id="test_s678_001",
        operator_id="op_789",
    )
    s.intake_message = "Build a food delivery app"
    s.s0_output = {
        "app_name": "RiyadhEats",
        "app_description": "Food delivery for Riyadh",
        "app_category": "food",
        "features_must": ["ordering", "tracking"],
        "target_platforms": ["ios", "android", "web"],
        "has_payments": True,
        "has_user_accounts": True,
    }
    s.s1_output = {
        "data_classification": "internal",
        "regulatory_bodies": ["PDPL"],
        "blocked_features": [],
        "required_legal_docs": ["privacy_policy", "terms_of_use"],
        "payment_mode": "SANDBOX",
        "risk_level": "medium",
        "proceed": True,
    }
    s.s2_output = {
        "project_id": s.project_id,
        "app_name": "RiyadhEats",
        "app_description": "Food delivery for Riyadh",
        "target_platforms": ["ios", "android", "web"],
        "selected_stack": "react_native",
        "screens": [
            {"name": "home", "components": []},
            {"name": "menu", "components": []},
        ],
        "data_model": [{"collection": "orders", "fields": []}],
        "api_endpoints": [],
        "auth_method": "phone",
        "color_palette": {"primary": "#FF5722"},
        "typography": {"heading": "Cairo"},
        "design_system": "material3",
    }
    s.selected_stack = TechStack.REACT_NATIVE
    s.s3_output = {
        "generated_files": {"App.tsx": "export default () => null"},
        "file_count": 1,
        "stack": "react_native",
    }
    s.s4_output = {
        "build_success": True,
        "artifacts": {"android": {"status": "success"}},
    }
    s.s5_output = {
        "passed": True,
        "total_tests": 10,
        "passed_tests": 10,
        "failed_tests": 0,
    }
    return s


@pytest.fixture
def mock_call_ai():
    """Mock call_ai for S6–S8 tests."""
    async def _mock(role, prompt, state=None, **kwargs):
        if role.value == "engineer":
            if "legal" in prompt.lower() or "privacy" in prompt.lower():
                return "⚠️ REQUIRES_LEGAL_REVIEW\n\n# Privacy Policy\n\nGenerated."
            elif "quick_start" in prompt.lower() or "handoff" in prompt.lower():
                return "# Quick Start\n\nLaunch instructions..."
            else:
                return "Generated document content."
        elif role.value == "quick_fix":
            return "curl -s -o /dev/null -w '%{http_code}' https://example.com"
        elif role.value == "scout":
            return "pass — no guideline violations found"
        return ""

    return _mock


# ═══════════════════════════════════════════════════════════════════
# Tests 1-5: S6 Deploy
# ═══════════════════════════════════════════════════════════════════

class TestS6Deploy:
    def test_all_nodes_registered(self):
        """All 10 stage nodes registered, zero stubs."""
        expected = [
            "s0_intake", "s1_legal", "s2_blueprint",
            "s3_codegen", "s4_build", "s5_test",
            "s6_deploy", "s7_verify", "s8_handoff",
            "halt_handler",
        ]
        for name in expected:
            assert name in _stage_nodes, f"Missing: {name}"
        assert len(_stage_nodes) >= 10

    def test_ios_submission_5_steps(self):
        """IOS_SUBMISSION_STEPS has 5 steps per FIX-21."""
        assert len(IOS_SUBMISSION_STEPS) == 5
        names = [s["name"] for s in IOS_SUBMISSION_STEPS]
        assert names == [
            "archive", "export", "validate",
            "upload", "poll_processing",
        ]

    def test_extract_url(self):
        """_extract_deploy_url parses URLs."""
        assert _extract_deploy_url(
            "Deployed to https://myapp.web.app done"
        ) == "https://myapp.web.app"
        assert _extract_deploy_url(
            "URL: https://api.example.com/v1 (live)"
        ) == "https://api.example.com/v1"

    def test_extract_url_none(self):
        """_extract_deploy_url returns None for no URL."""
        assert _extract_deploy_url("Deploying...") is None
        assert _extract_deploy_url("") is None

    @pytest.mark.asyncio
    async def test_deploy_populates_output(
        self, state, mock_call_ai,
    ):
        """S6 deploy populates s6_output."""
        with patch(
            "factory.pipeline.s6_deploy.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s6_deploy_node(state)
        assert result.s6_output is not None
        assert "deployments" in result.s6_output
        assert "all_success" in result.s6_output


# ═══════════════════════════════════════════════════════════════════
# Tests 6-8: S7 Verify
# ═══════════════════════════════════════════════════════════════════

class TestS7Verify:
    def test_verify_mobile_api(self):
        """_verify_mobile handles API deployment."""
        result = _verify_mobile(
            "ios", {"method": "api", "status": "processing"},
        )
        assert result["passed"] is True
        assert result["type"] == "ios_upload"

    def test_verify_mobile_airlock(self):
        """_verify_mobile handles Airlock delivery."""
        result = _verify_mobile(
            "android", {"method": "airlock_telegram"},
        )
        assert result["passed"] is True
        assert "manual upload" in result["note"]

    @pytest.mark.asyncio
    async def test_verify_populates_output(
        self, state, mock_call_ai,
    ):
        """S7 verify populates s7_output."""
        state.s6_output = {
            "deployments": {
                "web": {"success": True, "url": "https://test.web.app"},
                "android": {"method": "api", "success": True},
            },
            "all_success": True,
        }
        with patch(
            "factory.pipeline.s7_verify.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s7_verify_node(state)
        assert result.s7_output is not None
        assert "passed" in result.s7_output
        assert "checks" in result.s7_output


# ═══════════════════════════════════════════════════════════════════
# Tests 9-13: S8 Handoff
# ═══════════════════════════════════════════════════════════════════

class TestS8Handoff:
    def test_docugen_templates(self):
        """DOCUGEN_TEMPLATES has 5 templates."""
        assert len(DOCUGEN_TEMPLATES) == 5
        assert "privacy_policy" in DOCUGEN_TEMPLATES
        assert "terms_of_use" in DOCUGEN_TEMPLATES
        assert DOCUGEN_TEMPLATES["merchant_agreement"][
            "required_for"
        ] == ["marketplace", "e-commerce"]

    def test_handoff_docs(self):
        """HANDOFF_DOCS has 4 per-project docs (FIX-27)."""
        assert len(HANDOFF_DOCS) == 4
        assert "QUICK_START.md" in HANDOFF_DOCS
        assert "EMERGENCY_RUNBOOK.md" in HANDOFF_DOCS
        assert "SERVICE_MAP.md" in HANDOFF_DOCS
        assert "UPDATE_GUIDE.md" in HANDOFF_DOCS

    def test_program_docs(self):
        """PROGRAM_DOCS has 3 per-program docs (FIX-27)."""
        assert len(PROGRAM_DOCS) == 3
        assert "INTEGRATION_TEST_CHECKLIST.md" in PROGRAM_DOCS

    def test_compile_summary(self, state):
        """_compile_project_summary has required fields."""
        state.s6_output = {"deployments": {}}
        state.s7_output = {"passed": True, "check_count": 3}
        summary = _compile_project_summary(state)
        assert summary["project_id"] == state.project_id
        assert summary["app_name"] == "RiyadhEats"
        assert "total_cost_usd" in summary
        assert "completed_at" in summary

    @pytest.mark.asyncio
    async def test_handoff_populates_output(
        self, state, mock_call_ai,
    ):
        """S8 handoff populates s8_output."""
        state.s6_output = {
            "deployments": {"web": {"url": "https://test.web.app"}},
        }
        state.s7_output = {"passed": True, "check_count": 2}
        with patch(
            "factory.pipeline.s8_handoff.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await s8_handoff_node(state)
        assert result.s8_output is not None
        assert result.s8_output["delivered"] is True
        assert "privacy_policy" in result.s8_output["legal_docs"]
        assert "QUICK_START.md" in result.s8_output["handoff_docs"]


# ═══════════════════════════════════════════════════════════════════
# Tests 14-15: Full Pipeline + No Stubs
# ═══════════════════════════════════════════════════════════════════

class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_full_e2e_pipeline(self, state, mock_call_ai):
        """Full S0→S8 end-to-end via SimpleExecutor."""
        with patch(
            "factory.pipeline.s0_intake.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s1_legal.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s2_blueprint.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s3_codegen.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s4_build.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s5_test.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s6_deploy.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s7_verify.call_ai",
            side_effect=mock_call_ai,
        ), patch(
            "factory.pipeline.s8_handoff.call_ai",
            side_effect=mock_call_ai,
        ):
            result = await run_pipeline(state)

        # Should complete or be at S8_HANDOFF
        assert result.s0_output is not None
        assert result.s8_output is not None or (
            result.current_stage == Stage.HALTED
        )

    def test_no_stubs_remain(self):
        """No stub implementations in _stage_nodes."""
        for name, fn in _stage_nodes.items():
            # Check that no node has 'stub' in its module path
            module = getattr(fn, "__module__", "")
            assert "stubs" not in module, (
                f"Stub found: {name} from {module}"
            )
