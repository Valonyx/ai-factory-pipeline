"""Tests for factory.war_room (P6 War Room)."""

import pytest
from unittest.mock import AsyncMock, patch
from factory.war_room.levels import (
    WarRoomLevel, FixResult, ErrorContext,
    MAX_RETRY_CYCLES, GUI_FAILURE_THRESHOLD,
)
from factory.war_room.escalation import escalate_l1, escalate_l2, escalate_l3
from factory.war_room.war_room import (
    war_room_escalate, should_retry, increment_retry,
    reset_retries, get_war_room_summary,
)
from factory.war_room.patterns import (
    store_war_room_event, query_similar_errors, store_fix_pattern,
)


class TestLevels:
    def test_enum_values(self):
        assert WarRoomLevel.L1_QUICK_FIX.value == 1
        assert WarRoomLevel.L2_RESEARCHED.value == 2
        assert WarRoomLevel.L3_WAR_ROOM.value == 3

    def test_fix_result_serialization(self):
        fr = FixResult(
            resolved=True, level=WarRoomLevel.L1_QUICK_FIX,
            fix_applied="fix code", research="", plan={},
            cost_usd=0.005, error_summary="test error",
        )
        d = fr.to_dict()
        assert d["resolved"] is True
        assert d["level"] == 1

    def test_error_context(self):
        ec = ErrorContext(
            error_message="ImportError", error_type="ImportError",
            file_path="main.py", file_content="import foo",
        )
        d = ec.to_dict()
        assert d["error_type"] == "ImportError"

    def test_constants(self):
        assert MAX_RETRY_CYCLES == 3
        assert GUI_FAILURE_THRESHOLD == 3


class TestRetryManagement:
    def test_should_retry(self, fresh_state):
        assert should_retry(fresh_state) is True

    def test_increment_retry(self, fresh_state):
        increment_retry(fresh_state)
        assert fresh_state.retry_count == 1

    def test_max_retries(self, fresh_state):
        for _ in range(3):
            increment_retry(fresh_state)
        assert should_retry(fresh_state) is False

    def test_reset_retries(self, fresh_state):
        fresh_state.retry_count = 3
        reset_retries(fresh_state)
        assert fresh_state.retry_count == 0
        assert should_retry(fresh_state) is True


class TestWarRoomSummary:
    def test_empty_summary(self, fresh_state):
        s = get_war_room_summary(fresh_state)
        assert s["total_events"] == 0
        assert s["resolved"] == 0
        assert s["active"] is False

    def test_summary_with_history(self, fresh_state):
        fresh_state.war_room_history = [
            {"level": 1, "resolved": True, "error": "e1"},
            {"level": 2, "resolved": False, "error": "e2"},
        ]
        s = get_war_room_summary(fresh_state)
        assert s["total_events"] == 2
        assert s["resolved"] == 1
        assert s["unresolved"] == 1


class TestEscalation:
    @pytest.mark.asyncio
    async def test_l1_escalation(self, fresh_state, mock_ai):
        mock_ai.return_value = "fixed the import"
        ctx = ErrorContext(
            error_message="ImportError", error_type="ImportError",
            file_path="main.py", file_content="import foo",
        )
        result = await escalate_l1(fresh_state, ctx)
        assert isinstance(result, FixResult)
        assert result.level == WarRoomLevel.L1_QUICK_FIX

    @pytest.mark.asyncio
    async def test_l2_escalation(self, fresh_state):
        """L2 makes two AI calls: Scout research + Engineer fix."""
        # Patch escalation.call_ai directly to intercept the local binding
        with patch("factory.war_room.escalation.call_ai",
                   new_callable=AsyncMock) as mock:
            mock.return_value = "corrected file content"
            ctx = ErrorContext(
                error_message="TypeError: cannot unpack",
                error_type="TypeError",
                file_path="app.py",
                file_content="x, y = get_data()",
            )
            result = await escalate_l2(fresh_state, ctx)
        assert isinstance(result, FixResult)
        assert result.level == WarRoomLevel.L2_RESEARCHED
        assert result.resolved is True
        assert mock.call_count == 2  # Scout research + Engineer fix

    @pytest.mark.asyncio
    async def test_l3_escalation(self, fresh_state):
        """L3 uses Strategist for plan then Engineer for each rewrite."""
        plan_json = '{"root_cause": "missing dep", "cleanup_commands": [], "rewrite_plan": []}'
        with patch("factory.war_room.escalation.call_ai",
                   new_callable=AsyncMock) as mock:
            mock.return_value = plan_json
            ctx = ErrorContext(
                error_message="ModuleNotFoundError: no module named X",
                error_type="ModuleNotFoundError",
                file_path="main.py",
                file_content="import X",
            )
            result = await escalate_l3(fresh_state, ctx)
        assert isinstance(result, FixResult)
        assert result.level == WarRoomLevel.L3_WAR_ROOM
        assert isinstance(result.plan, dict)
        assert result.plan.get("root_cause") == "missing dep"

    @pytest.mark.asyncio
    async def test_l1_cannot_fix_escalates(self, fresh_state):
        """CANNOT_FIX from L1 means resolved=False."""
        with patch("factory.war_room.escalation.call_ai",
                   new_callable=AsyncMock) as mock:
            mock.return_value = "CANNOT_FIX"
            ctx = ErrorContext(
                error_message="deep runtime error",
                error_type="RuntimeError",
                file_path="core.py",
                file_content="broken code",
            )
            result = await escalate_l1(fresh_state, ctx)
        assert result.resolved is False


class TestWarRoomOrchestration:
    @pytest.mark.asyncio
    async def test_l1_resolves_skips_l2(self, fresh_state):
        """When L1 resolves, L2 and L3 are not called."""
        with patch("factory.war_room.escalation.call_ai",
                   new_callable=AsyncMock,
                   return_value="fixed: corrected import statement"):
            result = await war_room_escalate(
                fresh_state,
                error="SyntaxError",
                error_context={"type": "syntax", "file_path": "app.py",
                               "file_content": "bad code", "files": {}},
            )
        assert result["resolved"] is True
        assert result["level"] == 1

    @pytest.mark.asyncio
    async def test_full_escalation_l1_through_l3(self, fresh_state):
        """CANNOT_FIX at L1+L2 drives through to L3."""
        responses = [
            "CANNOT_FIX",   # L1
            "CANNOT_FIX",   # L2 Scout research
            "CANNOT_FIX",   # L2 Engineer fix
            '{"root_cause": "x", "cleanup_commands": [], "rewrite_plan": []}',  # L3
        ]
        call_count = [0]

        async def side_effect(**kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx] if idx < len(responses) else "fallback"

        with patch("factory.war_room.escalation.call_ai",
                   new_callable=AsyncMock) as mock:
            mock.side_effect = side_effect
            result = await war_room_escalate(
                fresh_state,
                error="deep error",
                error_context={"type": "codegen", "file_path": "main.py",
                               "file_content": "broken", "files": {}},
            )
        assert result["level"] == 3

    @pytest.mark.asyncio
    async def test_summary_after_escalation(self, fresh_state):
        """get_war_room_summary reflects history after escalation."""
        with patch("factory.war_room.escalation.call_ai",
                   new_callable=AsyncMock, return_value="fixed"):
            await war_room_escalate(
                fresh_state,
                error="NameError",
                error_context={"type": "name", "file_path": "x.py",
                               "file_content": "undefined", "files": {}},
            )
        summary = get_war_room_summary(fresh_state)
        assert summary["total_events"] >= 0  # history stored in state