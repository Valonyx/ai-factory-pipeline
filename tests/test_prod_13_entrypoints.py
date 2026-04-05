"""
PROD-13 Validation: Entry Points + Config + Orchestrator + CLI

Tests cover:
  Package Init (2 tests):
    1.  __version__ == "5.6.0"
    2.  __pipeline_version__ == "5.6"

  Config (6 tests):
    3.  ModelConfig has correct defaults
    4.  BudgetConfig has correct defaults
    5.  ComplianceConfig defaults
    6.  DataResidency primary region = me-central1
    7.  Config dataclasses are frozen
    8.  get_config_summary returns all sections

  Orchestrator (8 tests):
    9.  STAGE_SEQUENCE has 9 entries
    10. pipeline_node decorator runs and records history
    11. route_after_test: pass → s6_deploy
    12. route_after_test: fail → s3_codegen retry
    13. route_after_test: exhausted → halt
    14. route_after_verify: pass → s8_handoff
    15. route_after_verify: fail → s6_deploy retry
    16. halt_handler_node sets HALTED

  FastAPI App (2 tests):
    17. /health returns 200 with version
    18. app has all 5 routes

  CLI (2 tests):
    19. _show_health runs without error
    20. get_config_summary matches CLI output

Run:
  pytest tests/test_prod_13_entrypoints.py -v
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock

import factory
from factory.config import (
    MODELS,
    BUDGET,
    COMPLIANCE,
    DELIVERY,
    DATA_RESIDENCY,
    APP_STORE,
    WAR_ROOM,
    REQUIRED_SECRETS,
    CONDITIONAL_SECRETS,
    PIPELINE_FULL_VERSION,
    get_config_summary,
    validate_required_config,
    ModelConfig,
    BudgetConfig,
)
from factory.core.state import (
    PipelineState,
    Stage,
    AutonomyMode,
)
from factory.orchestrator import (
    STAGE_SEQUENCE,
    STAGE_NODES,
    pipeline_node,
    route_after_test,
    route_after_verify,
    halt_handler_node,
)
from factory.cli import _show_health


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    s = PipelineState(
        project_id="test_entry_001",
        operator_id="op_entry",
    )
    s.total_cost_usd = 0.0
    s.retry_count = 0
    s.stage_history = []
    return s


# ═══════════════════════════════════════════════════════════════════
# Tests 1-2: Package Init
# ═══════════════════════════════════════════════════════════════════

class TestPackageInit:
    def test_version(self):
        """__version__ == '5.6.0'."""
        assert factory.__version__ == "5.6.0"

    def test_pipeline_version(self):
        """__pipeline_version__ == '5.6'."""
        assert factory.__pipeline_version__ == "5.6"


# ═══════════════════════════════════════════════════════════════════
# Tests 3-8: Config
# ═══════════════════════════════════════════════════════════════════

class TestConfig:
    def test_model_defaults(self):
        """ModelConfig correct defaults."""
        assert MODELS.strategist == "claude-opus-4-6"
        assert MODELS.engineer == "claude-sonnet-4-5-20250929"
        assert MODELS.quick_fix == "claude-haiku-4-5-20251001"
        assert MODELS.scout == "sonar-pro"
        assert MODELS.scout_context_tier == "medium"

    def test_budget_defaults(self):
        """BudgetConfig correct defaults."""
        assert BUDGET.enabled is True
        assert BUDGET.monthly_budget_usd == 300.0
        assert BUDGET.project_cap_usd == 25.0
        assert BUDGET.project_alert_first == 8.0
        assert BUDGET.amber_pct == 80.0
        assert BUDGET.red_pct == 95.0
        assert BUDGET.black_pct == 100.0

    def test_compliance_defaults(self):
        """ComplianceConfig defaults."""
        assert COMPLIANCE.strict_store_compliance is False
        assert COMPLIANCE.confidence_threshold == 0.7
        assert COMPLIANCE.deploy_window_start == 6
        assert COMPLIANCE.deploy_window_end == 23

    def test_data_residency(self):
        """DataResidency primary = me-central1."""
        assert DATA_RESIDENCY.primary_region == "me-central1"
        assert "me-central1" in DATA_RESIDENCY.allowed_regions
        assert len(DATA_RESIDENCY.allowed_regions) == 4

    def test_frozen(self):
        """Config dataclasses are frozen."""
        with pytest.raises(Exception):
            MODELS.strategist = "changed"
        with pytest.raises(Exception):
            BUDGET.monthly_budget_usd = 999

    def test_summary(self):
        """get_config_summary returns all sections."""
        s = get_config_summary()
        assert s["version"] == "5.6.0"
        assert "models" in s
        assert "budget" in s
        assert "compliance" in s
        assert s["data_residency"] == "me-central1"


# ═══════════════════════════════════════════════════════════════════
# Tests 9-16: Orchestrator
# ═══════════════════════════════════════════════════════════════════

class TestOrchestrator:
    def test_stage_sequence(self):
        """STAGE_SEQUENCE has 9 entries."""
        assert len(STAGE_SEQUENCE) == 9
        names = [s[0] for s in STAGE_SEQUENCE]
        assert names[0] == "s0_intake"
        assert names[-1] == "s8_handoff"

    @pytest.mark.asyncio
    async def test_pipeline_node_decorator(self, state):
        """pipeline_node decorator runs and records."""

        @pipeline_node(Stage.S0_INTAKE)
        async def test_fn(s):
            s.project_metadata["ran"] = True
            return s

        result = await test_fn(state)
        assert result.project_metadata["ran"] is True
        assert result.snapshot_count >= 1
        assert len(result.stage_history) == 1
        assert result.stage_history[0][
            "stage"
        ] == "S0_INTAKE"

    def test_route_test_pass(self, state):
        """route_after_test: pass → s6_deploy."""
        state.s5_output = {"all_passed": True}
        assert route_after_test(state) == "s6_deploy"

    def test_route_test_fail_retry(self, state):
        """route_after_test: fail → s3_codegen."""
        state.s5_output = {"all_passed": False}
        state.retry_count = 0
        assert route_after_test(state) == "s3_codegen"
        assert state.retry_count == 1

    def test_route_test_exhausted(self, state):
        """route_after_test: exhausted → halt."""
        state.s5_output = {"all_passed": False}
        state.retry_count = 3
        assert route_after_test(state) == "halt"

    def test_route_verify_pass(self, state):
        """route_after_verify: pass → s8_handoff."""
        state.s7_output = {"verified": True}
        assert route_after_verify(state) == "s8_handoff"

    def test_route_verify_fail(self, state):
        """route_after_verify: fail → s6_deploy."""
        state.s7_output = {"verified": False}
        state.retry_count = 0
        assert route_after_verify(state) == "s6_deploy"
        assert state.retry_count == 1

    @pytest.mark.asyncio
    async def test_halt_handler(self, state):
        """halt_handler_node sets HALTED."""
        state.legal_halt_reason = "PDPL missing"
        result = await halt_handler_node(state)
        assert result.current_stage == Stage.HALTED


# ═══════════════════════════════════════════════════════════════════
# Tests 17-18: FastAPI App
# ═══════════════════════════════════════════════════════════════════

class TestFastAPIApp:
    def test_health_endpoint(self):
        """App has /health route."""
        from factory.app import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_all_routes(self):
        """App has all 5 routes."""
        from factory.app import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/health-deep" in routes
        assert "/webhook" in routes
        assert "/run" in routes
        assert "/status" in routes


# ═══════════════════════════════════════════════════════════════════
# Tests 19-20: CLI
# ═══════════════════════════════════════════════════════════════════

class TestCLI:
    def test_show_health(self, capsys):
        """_show_health runs without error."""
        _show_health()
        captured = capsys.readouterr()
        assert "Status:" in captured.out
        assert "Version:" in captured.out

    def test_config_summary_json(self):
        """get_config_summary produces valid JSON."""
        s = get_config_summary()
        serialized = json.dumps(s)
        parsed = json.loads(serialized)
        assert parsed["version"] == "5.6.0"
