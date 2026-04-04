"""
AI Factory Pipeline v5.6 — War Room Module

L1→L2→L3 escalation ladder for error resolution.
"""

from factory.war_room.levels import (
    WarRoomLevel,
    FixResult,
    ErrorContext,
    MAX_L1_ATTEMPTS,
    MAX_L2_ATTEMPTS,
    MAX_L3_ATTEMPTS,
    MAX_RETRY_CYCLES,
    GUI_FAILURE_THRESHOLD,
)

from factory.war_room.escalation import (
    escalate_l1,
    escalate_l2,
    escalate_l3,
    set_fix_hooks,
    apply_and_test_fix,
)

from factory.war_room.war_room import (
    war_room_escalate,
    should_retry,
    increment_retry,
    reset_retries,
    get_war_room_summary,
)

from factory.war_room.patterns import (
    store_war_room_event,
    query_similar_errors,
    store_fix_pattern,
)

__all__ = [
    # Levels
    "WarRoomLevel", "FixResult", "ErrorContext",
    "MAX_RETRY_CYCLES", "GUI_FAILURE_THRESHOLD",
    # Escalation
    "escalate_l1", "escalate_l2", "escalate_l3",
    "set_fix_hooks", "apply_and_test_fix",
    # Orchestrator
    "war_room_escalate", "should_retry",
    "increment_retry", "reset_retries", "get_war_room_summary",
    # Patterns
    "store_war_room_event", "query_similar_errors", "store_fix_pattern",
]