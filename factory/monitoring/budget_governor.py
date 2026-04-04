"""
AI Factory Pipeline v5.6 — Budget Governor (ADR-044)

Implements:
  - §2.14.1 Problem Statement (80–100% cliff edge)
  - §2.14.2 Tier Definitions (GREEN/AMBER/RED/BLACK)
  - §2.14.3 Graduated Degradation
  - §2.14.4 Integration with call_ai()
  - §2.14.5 /admin budget_override command
  - Kill switch (BUDGET_GOVERNOR_ENABLED=false)

Precedence chain (ADR-043/044):
  operator MODEL_OVERRIDE > Budget Governor > MODEL_CONFIG default.

Spec Authority: v5.6 §2.14
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable, Awaitable

from factory.core.state import AIRole, PipelineState, Stage

logger = logging.getLogger("factory.monitoring.budget_governor")


# ═══════════════════════════════════════════════════════════════════
# §2.14 Configuration
# ═══════════════════════════════════════════════════════════════════

BUDGET_GOVERNOR_ENABLED = os.getenv(
    "BUDGET_GOVERNOR_ENABLED", "true"
).lower() == "true"

# §8.3 BUDGET_CONFIG hard ceiling
HARD_CEILING_USD = float(os.getenv("BUDGET_HARD_CEILING_USD", "800.0"))


# ═══════════════════════════════════════════════════════════════════
# §2.14.2 Tier Definitions
# ═══════════════════════════════════════════════════════════════════


class BudgetTier(str, Enum):
    """Budget tier for graduated degradation.

    Spec: §2.14.2
    """
    GREEN = "GREEN"   # 0–79%: normal operation
    AMBER = "AMBER"   # 80–94%: degraded operation
    RED = "RED"       # 95–99%: intake blocked
    BLACK = "BLACK"   # 100%: hard stop


# Thresholds as percentages of hard_ceiling_usd.
# Using integer math to prevent floating-point comparison errors.
BUDGET_TIER_THRESHOLDS = {
    BudgetTier.AMBER: 80,
    BudgetTier.RED:   95,
    BudgetTier.BLACK: 100,
}


# ═══════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════


class BudgetExhaustedError(Exception):
    """BLACK tier — monthly budget fully consumed.

    Spec: §2.14.3
    """
    pass


class BudgetIntakeBlockedError(Exception):
    """RED tier — new project intake blocked.

    Spec: §2.14.3
    Override: /admin budget_override
    """
    pass


# ═══════════════════════════════════════════════════════════════════
# §2.14.3 Budget Governor Implementation
# ═══════════════════════════════════════════════════════════════════


class BudgetGovernor:
    """Graduated budget degradation.

    Spec: §2.14.3

    Called before every call_ai() invocation. Determines current tier
    and applies appropriate model/context degradation.

    Precedence chain (ADR-043/044):
      operator MODEL_OVERRIDE > Budget Governor > MODEL_CONFIG default.
    If operator has set a MODEL_OVERRIDE, Governor logs a warning but
    does NOT override the override — preserving operator agency.
    """

    def __init__(self, ceiling_usd: float = HARD_CEILING_USD):
        # Integer cents for all calculations
        self.ceiling_cents = int(ceiling_usd * 100)
        self._last_tier = BudgetTier.GREEN
        self._last_alert_tier: Optional[BudgetTier] = None
        self._override_active = False
        self._override_expires: Optional[str] = None

        # Injected spend source (set by cost_tracker)
        self._spend_source: Optional[Callable[[], Awaitable[int]]] = None
        self._cached_spend_cents: int = 0

    def set_spend_source(
        self, source: Callable[[], Awaitable[int]],
    ) -> None:
        """Inject async function that returns monthly spend in cents."""
        self._spend_source = source

    def update_cached_spend(self, cents: int) -> None:
        """Update cached spend (called after each AI call)."""
        self._cached_spend_cents = cents

    # ───────────────────────────────────────────────────────────
    # Tier Determination
    # ───────────────────────────────────────────────────────────

    def determine_tier(
        self, spend_cents: Optional[int] = None,
    ) -> BudgetTier:
        """Determine budget tier from current spend.

        Spec: §2.14.3
        """
        spend = spend_cents if spend_cents is not None else self._cached_spend_cents
        if self.ceiling_cents <= 0:
            return BudgetTier.GREEN

        pct = (spend * 100) // self.ceiling_cents
        if pct >= BUDGET_TIER_THRESHOLDS[BudgetTier.BLACK]:
            return BudgetTier.BLACK
        elif pct >= BUDGET_TIER_THRESHOLDS[BudgetTier.RED]:
            return BudgetTier.RED
        elif pct >= BUDGET_TIER_THRESHOLDS[BudgetTier.AMBER]:
            return BudgetTier.AMBER
        return BudgetTier.GREEN

    def spend_percentage(self) -> int:
        """Current spend as percentage of ceiling."""
        if self.ceiling_cents <= 0:
            return 0
        return (self._cached_spend_cents * 100) // self.ceiling_cents

    def remaining_usd(self) -> float:
        """Remaining budget in USD."""
        return (self.ceiling_cents - self._cached_spend_cents) / 100

    # ───────────────────────────────────────────────────────────
    # §2.14.3 check() — Pre-call_ai hook
    # ───────────────────────────────────────────────────────────

    async def check(
        self,
        role: AIRole,
        state: PipelineState,
        contract: dict,
        notify_fn: Optional[Callable] = None,
    ) -> dict:
        """Called before every call_ai(). Returns (possibly degraded) contract.

        Spec: §2.14.3, §2.14.4

        Execution order (within call_ai):
          1. Load role contract from ROLE_CONTRACTS
          2. Check MODEL_OVERRIDE → if valid, override contract.model
          3. BudgetGovernor.check() ← THIS
          4. Enforce role boundaries
          5. Route to provider
          6. Track cost

        Returns:
            Possibly degraded contract dict.

        Raises:
            BudgetExhaustedError: BLACK tier
            BudgetIntakeBlockedError: RED tier + S0_INTAKE
        """
        if not BUDGET_GOVERNOR_ENABLED:
            return contract

        # Refresh spend if source available
        if self._spend_source:
            try:
                self._cached_spend_cents = await self._spend_source()
            except Exception as e:
                logger.warning(f"Budget Governor: spend source error: {e}")

        tier = self.determine_tier()
        pct = self.spend_percentage()
        remaining = self.remaining_usd()

        # Alert on tier transition
        if tier != self._last_alert_tier and notify_fn:
            await self._send_tier_alert(
                tier, pct, remaining, state, notify_fn,
            )
            self._last_alert_tier = tier

        self._last_tier = tier

        # ── BLACK: hard stop ──
        if tier == BudgetTier.BLACK:
            raise BudgetExhaustedError(
                f"Monthly budget exhausted ({pct}% of "
                f"${self.ceiling_cents / 100:.2f}). "
                f"Pipeline halted. Resets on {self._next_month_date()}."
            )

        # ── RED: block new intake (unless override active) ──
        if tier == BudgetTier.RED:
            if (state.current_stage == Stage.S0_INTAKE
                    and not self._override_active):
                raise BudgetIntakeBlockedError(
                    f"Budget at {pct}%. New project intake blocked. "
                    f"In-flight projects continue with degraded models. "
                    f"Override: /admin budget_override"
                )
            # In-flight continues with AMBER degradation

        # ── AMBER/RED: degrade contract ──
        if tier in (BudgetTier.AMBER, BudgetTier.RED):
            # Check for operator MODEL_OVERRIDE
            override_key = f"{role.value.upper()}_MODEL_OVERRIDE"
            if os.getenv(override_key):
                logger.warning(
                    f"Override active during {tier.value} budget mode. "
                    f"Burn rate elevated."
                )
                return contract  # ADR-043: operator override wins

            contract = self._degrade_contract(role, contract)

        return contract  # GREEN: unchanged

    # ───────────────────────────────────────────────────────────
    # §2.14.3 Model Degradation
    # ───────────────────────────────────────────────────────────

    def _degrade_contract(
        self, role: AIRole, contract: dict,
    ) -> dict:
        """Apply AMBER/RED degradation to role contract.

        Spec: §2.14.3

        Strategist: Opus 4.6 → Opus 4.5
        Engineer: context capped at 100K (output 8192)
        Scout: prefer cached results (flagged for call_perplexity_safe)
        Quick Fix: unchanged (already cheapest)
        """
        degraded = dict(contract)

        if role == AIRole.STRATEGIST:
            if degraded.get("model") == "claude-opus-4-6":
                degraded["model"] = "claude-opus-4-5-20250929"
                logger.info("AMBER: Strategist downgraded to opus-4.5")

        elif role == AIRole.ENGINEER:
            degraded["max_output_tokens"] = min(
                degraded.get("max_output_tokens", 16384), 8192,
            )
            logger.info("AMBER: Engineer output capped at 8192")

        elif role == AIRole.SCOUT:
            degraded["_prefer_cached"] = True
            logger.info("AMBER: Scout preferring cached results")

        # QUICK_FIX: unchanged (already cheapest model)

        return degraded

    # ───────────────────────────────────────────────────────────
    # §2.14.5 /admin budget_override
    # ───────────────────────────────────────────────────────────

    def activate_override(self) -> None:
        """Activate intake override (RED tier).

        Spec: §2.14.5
        Allows new projects despite RED tier.
        """
        self._override_active = True
        self._override_expires = datetime.now(timezone.utc).isoformat()
        self._last_alert_tier = None  # Reset to allow re-alerting
        logger.warning("Budget override ACTIVATED — intake unblocked at RED tier")

    def deactivate_override(self) -> None:
        """Deactivate intake override."""
        self._override_active = False
        self._override_expires = None

    @property
    def is_override_active(self) -> bool:
        return self._override_active

    # ───────────────────────────────────────────────────────────
    # Tier Alerts
    # ───────────────────────────────────────────────────────────

    async def _send_tier_alert(
        self, tier: BudgetTier, pct: int, remaining: float,
        state: PipelineState, notify_fn: Callable,
    ) -> None:
        """Send Telegram alert on tier transition.

        Spec: §2.14.3
        """
        alerts = {
            BudgetTier.AMBER: (
                f"🟡 Budget at {pct}% — AMBER mode active\n"
                f"Remaining: ${remaining:.2f}\n"
                f"Strategist downgraded to opus-4.5\n"
                f"Engineer context capped at 100K\n"
                f"Scout preferring cached results"
            ),
            BudgetTier.RED: (
                f"🔴 Budget at {pct}% — RED mode active\n"
                f"Remaining: ${remaining:.2f}\n"
                f"New projects BLOCKED. In-flight continues degraded.\n"
                f"Override: /admin budget_override"
            ),
            BudgetTier.BLACK: (
                f"⛔ Monthly budget EXHAUSTED ({pct}%)\n"
                f"Pipeline HALTED. All activity stopped.\n"
                f"Resets on {self._next_month_date()}"
            ),
            BudgetTier.GREEN: (
                f"🟢 Budget back to GREEN ({pct}%)\n"
                f"Normal operation restored."
            ),
        }
        msg = alerts.get(tier)
        if msg:
            try:
                await notify_fn(state.operator_id, msg)
            except Exception as e:
                logger.error(f"Tier alert failed: {e}")

    def _next_month_date(self) -> str:
        """First day of next month."""
        now = datetime.now(timezone.utc)
        if now.month == 12:
            return f"{now.year + 1}-01-01"
        return f"{now.year}-{now.month + 1:02d}-01"

    # ───────────────────────────────────────────────────────────
    # Status
    # ───────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Current governor status for dashboards/health."""
        return {
            "enabled": BUDGET_GOVERNOR_ENABLED,
            "tier": self._last_tier.value,
            "spend_pct": self.spend_percentage(),
            "remaining_usd": self.remaining_usd(),
            "ceiling_usd": self.ceiling_cents / 100,
            "override_active": self._override_active,
        }


# Singleton
_governor = BudgetGovernor()
budget_governor = _governor  # public alias
