"""
AI Factory Pipeline v5.6 — War Room Level Definitions

Implements:
  - §2.2.4 WarRoomLevel enum (L1/L2/L3)
  - Fix result structures
  - Configuration constants
  - War Room event types for Neo4j logging

Spec Authority: v5.6 §2.2.4
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
# §2.2.4 War Room Levels
# ═══════════════════════════════════════════════════════════════════


class WarRoomLevel(IntEnum):
    """War Room escalation levels.

    Spec: §2.2.4

    L1: Quick Fix (Haiku) — syntax fix (~$0.005 illustrative)
    L2: Researched Fix (Scout → Engineer) — docs research (~$0.10)
    L3: War Room (Opus orchestrates) — full rewrite plan (~$0.50)
    """
    L1_QUICK_FIX = 1
    L2_RESEARCHED = 2
    L3_WAR_ROOM = 3


# ═══════════════════════════════════════════════════════════════════
# Fix Result
# ═══════════════════════════════════════════════════════════════════


class FixResult:
    """Result of a War Room fix attempt."""

    def __init__(
        self,
        resolved: bool,
        level: WarRoomLevel,
        fix_applied: str = "",
        research: str = "",
        plan: Optional[dict] = None,
        cost_usd: float = 0.0,
        error_summary: str = "",
    ):
        self.resolved = resolved
        self.level = level
        self.fix_applied = fix_applied
        self.research = research
        self.plan = plan
        self.cost_usd = cost_usd
        self.error_summary = error_summary

    def to_dict(self) -> dict:
        result = {
            "resolved": self.resolved,
            "level": self.level.value,
            "fix_applied": self.fix_applied[:200],
            "cost_usd": round(self.cost_usd, 4),
        }
        if self.research:
            result["research"] = self.research[:500]
        if self.plan:
            result["plan"] = self.plan
        return result


# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════

# Max retries at each level before escalating
MAX_L1_ATTEMPTS = 1
MAX_L2_ATTEMPTS = 1
MAX_L3_ATTEMPTS = 1

# Total retry loops S5→S3 before halt
MAX_RETRY_CYCLES = 3

# Context truncation limits (tokens ≈ chars/4)
L1_FILE_CONTEXT_CHARS = 4000
L2_FILE_CONTEXT_CHARS = 8000
L3_FILE_CONTEXT_CHARS = 8000
L3_METADATA_CHARS = 4000

# GUI failure pivot threshold (§2.3.2)
GUI_FAILURE_THRESHOLD = 3


# ═══════════════════════════════════════════════════════════════════
# Error Context
# ═══════════════════════════════════════════════════════════════════


class ErrorContext:
    """Structured error context for War Room escalation."""

    def __init__(
        self,
        error_message: str,
        error_type: str = "unknown",
        file_path: Optional[str] = None,
        file_content: Optional[str] = None,
        files: Optional[dict[str, str]] = None,
        stack_trace: str = "",
        test_output: str = "",
        stage: str = "",
    ):
        self.error_message = error_message
        self.error_type = error_type
        self.file_path = file_path
        self.file_content = file_content
        self.files = files or {}
        self.stack_trace = stack_trace
        self.test_output = test_output
        self.stage = stage

    def to_dict(self) -> dict:
        return {
            "error_message": self.error_message[:500],
            "error_type": self.error_type,
            "file_path": self.file_path,
            "file_content": (self.file_content or "")[:L2_FILE_CONTEXT_CHARS],
            "files": {k: v[:1000] for k, v in self.files.items()},
            "stack_trace": self.stack_trace[:2000],
            "test_output": self.test_output[:2000],
            "stage": self.stage,
        }