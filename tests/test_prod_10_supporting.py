"""
PROD-10 Validation: Supporting Modules

Tests cover:
  Execution Layer (6 tests):
    1.  execute_command runs echo
    2.  execute_command blocks sudo via enforce_user_space
    3.  ExecutionModeManager routes Cloud task
    4.  ExecutionModeManager Local→Cloud failover
    5.  ExecutionModeManager Hybrid routing
    6.  HeartbeatMonitor consecutive failure tracking

  User-Space Enforcer (5 tests):
    7.  enforce_user_space blocks all prohibited patterns
    8.  enforce_user_space rewrites pip install → --user
    9.  enforce_user_space rewrites npm install -g → npx
    10. validate_file_path blocks /etc
    11. sanitize_for_shell escapes dangerous chars

  Legal Engine (9 tests):
    12. resolve_regulatory_body alias resolution
    13. get_regulators_for_category e-commerce
    14. is_ksa_compliant_region me-central1
    15. is_within_deploy_window daytime
    16. check_prohibited_sdks detection
    17. LEGAL_CHECKS_BY_STAGE coverage (5 stages)
    18. get_all_check_names returns 9 checks
    19. legal_check_hook runs without error
    20. _check_data_residency rejects bad region

Run:
  pytest tests/test_prod_10_supporting.py -v
"""

from __future__ import annotations

import asyncio
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from factory.core.user_space import (
    UserSpaceViolation,
    PROHIBITED_PATTERNS,
    SAFE_INSTALL_REWRITES,
    enforce_user_space,
    validate_file_path,
    sanitize_for_shell,
)
from factory.core.execution import (
    execute_command,
    write_file,
    ExecutionModeManager,
    HeartbeatMonitor,
    heartbeat_loop,
)
from factory.core.state import (
    ExecutionMode,
    PipelineState,
    Stage,
)
from factory.legal.regulatory import (
    REGULATORY_BODY_MAPPING,
    resolve_regulatory_body,
    get_regulators_for_category,
    CATEGORY_REGULATORS,
    PDPL_REQUIREMENTS,
    ALLOWED_DATA_REGIONS,
    PRIMARY_DATA_REGION,
    is_ksa_compliant_region,
    is_within_deploy_window,
    check_prohibited_sdks,
    PROHIBITED_SDKS,
    KSA_TIMEZONE,
)
from factory.legal.checks import (
    LEGAL_CHECKS_BY_STAGE,
    legal_check_hook,
    run_legal_check,
    get_checks_for_stage,
    get_all_check_names,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    """Fresh PipelineState for testing."""
    s = PipelineState(
        project_id="test_support_001",
        operator_id="op_support",
    )
    s.s0_output = {
        "app_name": "TestApp",
        "app_category": "e-commerce",
        "has_user_accounts": True,
        "has_payments": True,
    }
    s.s2_output = {
        "selected_stack": "react_native",
        "auth_method": "phone",
        "deploy_region": "me-central1",
    }
    s.s4_output = {
        "generated_files": {
            "App.tsx": "// consent checkbox here\nexport default () => null",
            "package.json": '{"dependencies": {"react": "18"}}',
        },
    }
    return s


# ═══════════════════════════════════════════════════════════════════
# Tests 1-6: Execution Layer
# ═══════════════════════════════════════════════════════════════════

class TestExecutionLayer:
    @pytest.mark.asyncio
    async def test_execute_command_echo(self):
        """execute_command runs echo and captures output."""
        code, stdout, stderr = await execute_command("echo hello")
        assert code == 0
        assert "hello" in stdout

    @pytest.mark.asyncio
    async def test_execute_command_blocks_sudo(self):
        """execute_command blocks sudo via enforce_user_space."""
        with pytest.raises(UserSpaceViolation):
            await execute_command("sudo rm -rf /tmp/test")

    @pytest.mark.asyncio
    async def test_exec_mgr_cloud_task(self, state):
        """ExecutionModeManager routes Cloud task."""
        state.execution_mode = ExecutionMode.CLOUD
        mgr = ExecutionModeManager(state)
        result = await mgr.execute_task({
            "name": "test_task",
            "command": "echo cloud_test",
            "type": "general",
        })
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_mgr_local_failover(self, state):
        """ExecutionModeManager halts (not silently falls back) when LOCAL+unreachable.

        Issue 26: LOCAL mode must NOT fall back to CLOUD silently.
        The operator explicitly chose LOCAL; an unreachable machine raises RuntimeError
        so the pipeline halts with a clear Telegram message.
        """
        state.execution_mode = ExecutionMode.LOCAL
        state.local_heartbeat_alive = False
        mgr = ExecutionModeManager(state)
        with pytest.raises(RuntimeError, match="LOCAL mode: machine unreachable"):
            await mgr.execute_task({
                "name": "test_failover",
                "command": "echo failover",
                "type": "general",
            })
        # execution_mode must NOT have been changed to CLOUD
        assert state.execution_mode == ExecutionMode.LOCAL

    @pytest.mark.asyncio
    async def test_exec_mgr_hybrid_routing(self, state):
        """ExecutionModeManager Hybrid routes backend to cloud."""
        state.execution_mode = ExecutionMode.HYBRID
        state.local_heartbeat_alive = True
        mgr = ExecutionModeManager(state)

        # backend_deploy → cloud
        result = await mgr.execute_task({
            "name": "deploy",
            "command": "echo deploy",
            "type": "backend_deploy",
        })
        assert result["exit_code"] == 0

    def test_heartbeat_consecutive_failures(self, state):
        """HeartbeatMonitor tracks consecutive failures."""
        monitor = HeartbeatMonitor(state)
        assert monitor.consecutive_failures == 0
        assert monitor.max_failures == 3


# ═══════════════════════════════════════════════════════════════════
# Tests 7-11: User-Space Enforcer
# ═══════════════════════════════════════════════════════════════════

class TestUserSpaceEnforcer:
    def test_blocks_all_prohibited(self):
        """enforce_user_space blocks all prohibited patterns."""
        for pattern in PROHIBITED_PATTERNS:
            cmd = f"some prefix {pattern} suffix"
            with pytest.raises(UserSpaceViolation):
                enforce_user_space(cmd)

    def test_rewrites_pip(self):
        """enforce_user_space rewrites pip install → --user."""
        result = enforce_user_space("pip install flask")
        assert "--user" in result

    def test_rewrites_npm(self):
        """enforce_user_space rewrites npm install -g → npx."""
        result = enforce_user_space("npm install -g typescript")
        assert "npx" in result
        assert "-g" not in result

    def test_validate_path_blocks_etc(self):
        """validate_file_path blocks /etc paths."""
        with pytest.raises(UserSpaceViolation):
            validate_file_path("/etc/passwd")

    def test_sanitize_shell(self):
        """sanitize_for_shell escapes dangerous chars."""
        result = sanitize_for_shell("hello; rm -rf /")
        assert "\\;" in result
        result2 = sanitize_for_shell("test$(whoami)")
        assert "\\$" in result2


# ═══════════════════════════════════════════════════════════════════
# Tests 12-20: Legal Engine
# ═══════════════════════════════════════════════════════════════════

class TestLegalEngine:
    def test_resolve_regulatory_body(self):
        """resolve_regulatory_body normalizes aliases."""
        assert resolve_regulatory_body("CITC") == "CST"
        assert resolve_regulatory_body("Saudi Central Bank") == "SAMA"
        assert resolve_regulatory_body("MOC") == "MINISTRY_OF_COMMERCE"
        assert resolve_regulatory_body("NDMO") == "NDMO"
        assert resolve_regulatory_body("NCA") == "NCA"
        assert resolve_regulatory_body("SDAIA") == "SDAIA"

    def test_category_regulators_ecommerce(self):
        """get_regulators_for_category returns MOC for e-commerce."""
        regs = get_regulators_for_category("e-commerce")
        assert "MINISTRY_OF_COMMERCE" in regs
        assert "CST" in regs

    def test_ksa_compliant_region(self):
        """is_ksa_compliant_region accepts me-central1."""
        assert is_ksa_compliant_region("me-central1") is True
        assert is_ksa_compliant_region("us-east1") is False

    def test_deploy_window_daytime(self):
        """is_within_deploy_window returns True for daytime."""
        daytime = datetime(
            2026, 2, 27, 12, 0, 0,
            tzinfo=KSA_TIMEZONE,
        )
        assert is_within_deploy_window(daytime) is True

        nighttime = datetime(
            2026, 2, 27, 2, 0, 0,
            tzinfo=KSA_TIMEZONE,
        )
        assert is_within_deploy_window(nighttime) is False

    def test_prohibited_sdks_detection(self):
        """check_prohibited_sdks detects violations."""
        deps = ["react", "facebook-analytics", "lodash"]
        found = check_prohibited_sdks(deps)
        assert len(found) == 1
        assert "facebook-analytics" in found

        clean = check_prohibited_sdks(["react", "lodash"])
        assert len(clean) == 0

    def test_legal_checks_5_stages(self):
        """LEGAL_CHECKS_BY_STAGE covers 5 stages."""
        assert len(LEGAL_CHECKS_BY_STAGE) == 5
        assert Stage.S2_BLUEPRINT in LEGAL_CHECKS_BY_STAGE
        assert Stage.S4_CODEGEN in LEGAL_CHECKS_BY_STAGE
        assert Stage.S5_BUILD in LEGAL_CHECKS_BY_STAGE
        assert Stage.S7_DEPLOY in LEGAL_CHECKS_BY_STAGE
        assert Stage.S9_HANDOFF in LEGAL_CHECKS_BY_STAGE

    def test_all_check_names_9(self):
        """get_all_check_names returns 9 unique checks."""
        names = get_all_check_names()
        assert len(names) == 9
        assert "pdpl_consent_checkboxes" in names
        assert "cst_time_of_day_restrictions" in names

    @pytest.mark.asyncio
    async def test_legal_check_hook_runs(self, state):
        """legal_check_hook runs without error."""
        await legal_check_hook(
            state, Stage.S2_BLUEPRINT, "pre",
        )
        # Should not raise

    @pytest.mark.asyncio
    async def test_data_residency_rejects_bad(self, state):
        """_check_data_residency rejects non-compliant region."""
        state.s2_output["deploy_region"] = "us-east1"
        result = await run_legal_check(
            state, "data_residency_compliance",
        )
        assert result["passed"] is False
        assert result["severity"] == "critical"
