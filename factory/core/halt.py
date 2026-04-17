"""
AI Factory Pipeline v5.8.12 — Structured Halt Infrastructure

Issue 19 (Phase 1): Replace free-form `halt_reason = "unknown"` strings with
structured HaltReason dataclasses that carry code, title, detail, stage,
failing gate, remediation steps, and restore options.

Spec Authority: v5.8.12 Phase 1 §19
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HaltCode(str, Enum):
    """Structured halt codes. NO 'UNKNOWN' value is allowed — every halt
    must carry a specific, actionable code."""

    # Phase 1 (Issues 14, 19, 22)
    APP_NAME_MISSING = "APP_NAME_MISSING"
    APP_NAME_INVALID = "APP_NAME_INVALID"
    MODIFICATION_WITHOUT_PROJECT = "MODIFICATION_WITHOUT_PROJECT"
    PLATFORMS_NOT_SELECTED = "PLATFORMS_NOT_SELECTED"
    STACK_NOT_CONFIRMED = "STACK_NOT_CONFIRMED"

    # Reserved for later phases (already defined so call sites can reference)
    CREDENTIAL_MISSING = "CREDENTIAL_MISSING"
    QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"
    STAGE_VERIFICATION_FAILED = "STAGE_VERIFICATION_FAILED"
    DEPLOY_HEALTH_CHECK_FAILED = "DEPLOY_HEALTH_CHECK_FAILED"
    DEPLOY_TARGET_MISMATCH = "DEPLOY_TARGET_MISMATCH"
    PIPELINE_CANCELLED = "PIPELINE_CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    INTAKE_BLOCKED = "INTAKE_BLOCKED"
    UNCAUGHT_EXCEPTION = "UNCAUGHT_EXCEPTION"


@dataclass
class HaltReason:
    """Structured halt payload.

    Every field is mandatory except the three explicitly optional ones.
    A bare `HaltReason(code=..., title=..., detail=..., stage=...)` is
    always valid and renders a complete Telegram message.
    """

    code: HaltCode
    title: str
    detail: str
    stage: str
    failing_gate: Optional[str] = None
    remediation_steps: list[str] = field(default_factory=list)
    restore_options: list[str] = field(
        default_factory=lambda: ["/continue", "/cancel"]
    )

    def __post_init__(self) -> None:
        if not isinstance(self.code, HaltCode):
            # Accept string for back-compat, validate it is a known code.
            try:
                self.code = HaltCode(self.code)
            except ValueError as e:
                raise ValueError(
                    f"HaltReason.code must be a known HaltCode; got {self.code!r}"
                ) from e
        if not self.title or not self.title.strip():
            raise ValueError("HaltReason.title must not be empty")
        if not self.detail or not self.detail.strip():
            raise ValueError("HaltReason.detail must not be empty")
        if not self.stage or not self.stage.strip():
            raise ValueError("HaltReason.stage must not be empty")

    # ── Back-compat string rendering ────────────────────────────────
    def __str__(self) -> str:
        return f"[{self.code.value}] {self.title}: {self.detail}"

    def format_for_telegram(self) -> str:
        """Render the halt as a Telegram-ready block.

        Matches Issue 19 §4 template.
        """
        lines = [
            "⚠️ Pipeline halted",
            f"Stage: {self.stage}",
            f"Code: {self.code.value}",
            self.title,
            "",
            f"Details: {self.detail}",
        ]
        if self.failing_gate:
            lines.append(f"Failing gate: {self.failing_gate}")
        if self.remediation_steps:
            lines.append("")
            lines.append("Next steps:")
            for step in self.remediation_steps:
                lines.append(f"• {step}")
        if self.restore_options:
            lines.append("")
            lines.append("Options: " + " • ".join(self.restore_options))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "title": self.title,
            "detail": self.detail,
            "stage": self.stage,
            "failing_gate": self.failing_gate,
            "remediation_steps": list(self.remediation_steps),
            "restore_options": list(self.restore_options),
        }


def set_halt(state, reason: HaltReason) -> None:
    """Attach a HaltReason to a PipelineState and flip the halt flag.

    Writes both the structured payload (state.halt_reason_struct in
    project_metadata) and the string form (state.legal_halt_reason /
    project_metadata["halt_reason"]) for back-compat with existing
    Telegram templates that read plain strings.
    """
    state.project_metadata["halt_reason_struct"] = reason.to_dict()
    state.project_metadata["halt_reason"] = str(reason)
    # Legal halt is the existing cross-stage "stop the pipeline" signal.
    state.legal_halt = True
    state.legal_halt_reason = str(reason)
