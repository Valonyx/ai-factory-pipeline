"""
AI Factory Pipeline v5.8.14 — ModeStore

Issue 36: Single source of truth for all three mode axes.

Three axes:
  Master    → BASIC / BALANCED / TURBO / CUSTOM   (AI provider strategy)
  Execution → CLOUD / LOCAL / HYBRID              (where code runs)
  Transport → POLLING / WEBHOOK                   (bot connection type)

All three axes are persisted to Supabase operator preferences via
set_operator_preference().  ModeStore is the ONLY place that reads
and writes these values — bot.py and other callers go through it.

Auto-detect transport default:
  If TELEGRAM_WEBHOOK_URL is set in the environment → "webhook"
  Otherwise → "polling"

Usage:
    store = ModeStore(operator_id)
    await store.load()                          # populate from Supabase
    mm = store.master_mode                      # MasterMode enum
    await store.set_master("basic")             # persist immediately
    await store.set_transport("polling")
    state = store.apply_to_state(state)         # stamp all axes onto PipelineState
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from factory.core.mode_router import MasterMode
from factory.core.state import ExecutionMode, AutonomyMode

from factory.telegram.decisions import load_operator_preferences, set_operator_preference  # noqa: E402

logger = logging.getLogger("factory.telegram.mode_store")

# ── Transport mode strings ─────────────────────────────────────────
TRANSPORT_POLLING = "polling"
TRANSPORT_WEBHOOK = "webhook"


def _detect_transport_default() -> str:
    """Auto-detect transport default from environment.

    If TELEGRAM_WEBHOOK_URL is set (Render deployment), default to webhook.
    Otherwise, assume local polling.
    """
    return TRANSPORT_WEBHOOK if os.getenv("TELEGRAM_WEBHOOK_URL") else TRANSPORT_POLLING


class ModeStore:
    """Typed, persistent wrapper for all three mode axes.

    Issue 36 — replaces scattered `prefs.get(...)` calls with a single
    authoritative object.

    Lifecycle:
        store = ModeStore(operator_id)
        await store.load()          # must call before reading axes
        ... read/write ...
    """

    def __init__(self, operator_id: str) -> None:
        self.operator_id = operator_id
        self._prefs: dict = {}
        self._loaded = False

    # ── load ──────────────────────────────────────────────────────────

    async def load(self) -> "ModeStore":
        """Load preferences from Supabase (or memory cache) into this store."""
        self._prefs = await load_operator_preferences(self.operator_id)
        self._loaded = True
        return self

    # ── typed property readers ─────────────────────────────────────────

    @property
    def master_mode(self) -> MasterMode:
        """Active master axis value (defaults to BASIC — free tier, fail-safe to $0)."""
        raw = self._prefs.get("master_mode", "basic")
        try:
            return MasterMode(raw)
        except ValueError:
            return MasterMode.BASIC

    @property
    def execution_mode(self) -> ExecutionMode:
        """Active execution axis value (defaults to LOCAL)."""
        raw = self._prefs.get("execution_mode", "local")
        try:
            return ExecutionMode(raw)
        except ValueError:
            return ExecutionMode.LOCAL

    @property
    def autonomy_mode(self) -> AutonomyMode:
        """Active autonomy mode value (defaults to AUTOPILOT)."""
        raw = self._prefs.get("autonomy_mode", "autopilot")
        try:
            return AutonomyMode(raw)
        except ValueError:
            return AutonomyMode.AUTOPILOT

    @property
    def transport_mode(self) -> str:
        """Active transport axis value: 'polling' or 'webhook'."""
        return self._prefs.get("transport_mode", _detect_transport_default())

    # ── typed setters (persist immediately) ───────────────────────────

    async def set_master(self, value: str) -> None:
        """Validate and persist master mode."""
        mm = MasterMode(value.lower())   # raises ValueError on bad input
        await self._set("master_mode", mm.value)

    async def set_execution(self, value: str) -> None:
        """Validate and persist execution mode."""
        em = ExecutionMode(value.lower())
        await self._set("execution_mode", em.value)

    async def set_autonomy(self, value: str) -> None:
        """Validate and persist autonomy mode."""
        am = AutonomyMode(value.lower())
        await self._set("autonomy_mode", am.value)

    async def set_transport(self, value: str) -> None:
        """Validate and persist transport mode.

        Accepts 'polling' or 'webhook'.
        """
        if value not in (TRANSPORT_POLLING, TRANSPORT_WEBHOOK):
            raise ValueError(f"transport_mode must be 'polling' or 'webhook', got {value!r}")
        await self._set("transport_mode", value)

    # ── apply to PipelineState ─────────────────────────────────────────

    def apply_to_state(self, state) -> object:
        """Stamp all three axes onto a PipelineState.

        Mutates state in-place and returns it (for chaining).
        Issue 36: master_mode was never applied before this fix.
        """
        state.master_mode    = self.master_mode
        state.execution_mode = self.execution_mode
        state.autonomy_mode  = self.autonomy_mode
        return state

    # ── internals ────────────────────────────────────────────────────

    async def _set(self, key: str, value: str) -> None:
        self._prefs[key] = value
        await set_operator_preference(self.operator_id, key, value)

    # ── scope-aware effective readers (Issue 51) ──────────────────────

    @staticmethod
    async def get_effective_execution_mode(
        operator_id: str,
        state: Optional[object] = None,
    ) -> ExecutionMode:
        """Return the execution mode that SHOULD be applied right now.

        Scope precedence (highest first):
          1. Active PipelineState.execution_mode (project-scoped)
          2. Operator pref (operator-scoped, Supabase → SQLite → defaults)
          3. CLOUD (ultimate default)
        """
        if state is not None:
            em = getattr(state, "execution_mode", None)
            if isinstance(em, ExecutionMode):
                return em
        prefs = await load_operator_preferences(operator_id)
        try:
            return ExecutionMode(prefs.get("execution_mode", "local"))
        except ValueError:
            return ExecutionMode.LOCAL

    @staticmethod
    async def get_effective_master_mode(
        operator_id: str,
        state: Optional[object] = None,
    ) -> MasterMode:
        """Return the master mode that SHOULD be applied right now.

        Scope precedence: PipelineState.master_mode → operator pref → BASIC.
        Default is BASIC (free tier, $0 fail-safe) to match _PREFS_DEFAULTS.
        """
        if state is not None:
            mm = getattr(state, "master_mode", None)
            if isinstance(mm, MasterMode):
                return mm
        prefs = await load_operator_preferences(operator_id)
        try:
            return MasterMode(prefs.get("master_mode", "basic"))
        except ValueError:
            return MasterMode.BASIC

    def __repr__(self) -> str:
        if not self._loaded:
            return f"ModeStore(operator={self.operator_id!r}, not loaded)"
        return (
            f"ModeStore(operator={self.operator_id!r}, "
            f"master={self.master_mode.value}, "
            f"execution={self.execution_mode.value}, "
            f"transport={self.transport_mode})"
        )
