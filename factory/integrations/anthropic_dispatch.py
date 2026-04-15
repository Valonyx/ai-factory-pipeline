"""
AI Factory Pipeline v5.8 — Anthropic Dispatch Compatibility Shim

Re-exports from factory.core.roles and factory.monitoring.budget_governor
for backwards-compatibility with test imports expecting a combined module.

Spec Authority: v5.8 §2.4, §2.14
"""

from __future__ import annotations

from factory.core.state import (
    AIRole,
    PHASE_BUDGET_LIMITS,
    ROLE_CONTRACTS as _ROLE_CONTRACTS_RAW,
)
from factory.integrations.perplexity import SONAR_PRO_TRIGGERS
from factory.monitoring.budget_governor import (
    BudgetGovernor,
    BudgetTier,
)


class BudgetExhaustedError(Exception):
    """Raised when the monthly or per-project budget is exhausted."""
    pass


# Convert RoleContract objects to plain dicts for backwards-compat test access
def _to_dict(rc) -> dict:
    d = {
        "model": rc.model,
        "can_read_web": rc.can_read_web,
        "can_write_code": rc.can_write_code,
        "can_write_files": rc.can_write_files,
        "can_plan_architecture": rc.can_plan_architecture,
        "can_decide_legal": rc.can_decide_legal,
        "can_manage_war_room": rc.can_manage_war_room,
        "max_output_tokens": rc.max_output_tokens,
    }
    # Scout uses Perplexity, not Anthropic
    if rc.role == AIRole.SCOUT:
        d["provider"] = "perplexity"
    else:
        d["provider"] = "anthropic"
    return d


ROLE_CONTRACTS: dict = {
    role: _to_dict(contract)
    for role, contract in _ROLE_CONTRACTS_RAW.items()
}

# Stage budget limits for circuit breaker (USD per stage)
_STAGE_BUDGET_LIMITS: dict = {
    "S0_INTAKE":    0.50,
    "S1_LEGAL":     1.00,
    "S2_BLUEPRINT": 2.00,
    "S4_CODEGEN":   5.00,
    "S5_BUILD":     3.00,
    "S6_TEST":      2.00,
    "S7_DEPLOY":    1.00,
    "S8_VERIFY":    1.00,
    "S9_HANDOFF":   0.50,
}


async def check_circuit_breaker(state, estimated_cost_usd: float) -> bool:
    """Check if adding estimated_cost_usd to current stage spend exceeds limit.

    Args:
        state: PipelineState with current_stage and stage_cost_usd
        estimated_cost_usd: Cost of the upcoming operation

    Returns:
        True if within limits, False if would exceed stage limit
    Spec: §3.6 Circuit Breaker
    """
    stage_key = state.current_stage.value if hasattr(state.current_stage, "value") else str(state.current_stage)
    limit = _STAGE_BUDGET_LIMITS.get(stage_key, 2.00)
    current = getattr(state, "stage_cost_usd", 0.0) or 0.0
    return (current + estimated_cost_usd) <= limit


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost for an Anthropic API call without making it.

    Spec: §2.4 Role Contracts
    """
    from factory.integrations.anthropic import calculate_cost
    return calculate_cost(model, input_tokens, output_tokens)


__all__ = [
    "ROLE_CONTRACTS", "PHASE_BUDGET_LIMITS", "SONAR_PRO_TRIGGERS",
    "BudgetGovernor", "BudgetTier", "BudgetExhaustedError",
    "check_circuit_breaker", "estimate_cost",
]
