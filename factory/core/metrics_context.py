"""
v5.8.15 Issue 50 — contextvars-based per-stage activity counters.

Rationale: stage handlers dispatch work through many layers (call_ai,
mother_memory.store_*, file writes). Threading `state` to every call site
would require invasive edits. A ContextVar lets pipeline_node set a
collector at stage entry and every downstream `bump_*` call records into
it without needing the state reference.

At stage exit, pipeline_node merges the collected counters into
state.metrics (the durable Pydantic field) before the snapshot persists.
"""

from __future__ import annotations

import contextvars
from datetime import datetime, timezone
from typing import Optional, TypedDict


class _StageCounters(TypedDict):
    provider_calls: int
    artifacts_produced: int
    mm_writes: int
    last_provider_call_at: Optional[str]
    last_artifact_at: Optional[str]
    last_mm_write_at: Optional[str]


_current: contextvars.ContextVar[Optional[_StageCounters]] = contextvars.ContextVar(
    "_v5815_stage_counters", default=None
)


def _new_counters() -> _StageCounters:
    return {
        "provider_calls": 0,
        "artifacts_produced": 0,
        "mm_writes": 0,
        "last_provider_call_at": None,
        "last_artifact_at": None,
        "last_mm_write_at": None,
    }


def start_stage_metrics() -> _StageCounters:
    """Called by pipeline_node at stage entry. Installs a fresh counter dict
    into the current context. Returns the dict so pipeline_node can read it
    back at stage exit."""
    counters = _new_counters()
    _current.set(counters)
    return counters


def clear_stage_metrics() -> None:
    _current.set(None)


def get_current_counters() -> Optional[_StageCounters]:
    return _current.get()


def _bump(field: str, n: int = 1, stamp_field: Optional[str] = None) -> None:
    counters = _current.get()
    if counters is None:
        return  # no active stage context — silently ignore
    counters[field] = counters.get(field, 0) + n  # type: ignore[literal-required]
    if stamp_field:
        counters[stamp_field] = datetime.now(timezone.utc).isoformat()  # type: ignore[literal-required]


def bump_provider_call(n: int = 1) -> None:
    _bump("provider_calls", n, "last_provider_call_at")


def bump_artifact(n: int = 1) -> None:
    _bump("artifacts_produced", n, "last_artifact_at")


def bump_mm_write(n: int = 1) -> None:
    _bump("mm_writes", n, "last_mm_write_at")
