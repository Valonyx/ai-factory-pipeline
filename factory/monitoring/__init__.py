"""
AI Factory Pipeline v5.6 — Monitoring Module

Budget Governor, Circuit Breaker, Cost Tracking, Health Endpoints.
"""

# Import submodules explicitly first.
# Python's import system automatically places the MODULE into this
# package's namespace as 'budget_governor'. We do NOT overwrite it
# with the singleton — that would shadow the submodule and break
# `import factory.monitoring.budget_governor as bg_mod`.
# The singleton (budget_governor instance) is accessible via:
#   from factory.monitoring.budget_governor import budget_governor
import factory.monitoring.budget_governor as _bg_mod
import factory.monitoring.circuit_breaker as _cb_mod

from factory.monitoring.budget_governor import (
    BudgetGovernor,
    BudgetTier,
    BudgetExhaustedError,
    BudgetIntakeBlockedError,
    BUDGET_GOVERNOR_ENABLED,
    BUDGET_TIER_THRESHOLDS,
    HARD_CEILING_USD,
)

from factory.monitoring.circuit_breaker import (
    check_circuit_breaker,
    record_cost,
    get_phase_summary,
    budget_category,
    CircuitBreakerTripped,
    PHASE_BUDGET_LIMITS,
    PER_PROJECT_CAP,
    MONTHLY_GLOBAL_CAP,
)

from factory.monitoring.cost_tracker import (
    CostTracker,
    cost_tracker,
    COST_ALERT_THRESHOLDS,
    BUDGET_CONFIG,
    MONTHLY_BASELINE,
)

from factory.monitoring.health import (
    health_check,
    readiness_check,
    HeartbeatMonitor,
    PIPELINE_VERSION,
)

__all__ = [
    "BudgetGovernor", "BudgetTier", "budget_governor",
    "BudgetExhaustedError", "BudgetIntakeBlockedError",
    "BUDGET_GOVERNOR_ENABLED", "BUDGET_TIER_THRESHOLDS", "HARD_CEILING_USD",
    "check_circuit_breaker", "record_cost", "get_phase_summary",
    "budget_category", "CircuitBreakerTripped",
    "PHASE_BUDGET_LIMITS", "PER_PROJECT_CAP", "MONTHLY_GLOBAL_CAP",
    "CostTracker", "cost_tracker", "COST_ALERT_THRESHOLDS",
    "BUDGET_CONFIG", "MONTHLY_BASELINE",
    "health_check", "readiness_check", "HeartbeatMonitor", "PIPELINE_VERSION",
]
