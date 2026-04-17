"""
AI Factory Pipeline v5.8.12 — Output Quality Gates
Issue 17: Every stage output is validated before marking COMPLETE.
"""
from __future__ import annotations
import re, logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("factory.core.quality_gates")

@dataclass
class GateResult:
    name: str
    passed: bool
    observed: Any
    required: Any
    message: str = ""

@dataclass
class QualityGateFailure(Exception):
    stage: str
    failed_gates: list[GateResult] = field(default_factory=list)
    recommended_action: str = "retry"
    regress_to: Optional[str] = None  # e.g. "S1_LEGAL" if regression is needed

    def format_for_telegram(self) -> str:
        lines = [f"Quality gate failed — Stage {self.stage}"]
        for g in self.failed_gates:
            lines.append(f"  x {g.name}: got {g.observed!r}, need {g.required!r}")
            if g.message:
                lines.append(f"    {g.message}")
        lines.append(f"\nRecommended: {self.recommended_action}")
        if self.regress_to:
            lines.append(f"Regress to: {self.regress_to}")
        return "\n".join(lines)

# ── Placeholder token pattern ────────────────────────────────────
_PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z_]{2,}\]")

def check_no_placeholders(text: str, field_name: str) -> GateResult:
    tokens = _PLACEHOLDER_RE.findall(text)
    return GateResult(
        name=f"no_placeholders:{field_name}",
        passed=len(tokens) == 0,
        observed=tokens[:5],
        required=[],
        message=f"Found unfilled placeholder tokens: {tokens[:5]}" if tokens else "",
    )

def check_min_length(text: str, min_chars: int, field_name: str) -> GateResult:
    return GateResult(
        name=f"min_length:{field_name}",
        passed=len(text) >= min_chars,
        observed=len(text),
        required=min_chars,
        message=f"Content too short: {len(text)} < {min_chars} chars" if len(text) < min_chars else "",
    )

def check_min_list(lst: list, min_count: int, field_name: str) -> GateResult:
    return GateResult(
        name=f"min_list:{field_name}",
        passed=len(lst) >= min_count,
        observed=len(lst),
        required=min_count,
        message=f"List too short: {len(lst)} < {min_count} items" if len(lst) < min_count else "",
    )

def check_file_size(path: str, min_bytes: int, field_name: str) -> GateResult:
    import os
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError):
        size = 0
    return GateResult(
        name=f"file_size:{field_name}",
        passed=size >= min_bytes,
        observed=size,
        required=min_bytes,
        message=f"File too small: {size} < {min_bytes} bytes" if size < min_bytes else "",
    )

def raise_if_failed(stage: str, results: list[GateResult],
                    recommended_action: str = "retry",
                    regress_to: Optional[str] = None) -> None:
    failed = [r for r in results if not r.passed]
    if failed:
        raise QualityGateFailure(
            stage=stage,
            failed_gates=failed,
            recommended_action=recommended_action,
            regress_to=regress_to,
        )
