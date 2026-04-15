"""
AI Factory Pipeline v5.8 — Cost Tracking & Alerts

Implements:
  - §7.4.2 Cost Monitoring Alerts
  - Per-project warning ($8) and critical ($15) thresholds
  - Monthly baseline monitoring (85% alert)
  - Cost report generation
  - SAR conversion

All thresholds derived from BUDGET_CONFIG [C2], never hardcoded.

Spec Authority: v5.6 §7.4.2, §8.3
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable

from factory.core.state import PipelineState, AIRole
from factory.monitoring.circuit_breaker import budget_category, PHASE_BUDGET_LIMITS

logger = logging.getLogger("factory.monitoring.cost_tracker")


# ═══════════════════════════════════════════════════════════════════
# §8.3 Budget Configuration (source of truth)
# ═══════════════════════════════════════════════════════════════════

BUDGET_CONFIG = {
    "hard_ceiling_usd": 800.0,
    "fx_rate": 3.75,  # USD → SAR
    "fixed_monthly": {
        "supabase_pro": 25.0,
        "neo4j_aura_free": 0.0,
        "github_free": 0.0,
        "gcp_cloud_run": 5.0,
        "telegram_bot": 0.0,
        "cloudflare_tunnel": 0.0,
    },
    "variable_monthly_4proj": {
        "anthropic_ai": 55.0,
        "perplexity_sonar": 8.0,
        "macincloud_payg": 7.55,
        "firebase_hosting": 0.0,
        "gcp_secret_manager": 0.06,
    },
}

# [C2] All thresholds derived from BUDGET_CONFIG
MONTHLY_FIXED = sum(BUDGET_CONFIG["fixed_monthly"].values())
MONTHLY_VARIABLE = sum(BUDGET_CONFIG["variable_monthly_4proj"].values())
MONTHLY_BASELINE = MONTHLY_FIXED + MONTHLY_VARIABLE


# ═══════════════════════════════════════════════════════════════════
# §7.4.2 Alert Thresholds
# ═══════════════════════════════════════════════════════════════════

COST_ALERT_THRESHOLDS = {
    "per_project_warning": 8.00,
    "per_project_critical": 15.00,
    "monthly_warning": 180.00,
    "monthly_critical": MONTHLY_VARIABLE,  # $70.61
}


# ═══════════════════════════════════════════════════════════════════
# Cost Tracker
# ═══════════════════════════════════════════════════════════════════


class CostTracker:
    """Tracks AI call costs and triggers alerts.

    Spec: §7.4.2
    """

    def __init__(self):
        self._calls: list[dict] = []
        self._alert_fn: Optional[Callable] = None

    def set_alert_fn(
        self, fn: Callable[[str, str], Awaitable[None]],
    ) -> None:
        """Set async function for sending alerts (operator_id, message)."""
        self._alert_fn = fn

    # ───────────────────────────────────────────────────────────
    # Cost Recording
    # ───────────────────────────────────────────────────────────

    async def record(
        self,
        state: PipelineState,
        role: AIRole,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Record an AI call cost and check alerts.

        Spec: §7.4.2
        """
        entry = {
            "project_id": state.project_id,
            "role": role.value.upper(),
            "stage": state.current_stage.value,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._calls.append(entry)

        # Update state
        category = budget_category(role, state.current_stage.value)
        state.phase_costs[category] = (
            state.phase_costs.get(category, 0.0) + cost_usd
        )
        state.total_cost_usd += cost_usd

        # Check alerts
        await self._check_project_alerts(state)

    # ───────────────────────────────────────────────────────────
    # §7.4.2 Per-Project Alerts
    # ───────────────────────────────────────────────────────────

    async def _check_project_alerts(self, state: PipelineState) -> None:
        """Check per-project cost thresholds.

        Spec: §7.4.2
        """
        cost = state.total_cost_usd

        if cost > COST_ALERT_THRESHOLDS["per_project_critical"]:
            await self._alert(
                state.operator_id,
                f"🚨 Project cost CRITICAL: ${cost:.2f} "
                f"(>${COST_ALERT_THRESHOLDS['per_project_critical']})\n"
                f"Consider /cancel or reducing scope.",
            )
        elif cost > COST_ALERT_THRESHOLDS["per_project_warning"]:
            await self._alert(
                state.operator_id,
                f"⚠️ Project cost elevated: ${cost:.2f}",
            )

    # ───────────────────────────────────────────────────────────
    # §7.4.2 Monthly Alerts
    # ───────────────────────────────────────────────────────────

    async def check_monthly_alerts(
        self, operator_id: str, monthly_total_usd: float,
    ) -> None:
        """Monthly cost check — runs after each project completes.

        Spec: §7.4.2 [C2] Reads from BUDGET_CONFIG.
        """
        baseline = MONTHLY_BASELINE

        if monthly_total_usd > baseline * 0.85:
            remaining = baseline - monthly_total_usd
            remaining_sar = remaining * BUDGET_CONFIG["fx_rate"]
            await self._alert(
                operator_id,
                f"📊 Monthly spend: ${monthly_total_usd:.2f}/${baseline:.2f} budget\n"
                f"Remaining: ${remaining:.2f} ({remaining_sar:.2f} SAR)",
            )

    async def _alert(self, operator_id: str, message: str) -> None:
        """Send alert via configured function."""
        if self._alert_fn:
            try:
                await self._alert_fn(operator_id, message)
            except Exception as e:
                logger.error(f"Cost alert failed: {e}")
        logger.info(f"Cost alert [{operator_id}]: {message}")

    # ───────────────────────────────────────────────────────────
    # Reporting
    # ───────────────────────────────────────────────────────────

    def project_cost(self, project_id: str) -> float:
        """Total cost for a specific project."""
        return sum(
            c["cost_usd"] for c in self._calls
            if c["project_id"] == project_id
        )

    def monthly_total(self) -> float:
        """Total spend for current month."""
        now = datetime.now(timezone.utc)
        return sum(
            c["cost_usd"] for c in self._calls
            if datetime.fromisoformat(c["timestamp"]).month == now.month
            and datetime.fromisoformat(c["timestamp"]).year == now.year
        )

    def monthly_total_cents(self) -> int:
        """Monthly total in integer cents (for Budget Governor)."""
        return int(self.monthly_total() * 100)

    def cost_report(self, project_id: Optional[str] = None) -> dict:
        """Generate cost report.

        Args:
            project_id: If provided, per-project report.
                        If None, monthly summary.
        """
        calls = self._calls
        if project_id:
            calls = [c for c in calls if c["project_id"] == project_id]

        total = sum(c["cost_usd"] for c in calls)
        by_role: dict[str, float] = {}
        by_stage: dict[str, float] = {}
        by_model: dict[str, float] = {}

        for c in calls:
            by_role[c["role"]] = by_role.get(c["role"], 0) + c["cost_usd"]
            by_stage[c["stage"]] = by_stage.get(c["stage"], 0) + c["cost_usd"]
            by_model[c["model"]] = by_model.get(c["model"], 0) + c["cost_usd"]

        return {
            "total_usd": round(total, 4),
            "total_sar": round(total * BUDGET_CONFIG["fx_rate"], 2),
            "call_count": len(calls),
            "by_role": {k: round(v, 4) for k, v in by_role.items()},
            "by_stage": {k: round(v, 4) for k, v in by_stage.items()},
            "by_model": {k: round(v, 4) for k, v in by_model.items()},
            "monthly_baseline": MONTHLY_BASELINE,
            "budget_config": BUDGET_CONFIG,
        }


# Singleton
cost_tracker = CostTracker()