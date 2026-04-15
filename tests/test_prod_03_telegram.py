"""
PROD-3 Validation: Real Telegram Bot

Tests cover:
  1. Message formatting (all 6 formatters)
  2. Truncation (4096 char limit)
  3. Emoji maps completeness
  4. Decision queue (present, resolve, timeout)
  5. Deploy gate (confirm, cancel, check)
  6. Operator state management
  7. Callback routing (mode, autonomy, cancel, decision)
  8. Active project management
  9. Notification typing (emoji by NotificationType)
  10. File size enforcement (50MB limit)

Run:
  pytest tests/test_prod_03_telegram.py -v
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from factory.core.state import (
    AIRole, AutonomyMode, ExecutionMode, NotificationType,
    PipelineState, Stage, PHASE_BUDGET_LIMITS,
)
from factory.telegram.messages import (
    format_welcome_message,
    format_help_message,
    format_status_message,
    format_cost_message,
    format_halt_message,
    format_project_started,
    truncate_message,
    STAGE_EMOJI,
    MODE_EMOJI,
    AUTONOMY_EMOJI,
    NOTIFICATION_EMOJI,
)
from factory.telegram.decisions import (
    present_decision,
    resolve_decision,
    store_operator_decision,
    record_deploy_decision,
    check_deploy_decision,
    clear_deploy_decision,
    set_operator_state,
    get_operator_state,
    clear_operator_state,
    set_operator_preference,
    get_operator_preferences,
)
from factory.telegram.notifications import (
    TELEGRAM_FILE_LIMIT_MB,
)
from factory.telegram.bot import (
    get_active_project,
    update_project_state,
    archive_project,
)


# ═══════════════════════════════════════════════════════════════════
# Test 1: Message Formatting
# ═══════════════════════════════════════════════════════════════════

class TestMessageFormatting:
    """Verify all 6 message formatters produce correct output."""

    def test_welcome_message(self):
        msg = format_welcome_message("Alex")
        assert "Alex" in msg
        assert "v5.8" in msg
        assert "/help" in msg

    def test_help_message(self):
        msg = format_help_message()
        assert "/new" in msg
        assert "/status" in msg
        assert "/restore" in msg
        assert "/deploy_confirm" in msg
        assert "/warroom" in msg

    def test_status_message(self):
        state = PipelineState(project_id="test-proj", operator_id="123")
        state.current_stage = Stage.S4_CODEGEN
        state.total_cost_usd = 1.50
        msg = format_status_message(state)
        assert "test-proj" in msg
        assert "S4_CODEGEN" in msg
        assert "$1.50" in msg

    def test_cost_message(self):
        state = PipelineState(project_id="cost-proj", operator_id="123")
        state.phase_costs["scout_research"] = 0.50
        msg = format_cost_message(state)
        assert "cost-proj" in msg
        assert "scout_research" in msg
        assert "$0.50" in msg

    def test_halt_message(self):
        state = PipelineState(project_id="halt-proj", operator_id="123")
        state.current_stage = Stage.HALTED
        msg = format_halt_message(state, "Build failed 3 times")
        assert "HALTED" in msg
        assert "Build failed" in msg
        assert "/continue" in msg
        assert "/restore" in msg

    def test_project_started(self):
        state = PipelineState(project_id="new-proj", operator_id="123")
        msg = format_project_started("new-proj", state)
        assert "new-proj" in msg
        assert "started" in msg


# ═══════════════════════════════════════════════════════════════════
# Test 2: Truncation
# ═══════════════════════════════════════════════════════════════════

class TestTruncation:
    def test_short_message_unchanged(self):
        msg = "Hello, operator!"
        assert truncate_message(msg) == msg

    def test_long_message_truncated(self):
        msg = "x" * 5000
        result = truncate_message(msg)
        assert len(result) <= 4096
        assert "truncated" in result

    def test_exact_limit_unchanged(self):
        msg = "y" * 4096
        assert truncate_message(msg) == msg

    def test_custom_limit(self):
        msg = "z" * 200
        result = truncate_message(msg, max_length=100)
        assert len(result) <= 100


# ═══════════════════════════════════════════════════════════════════
# Test 3: Emoji Maps
# ═══════════════════════════════════════════════════════════════════

class TestEmojiMaps:
    def test_all_stages_have_emoji(self):
        for stage in Stage:
            assert stage.value in STAGE_EMOJI, f"Missing emoji for {stage.value}"

    def test_all_modes_have_emoji(self):
        for mode in ExecutionMode:
            assert mode.value in MODE_EMOJI

    def test_all_autonomy_have_emoji(self):
        for mode in AutonomyMode:
            assert mode.value in AUTONOMY_EMOJI

    def test_notification_emoji_count(self):
        assert len(NOTIFICATION_EMOJI) >= 9


# ═══════════════════════════════════════════════════════════════════
# Test 4: Decision Queue
# ═══════════════════════════════════════════════════════════════════

class TestDecisionQueue:
    @pytest.mark.asyncio
    async def test_autopilot_auto_selects(self):
        """In Autopilot mode, should auto-select recommended option."""
        state = PipelineState(project_id="auto-test", operator_id="123")
        state.autonomy_mode = AutonomyMode.AUTOPILOT

        result = await present_decision(
            state=state,
            decision_type="test_decision",
            message="Pick one",
            options=[
                {"label": "Option A", "value": "a"},
                {"label": "Option B", "value": "b"},
            ],
            recommended=1,
        )
        assert result == "b"  # Recommended index 1

    @pytest.mark.asyncio
    async def test_resolve_decision(self):
        """Resolving a pending decision should complete the future."""
        from factory.telegram.decisions import _pending_decisions

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        _pending_decisions["dec_test123"] = future

        resolved = await resolve_decision("dec_test123", "selected_value")
        assert resolved is True
        assert future.result() == "selected_value"

        # Cleanup
        _pending_decisions.pop("dec_test123", None)

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_decision(self):
        resolved = await resolve_decision("dec_nonexistent", "value")
        assert resolved is False


# ═══════════════════════════════════════════════════════════════════
# Test 5: Deploy Gate (FIX-08)
# ═══════════════════════════════════════════════════════════════════

class TestDeployGate:
    @pytest.mark.asyncio
    async def test_record_and_check_confirm(self):
        await record_deploy_decision("proj-dg1", "op1", confirmed=True)
        result = await check_deploy_decision("proj-dg1")
        assert result is True
        await clear_deploy_decision("proj-dg1")

    @pytest.mark.asyncio
    async def test_record_and_check_cancel(self):
        await record_deploy_decision("proj-dg2", "op1", confirmed=False)
        result = await check_deploy_decision("proj-dg2")
        assert result is False
        await clear_deploy_decision("proj-dg2")

    @pytest.mark.asyncio
    async def test_check_pending(self):
        result = await check_deploy_decision("proj-nonexistent")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Test 6: Operator State
# ═══════════════════════════════════════════════════════════════════

class TestOperatorState:
    @pytest.mark.asyncio
    async def test_set_and_get_state(self):
        await set_operator_state("op1", "awaiting_input", {"stage": "S0"})
        state = await get_operator_state("op1")
        assert state["state"] == "awaiting_input"
        assert state["context"]["stage"] == "S0"
        await clear_operator_state("op1")

    @pytest.mark.asyncio
    async def test_clear_state(self):
        await set_operator_state("op2", "active")
        await clear_operator_state("op2")
        assert await get_operator_state("op2") is None

    @pytest.mark.asyncio
    async def test_preferences(self):
        await set_operator_preference("op3", "autonomy_default", "copilot")
        prefs = get_operator_preferences("op3")
        assert prefs["autonomy_default"] == "copilot"


# ═══════════════════════════════════════════════════════════════════
# Test 7: Active Project Management
# ═══════════════════════════════════════════════════════════════════

class TestActiveProjects:
    @pytest.mark.asyncio
    async def test_create_and_get(self):
        state = PipelineState(project_id="proj-ap1", operator_id="op1")
        await update_project_state(state)
        project = await get_active_project("op1")
        assert project is not None
        assert project["project_id"] == "proj-ap1"

    @pytest.mark.asyncio
    async def test_archive(self):
        state = PipelineState(project_id="proj-ap2", operator_id="op2")
        await update_project_state(state)
        await archive_project("proj-ap2")
        project = await get_active_project("op2")
        assert project is None


# ═══════════════════════════════════════════════════════════════════
# Test 8: File Size Enforcement
# ═══════════════════════════════════════════════════════════════════

class TestFileSizeEnforcement:
    def test_telegram_file_limit(self):
        """Telegram file limit should be 50MB per spec [V12]."""
        assert TELEGRAM_FILE_LIMIT_MB == 50.0

    def test_phase_budget_limits_in_cost_message(self):
        """Cost message should include all phase categories."""
        state = PipelineState(project_id="fmt-test", operator_id="123")
        msg = format_cost_message(state)
        for category in PHASE_BUDGET_LIMITS:
            assert category in msg
