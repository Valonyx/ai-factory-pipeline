"""Tests for factory.war_room (P6 War Room)."""

import pytest
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