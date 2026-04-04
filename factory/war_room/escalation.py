"""
AI Factory Pipeline v5.6 — War Room Escalation Ladder

Implements:
  - §2.2.4 L1 Quick Fix (Haiku — minimal syntax fix)
  - §2.2.4 L2 Researched Fix (Scout → Engineer)
  - §2.2.4 L3 War Room (Opus orchestrates rewrite plan)

Cost note (§2.2.4): Per-invocation estimates are illustrative.
Runtime cost enforcement by circuit breaker (§3.6) + Budget Governor (§2.14).

Spec Authority: v5.6 §2.2.4
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from factory.core.state import AIRole, PipelineState
from factory.core.roles import call_ai
from factory.core.user_space import enforce_user_space
from factory.war_room.levels import (
    WarRoomLevel,
    FixResult,
    ErrorContext,
    L1_FILE_CONTEXT_CHARS,
    L2_FILE_CONTEXT_CHARS,
    L3_FILE_CONTEXT_CHARS,
    L3_METADATA_CHARS,
)

logger = logging.getLogger("factory.war_room.escalation")


# ═══════════════════════════════════════════════════════════════════
# Fix Application Abstraction
# ═══════════════════════════════════════════════════════════════════

# Pluggable test runner — injected by pipeline orchestrator
_test_runner: Optional[Callable[..., Awaitable[bool]]] = None
_file_writer: Optional[Callable[..., Awaitable[None]]] = None
_command_executor: Optional[Callable[..., Awaitable[dict]]] = None


def set_fix_hooks(
    test_runner: Callable[..., Awaitable[bool]],
    file_writer: Callable[..., Awaitable[None]],
    command_executor: Callable[..., Awaitable[dict]],
) -> None:
    """Inject test/file/command hooks for fix application."""
    global _test_runner, _file_writer, _command_executor
    _test_runner = test_runner
    _file_writer = file_writer
    _command_executor = command_executor


async def apply_and_test_fix(
    fix_content: str, context: ErrorContext,
) -> bool:
    """Apply a fix and run tests to verify.

    Spec: §2.2.4

    In production: writes file, runs test suite.
    Stub: returns True if fix content is non-empty.
    """
    if _test_runner and _file_writer and context.file_path:
        await _file_writer(context.file_path, fix_content)
        return await _test_runner(context)

    # Stub mode: non-empty fix is "success"
    return bool(fix_content and len(fix_content.strip()) > 10)


async def run_tests(context: ErrorContext) -> bool:
    """Run test suite after War Room fixes.

    Spec: §2.2.4
    """
    if _test_runner:
        return await _test_runner(context)
    return True  # Stub


async def execute_command(command: str) -> dict:
    """Execute a cleanup command (user-space enforced).

    Spec: §2.2.4
    """
    if _command_executor:
        return await _command_executor(command)
    # Stub
    logger.debug(f"Stub execute: {command}")
    return {"exit_code": 0, "stdout": "", "stderr": ""}


# ═══════════════════════════════════════════════════════════════════
# §2.2.4 Level 1 — Quick Fix (Haiku)
# ═══════════════════════════════════════════════════════════════════


async def escalate_l1(
    state: PipelineState,
    context: ErrorContext,
) -> FixResult:
    """L1 Quick Fix — Haiku applies minimal syntax fix.

    Spec: §2.2.4 Level 1
    Cost: ~$0.005 illustrative
    """
    logger.info(
        f"[{state.project_id}] War Room L1: "
        f"{context.error_message[:100]}"
    )

    fix = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=(
            f"Fix this error with minimal changes. "
            f"Error: {context.error_message}\n\n"
            f"Context:\n{(context.file_content or '')[:L1_FILE_CONTEXT_CHARS]}"
        ),
        state=state,
        action="write_code",
    )

    success = await apply_and_test_fix(fix, context)

    result = FixResult(
        resolved=success,
        level=WarRoomLevel.L1_QUICK_FIX,
        fix_applied=fix,
        error_summary=context.error_message[:300],
    )

    if success:
        _log_resolution(state, result)
        logger.info(f"[{state.project_id}] War Room L1: RESOLVED")
    else:
        logger.info(f"[{state.project_id}] War Room L1: FAILED → escalate")

    return result


# ═══════════════════════════════════════════════════════════════════
# §2.2.4 Level 2 — Researched Fix (Scout → Engineer)
# ═══════════════════════════════════════════════════════════════════


async def escalate_l2(
    state: PipelineState,
    context: ErrorContext,
) -> FixResult:
    """L2 Researched Fix — Scout researches, Engineer applies.

    Spec: §2.2.4 Level 2
    Cost: ~$0.10 illustrative
    """
    logger.info(
        f"[{state.project_id}] War Room L2: researching "
        f"{context.error_message[:80]}"
    )

    # Scout researches the error
    research = await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"Find the solution for this error in official documentation. "
            f"Error: {context.error_message}\n"
            f"Stack: {getattr(state, 'selected_stack', 'unknown')}\n"
            f"Return: exact fix steps, relevant docs URLs, known issues."
        ),
        state=state,
        action="general",
    )

    # Engineer applies researched fix
    fix = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Apply this researched fix.\n\n"
            f"Error: {context.error_message}\n"
            f"Research findings:\n{research[:4000]}\n\n"
            f"File content:\n{(context.file_content or '')[:L2_FILE_CONTEXT_CHARS]}\n\n"
            f"Return the corrected file content."
        ),
        state=state,
        action="write_code",
    )

    success = await apply_and_test_fix(fix, context)

    result = FixResult(
        resolved=success,
        level=WarRoomLevel.L2_RESEARCHED,
        fix_applied=fix,
        research=research,
        error_summary=context.error_message[:300],
    )

    if success:
        _log_resolution(state, result)
        logger.info(f"[{state.project_id}] War Room L2: RESOLVED")
    else:
        logger.info(f"[{state.project_id}] War Room L2: FAILED → escalate")

    return result


# ═══════════════════════════════════════════════════════════════════
# §2.2.4 Level 3 — War Room (Opus orchestrates)
# ═══════════════════════════════════════════════════════════════════


async def escalate_l3(
    state: PipelineState,
    context: ErrorContext,
) -> FixResult:
    """L3 War Room — Opus maps deps, identifies root cause, plans rewrite.

    Spec: §2.2.4 Level 3
    Cost: ~$0.50 illustrative

    Opus:
      1. Maps dependency tree of failing component
      2. Identifies root cause (not symptom)
      3. Orders CLI cleanup commands (user-space enforced)
      4. Produces file-by-file rewrite plan

    Engineer executes each file rewrite.
    """
    logger.warning(
        f"[{state.project_id}] War Room L3 ACTIVATED: "
        f"{context.error_message[:100]}"
    )

    state.war_room_active = True

    # ── Opus analyzes and plans ──
    metadata_str = json.dumps(
        state.project_metadata, default=str,
    )[:L3_METADATA_CHARS]

    war_room_plan_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"WAR ROOM ACTIVATED.\n\n"
            f"Error that survived L1 (quick fix) and L2 (researched fix): "
            f"{context.error_message}\n\n"
            f"Project stack: {getattr(state, 'selected_stack', 'unknown')}\n"
            f"Project metadata: {metadata_str}\n"
            f"Files involved: {list(context.files.keys())}\n\n"
            f"Instructions:\n"
            f"1. Map the dependency tree of the failing component.\n"
            f"2. Identify the root cause (not the symptom).\n"
            f"3. Order specific CLI cleanup commands if needed "
            f"(e.g., pod deintegrate, flutter clean, rm -rf node_modules).\n"
            f"4. Produce a file-by-file rewrite plan listing each file, "
            f"what's wrong, and the exact fix.\n\n"
            f"Return JSON:\n"
            f'{{"root_cause": "...", "cleanup_commands": [...], '
            f'"rewrite_plan": [{{"file": "...", "issue": "...", "fix": "..."}}]}}'
        ),
        state=state,
        action="plan_architecture",
    )

    plan = _parse_plan(war_room_plan_raw)

    # ── Execute cleanup commands (user-space enforced) ──
    for cmd in plan.get("cleanup_commands", []):
        validated_cmd = enforce_user_space(cmd)
        await execute_command(validated_cmd)

    # ── Execute file-by-file rewrites via Engineer ──
    for rewrite in plan.get("rewrite_plan", []):
        file_path = rewrite.get("file", "")
        file_content = context.files.get(
            file_path, ""
        )[:L3_FILE_CONTEXT_CHARS]

        fix = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Rewrite this file per the War Room plan.\n\n"
                f"File: {file_path}\n"
                f"Issue: {rewrite.get('issue', '')}\n"
                f"Required fix: {rewrite.get('fix', '')}\n\n"
                f"Current content:\n{file_content}"
            ),
            state=state,
            action="write_code",
        )

        if _file_writer and file_path:
            await _file_writer(file_path, fix)

    # ── Run tests after all rewrites ──
    success = await run_tests(context)

    state.war_room_active = False

    result = FixResult(
        resolved=success,
        level=WarRoomLevel.L3_WAR_ROOM,
        fix_applied="war_room_plan",
        plan=plan,
        error_summary=context.error_message[:300],
    )

    _log_resolution(state, result)
    if success:
        logger.info(f"[{state.project_id}] War Room L3: RESOLVED")
    else:
        logger.error(f"[{state.project_id}] War Room L3: FAILED — pipeline halts")

    return result


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _parse_plan(raw: str) -> dict:
    """Parse Strategist's JSON plan from L3 response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    logger.warning("War Room L3: failed to parse plan JSON")
    return {
        "root_cause": "parse_error",
        "cleanup_commands": [],
        "rewrite_plan": [],
    }


def _log_resolution(state: PipelineState, result: FixResult) -> None:
    """Log War Room resolution to state history."""
    state.war_room_history.append({
        "level": result.level.value,
        "error": result.error_summary,
        "resolved": result.resolved,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **({
            "research": result.research[:500]
        } if result.research else {}),
        **({
            "plan": result.plan
        } if result.plan else {}),
    })