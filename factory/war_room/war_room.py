"""
AI Factory Pipeline v5.6 — War Room Orchestrator

Implements:
  - §2.2.4 Full escalation flow (L1→L2→L3)
  - L3 failure → pipeline halt + operator notification
  - GUI stack pivot check (§2.3.2)
  - Mother Memory pattern query before escalation
  - Retry cycle tracking

Spec Authority: v5.6 §2.2.4
"""

from __future__ import annotations

import logging
from typing import Optional

from factory.core.state import PipelineState, Stage
from factory.telegram.notifications import send_telegram_message
from factory.war_room.levels import (
    WarRoomLevel,
    FixResult,
    ErrorContext,
    MAX_RETRY_CYCLES,
)
from factory.war_room.escalation import (
    escalate_l1,
    escalate_l2,
    escalate_l3,
)
from factory.war_room.patterns import (
    store_war_room_event,
    query_similar_errors,
    store_fix_pattern,
)

logger = logging.getLogger("factory.war_room")


# ═══════════════════════════════════════════════════════════════════
# §2.2.4 War Room Orchestrator
# ═══════════════════════════════════════════════════════════════════


async def war_room_escalate(
    state: PipelineState,
    error: str,
    error_context: dict,
    current_level: WarRoomLevel = WarRoomLevel.L1_QUICK_FIX,
) -> dict:
    """Full War Room escalation — L1 → L2 → L3.

    Spec: §2.2.4

    Each level is tried in order. If a level resolves the error,
    the resolution is logged and execution continues.

    Args:
        state: Current pipeline state.
        error: Error message string.
        error_context: Dict with file_content, files, etc.
        current_level: Starting level (default L1).

    Returns:
        {"resolved": bool, "level": int, "fix_applied": str, ...}
    """
    context = _build_context(error, error_context)

    # ── Check Mother Memory for similar past resolutions ──
    similar = await query_similar_errors(
        error,
        stack=getattr(state, "selected_stack", ""),
    )
    if similar:
        logger.info(
            f"[{state.project_id}] Found {len(similar)} similar "
            f"past resolutions in Mother Memory"
        )
        # Inject prior knowledge into context
        context.files["_prior_fixes"] = "\n".join(
            f"- L{s['level']}: {s['fix_applied'][:200]}"
            for s in similar[:3]
        )

    # ── Level 1: Quick Fix (Haiku) ──
    if current_level <= WarRoomLevel.L1_QUICK_FIX:
        result = await escalate_l1(state, context)
        if result.resolved:
            await _on_resolved(state, result, context)
            return result.to_dict()

    # ── Level 2: Researched Fix (Scout → Engineer) ──
    if current_level <= WarRoomLevel.L2_RESEARCHED:
        result = await escalate_l2(state, context)
        if result.resolved:
            await _on_resolved(state, result, context)
            return result.to_dict()

    # ── Level 3: War Room (Opus orchestrates) ──
    result = await escalate_l3(state, context)
    await _on_resolved(state, result, context)

    if not result.resolved:
        await _on_l3_failed(state, error)

    return result.to_dict()


# ═══════════════════════════════════════════════════════════════════
# Resolution Handlers
# ═══════════════════════════════════════════════════════════════════


async def _on_resolved(
    state: PipelineState,
    result: FixResult,
    context: ErrorContext,
) -> None:
    """Post-resolution: store in Mother Memory, notify if needed."""
    # Store WarRoomEvent in Neo4j
    await store_war_room_event(state, result)

    # Store fix pattern for cross-project learning
    if result.resolved:
        await store_fix_pattern(
            state,
            error_type=context.error_type,
            fix_description=result.fix_applied[:500],
            success=True,
        )


async def _on_l3_failed(
    state: PipelineState,
    error: str,
) -> None:
    """L3 failed — pipeline halts, operator notified.

    Spec: §2.2.4 — "If L3 fails: pipeline pauses and alerts operator."
    """
    logger.error(
        f"[{state.project_id}] War Room L3 FAILED — halting pipeline"
    )

    await send_telegram_message(
        state.operator_id,
        f"🚨 War Room exhausted all levels (L1→L2→L3).\n\n"
        f"Error: {error[:300]}\n\n"
        f"The pipeline cannot auto-resolve this issue.\n"
        f"Options:\n"
        f"  /retry — Try again from S3 (CodeGen)\n"
        f"  /pivot — Switch to different tech stack\n"
        f"  /cancel — Stop this project\n\n"
        f"War Room history: {len(state.war_room_history)} attempts",
    )

    # Check GUI pivot threshold (§2.3.2)
    gui_failures = sum(
        1 for h in state.war_room_history
        if h.get("level") == 3 and not h.get("resolved")
    )
    if gui_failures >= 3:
        await send_telegram_message(
            state.operator_id,
            f"🔧 **Stack Pivot Suggestion**\n\n"
            f"L3 has failed {gui_failures} times. Consider switching "
            f"to a CLI-native stack:\n"
            f"  /pivot react_native\n"
            f"  /pivot kotlin\n"
            f"  /pivot python_backend",
        )


# ═══════════════════════════════════════════════════════════════════
# Retry Cycle Management
# ═══════════════════════════════════════════════════════════════════


def should_retry(state: PipelineState) -> bool:
    """Check if another S5→S3 retry cycle is allowed.

    Spec: §2.7.1 — retry_count tracks loop iterations.
    Default max: 3 cycles.
    """
    return state.retry_count < MAX_RETRY_CYCLES


def increment_retry(state: PipelineState) -> int:
    """Increment retry counter, return new count."""
    state.retry_count += 1
    logger.info(
        f"[{state.project_id}] Retry cycle "
        f"{state.retry_count}/{MAX_RETRY_CYCLES}"
    )
    return state.retry_count


def reset_retries(state: PipelineState) -> None:
    """Reset retry counter (e.g., after successful deploy)."""
    state.retry_count = 0


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _build_context(error: str, error_context: dict) -> ErrorContext:
    """Build ErrorContext from raw dict."""
    return ErrorContext(
        error_message=error,
        error_type=error_context.get("type", "unknown"),
        file_path=error_context.get("file_path"),
        file_content=error_context.get("file_content"),
        files=error_context.get("files", {}),
        stack_trace=error_context.get("stack_trace", ""),
        test_output=error_context.get("test_output", ""),
        stage=error_context.get("stage", ""),
    )


def get_war_room_summary(state: PipelineState) -> dict:
    """War Room status summary for dashboards."""
    history = state.war_room_history
    return {
        "active": state.war_room_active,
        "total_events": len(history),
        "resolved": sum(1 for h in history if h.get("resolved")),
        "unresolved": sum(1 for h in history if not h.get("resolved")),
        "by_level": {
            1: sum(1 for h in history if h.get("level") == 1),
            2: sum(1 for h in history if h.get("level") == 2),
            3: sum(1 for h in history if h.get("level") == 3),
        },
        "retry_count": state.retry_count,
        "max_retries": MAX_RETRY_CYCLES,
    }