"""
AI Factory Pipeline v5.8 — Circuit Breaker (Per-Role/Phase)

Implements:
  - §3.6.1 Per-Role/Phase Enforcement
  - Budget category mapping (role + stage → category)
  - 4-way decision on trip (authorize / skip / pause / cancel)
  - Per-project cap ($25) and monthly global cap ($80)

Spec Authority: v5.6 §3.6
"""

from __future__ import annotations

import logging
from typing import Optional, Callable, Awaitable

from factory.core.state import AIRole, PipelineState, Stage

logger = logging.getLogger("factory.monitoring.circuit_breaker")


# ═══════════════════════════════════════════════════════════════════
# §3.6 Phase Budget Limits
# ═══════════════════════════════════════════════════════════════════

PHASE_BUDGET_LIMITS: dict[str, float] = {
    "scout_research":      2.00,
    "strategist_planning":  5.00,
    "design_engine":       10.00,
    "codegen_engineer":    25.00,
    "testing_qa":           8.00,
    "deploy_release":       5.00,
    "legal_guardian":       3.00,
    "war_room_debug":      15.00,
}

PER_PROJECT_CAP = 25.00
MONTHLY_GLOBAL_CAP = 80.00


# ═══════════════════════════════════════════════════════════════════
# Category Mapping
# ═══════════════════════════════════════════════════════════════════


def budget_category(role: AIRole, stage: str) -> str:
    """Map role + stage to budget category.

    Spec: §3.6.1
    """
    if role == AIRole.SCOUT:
        return "scout_research"

    if role == AIRole.STRATEGIST:
        if "legal" in stage.lower() or "S1" in stage:
            return "legal_guardian"
        return "strategist_planning"

    if role == AIRole.ENGINEER:
        if "S3" in stage:
            return "codegen_engineer"
        if "S2" in stage:
            return "design_engine"
        if "S5" in stage:
            return "testing_qa"
        return "deploy_release"

    if role == AIRole.QUICK_FIX:
        if "war_room" in stage.lower():
            return "war_room_debug"
        return "testing_qa"

    return "scout_research"


# ═══════════════════════════════════════════════════════════════════
# Circuit Breaker Check
# ═══════════════════════════════════════════════════════════════════


class CircuitBreakerTripped(Exception):
    """Raised when circuit breaker trips and operator cancels."""
    pass


async def check_circuit_breaker(
    state: PipelineState,
    role: AIRole,
    cost_increment: float,
    decision_fn: Optional[Callable] = None,
) -> bool:
    """Check if cost would breach role/phase limit.

    Spec: §3.6.1

    Returns True if OK to proceed, False if should skip.
    Raises CircuitBreakerTripped if operator cancels.

    Args:
        state: Current pipeline state.
        role: AI role making the call.
        cost_increment: Estimated cost of the next call.
        decision_fn: Optional Telegram decision function
                     (for Copilot 4-way choice).
    """
    category = budget_category(role, state.current_stage.value)
    limit = PHASE_BUDGET_LIMITS.get(category, 5.00)
    current = state.phase_costs.get(category, 0.0)

    # ── Phase limit check ──
    if current + cost_increment > limit:
        state.circuit_breaker_triggered = True
        logger.warning(
            f"[{state.project_id}] Circuit breaker: "
            f"{category} ${current:.2f}+${cost_increment:.3f} > ${limit:.2f}"
        )

        if decision_fn:
            response = await decision_fn(
                state.operator_id,
                message=(
                    f"⚡ [{category}] budget: ${current:.2f}/${limit:.2f}.\n"
                    f"Role: {role.value} | Stage: {state.current_stage.value}\n"
                    f"Next call: ~${cost_increment:.3f}."
                ),
                options=[
                    f"💰 Authorize additional ${limit:.2f}",
                    "📋 Skip research, use existing intel",
                    "⏸ Pause and review costs",
                    "🛑 Cancel this phase",
                ],
            )
            return _handle_decision(state, response, category, limit)

        # No decision function (Autopilot) → skip
        return False

    # ── Per-project cap check ──
    if state.total_cost_usd + cost_increment > PER_PROJECT_CAP:
        logger.warning(
            f"[{state.project_id}] Per-project cap: "
            f"${state.total_cost_usd:.2f}+${cost_increment:.3f} > ${PER_PROJECT_CAP}"
        )
        state.circuit_breaker_triggered = True
        return False

    return True


def _handle_decision(
    state: PipelineState,
    response: str,
    category: str,
    limit: float,
) -> bool:
    """Handle operator's 4-way circuit breaker decision.

    Spec: §3.6.1
    """
    if response == "1":
        # Authorize: double the limit for this category
        state.phase_costs[f"{category}_authorized_extra"] = limit
        state.circuit_breaker_triggered = False
        logger.info(f"[{state.project_id}] Circuit breaker: authorized +${limit:.2f}")
        return True

    elif response == "2":
        # Skip: use existing intel
        state.circuit_breaker_triggered = False
        return False

    elif response == "3":
        # Pause: keep triggered, caller handles
        return False

    elif response == "4":
        # Cancel phase
        raise CircuitBreakerTripped(
            f"Operator cancelled phase at circuit breaker ({category})"
        )

    # Default: skip
    state.circuit_breaker_triggered = False
    return False


# ═══════════════════════════════════════════════════════════════════
# Cost Recording
# ═══════════════════════════════════════════════════════════════════


def record_cost(
    state: PipelineState, role: AIRole, cost_usd: float,
) -> None:
    """Record an AI call cost against the budget category.

    Spec: §3.6.1
    """
    category = budget_category(role, state.current_stage.value)
    state.phase_costs[category] = (
        state.phase_costs.get(category, 0.0) + cost_usd
    )
    state.total_cost_usd += cost_usd


def get_phase_summary(state: PipelineState) -> dict[str, dict]:
    """Get cost summary per phase category."""
    summary = {}
    for category, limit in PHASE_BUDGET_LIMITS.items():
        spent = state.phase_costs.get(category, 0.0)
        summary[category] = {
            "spent": round(spent, 4),
            "limit": limit,
            "remaining": round(limit - spent, 4),
            "pct": round(spent / limit * 100, 1) if limit > 0 else 0,
        }
    return summary