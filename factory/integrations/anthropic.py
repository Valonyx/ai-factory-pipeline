"""
AI Factory Pipeline v5.6 — Anthropic + Perplexity AI Dispatch

Implements:
  - §2.2 AI Role contracts and dispatch
  - §3.1 Perplexity Sonar integration (Scout)
  - §3.2 Strategist cost control
  - §2.14 Budget Governor integration
  - §3.6 Circuit breaker per-role cost tracking
  - Role boundary enforcement

Spec Authority: v5.6 §2.2, §3.1, §3.2, §3.6, §2.14
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    PipelineState,
    Stage,
    TechStack,
)

logger = logging.getLogger("factory.integrations.anthropic")


# ═══════════════════════════════════════════════════════════════════
# §2.2 Role Contracts (Model Bindings)
# ═══════════════════════════════════════════════════════════════════

ROLE_CONTRACTS: dict[AIRole, dict] = {
    AIRole.STRATEGIST: {
        "model": "claude-opus-4-6",
        "max_output_tokens": 16384,
        "temperature": 0.3,
        "provider": "anthropic",
        "allowed_actions": [
            "plan_architecture", "decide_legal",
            "select_stack", "design_review",
        ],
        "cost_per_m_input": 5.0,
        "cost_per_m_output": 25.0,
    },
    AIRole.ENGINEER: {
        "model": "claude-sonnet-4-5-20250929",
        "max_output_tokens": 16384,
        "temperature": 0.2,
        "provider": "anthropic",
        "allowed_actions": [
            "write_code", "generate_tests", "write_docs",
            "build_scripts", "deploy_scripts", "general",
        ],
        "cost_per_m_input": 3.0,
        "cost_per_m_output": 15.0,
    },
    AIRole.QUICK_FIX: {
        "model": "claude-haiku-4-5-20251001",
        "max_output_tokens": 4096,
        "temperature": 0.1,
        "provider": "anthropic",
        "allowed_actions": [
            "write_code", "general", "validate",
        ],
        "cost_per_m_input": 0.80,
        "cost_per_m_output": 4.0,
    },
    AIRole.SCOUT: {
        "model": "sonar",
        "max_output_tokens": 2048,
        "temperature": 0.3,
        "provider": "perplexity",
        "allowed_actions": ["general"],
        "cost_per_m_input": 1.0,
        "cost_per_m_output": 1.0,
    },
}


# §3.1.2 Sonar Pro trigger keywords
SONAR_PRO_TRIGGERS = [
    "regulation", "compliance", "legal", "pdpl", "cst", "sama",
    "ministry of commerce", "license", "permit",
    "root cause", "dependency conflict", "breaking change",
    "migration guide", "deprecated",
    "competing apps", "market analysis", "trending", "design trends",
]

# §3.2.2 Strategist usage limits
STRATEGIST_USAGE_LIMITS = {
    "S1_LEGAL":     {"max_calls": 2, "max_input_tokens": 8000},
    "S2_BLUEPRINT": {"max_calls": 3, "max_input_tokens": 16000},
    "WAR_ROOM_L3":  {"max_calls": 2, "max_input_tokens": 16000},
    "LEGAL_CHECKS": {"max_calls": 1, "max_input_tokens": 4000},
}

# §3.6 Phase budget limits
PHASE_BUDGET_LIMITS = {
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
# §2.14 Budget Governor
# ═══════════════════════════════════════════════════════════════════

BUDGET_GOVERNOR_ENABLED = os.getenv(
    "BUDGET_GOVERNOR_ENABLED", "true"
).lower() == "true"


class BudgetTier:
    GREEN = "GREEN"   # 0-79%
    AMBER = "AMBER"   # 80-94%
    RED = "RED"       # 95-99%
    BLACK = "BLACK"   # 100%


BUDGET_TIER_THRESHOLDS = {
    BudgetTier.AMBER: 80,
    BudgetTier.RED:   95,
    BudgetTier.BLACK: 100,
}


class BudgetExhaustedError(Exception):
    """BLACK tier — monthly budget fully consumed."""
    pass


class BudgetIntakeBlockedError(Exception):
    """RED tier — new project intake blocked."""
    pass


class BudgetGovernor:
    """Graduated budget degradation.

    Spec: §2.14
    Called before every call_ai(). Determines tier and applies
    appropriate model/context degradation.

    Precedence (ADR-043/044):
      operator MODEL_OVERRIDE > Budget Governor > MODEL_CONFIG default.
    """

    def __init__(self, ceiling_usd: float = 800.0):
        self.ceiling_cents = int(ceiling_usd * 100)
        self._last_tier = BudgetTier.GREEN
        self._last_alert_tier: Optional[str] = None
        self._monthly_spend_cents: int = 0

    def set_monthly_spend(self, cents: int) -> None:
        """Update cached monthly spend (called periodically)."""
        self._monthly_spend_cents = cents

    def determine_tier(self, spend_cents: Optional[int] = None) -> str:
        """Determine budget tier from spend."""
        spend = spend_cents if spend_cents is not None else self._monthly_spend_cents
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

    def check(
        self, role: AIRole, state: PipelineState, contract: dict,
    ) -> dict:
        """Check budget tier and apply degradation if needed.

        Returns (possibly degraded) contract dict.
        Raises on BLACK/RED-intake.
        """
        if not BUDGET_GOVERNOR_ENABLED:
            return contract

        tier = self.determine_tier()
        spend_pct = (
            (self._monthly_spend_cents * 100) // self.ceiling_cents
            if self.ceiling_cents > 0 else 0
        )

        if tier == BudgetTier.BLACK:
            raise BudgetExhaustedError(
                f"Monthly budget exhausted ({spend_pct}%). Pipeline halted."
            )

        if tier == BudgetTier.RED and state.current_stage == Stage.S0_INTAKE:
            raise BudgetIntakeBlockedError(
                f"Budget at {spend_pct}%. New project intake blocked."
            )

        if tier in (BudgetTier.AMBER, BudgetTier.RED):
            contract = self._degrade(role, contract)

        self._last_tier = tier
        return contract

    def _degrade(self, role: AIRole, contract: dict) -> dict:
        """Apply AMBER/RED degradation.

        Spec: §2.14.3
        """
        degraded = dict(contract)

        if role == AIRole.STRATEGIST:
            if degraded.get("model") == "claude-opus-4-6":
                degraded["model"] = "claude-opus-4-5-20250929"
                logger.info("AMBER: Strategist downgraded to opus-4.5")

        elif role == AIRole.ENGINEER:
            degraded["max_output_tokens"] = min(
                degraded.get("max_output_tokens", 16384), 8192
            )
            logger.info("AMBER: Engineer output capped at 8192")

        return degraded


budget_governor = BudgetGovernor()


# ═══════════════════════════════════════════════════════════════════
# §3.6 Circuit Breaker
# ═══════════════════════════════════════════════════════════════════


def _budget_category(role: AIRole, stage: str) -> str:
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
        return "war_room_debug" if "war_room" in stage.lower() else "testing_qa"
    return "scout_research"


async def check_circuit_breaker(
    state: PipelineState, cost_increment: float,
    role: Optional[AIRole] = None,
) -> bool:
    """Check if cost would breach role/phase limit.

    Spec: §3.6.1
    Returns True if OK to proceed, False if tripped.
    """
    if role is None:
        return True

    category = _budget_category(role, state.current_stage.value)
    limit = PHASE_BUDGET_LIMITS.get(category, 5.00)
    current = state.phase_costs.get(category, 0.0)

    if current + cost_increment > limit:
        state.circuit_breaker_triggered = True
        logger.warning(
            f"[{state.project_id}] Circuit breaker: "
            f"{category} ${current:.2f}+${cost_increment:.3f} > ${limit:.2f}"
        )
        return False
    return True


# ═══════════════════════════════════════════════════════════════════
# AI Dispatch (call_ai implementation)
# ═══════════════════════════════════════════════════════════════════


async def dispatch_ai_call(
    role: AIRole,
    prompt: str,
    state: PipelineState,
    action: str = "general",
) -> str:
    """Execute an AI call through the dispatch layer.

    Spec: §2.2, §3.6, §2.14

    Execution order:
      1. Load role contract
      2. Check MODEL_OVERRIDE
      3. Budget Governor check
      4. Enforce role boundaries
      5. Route to provider (Anthropic or Perplexity)
      6. Track cost
    """
    # 1. Load role contract
    contract = dict(ROLE_CONTRACTS.get(role, ROLE_CONTRACTS[AIRole.QUICK_FIX]))

    # 2. Check MODEL_OVERRIDE
    override_key = f"{role.value.upper()}_MODEL_OVERRIDE"
    override_model = os.getenv(override_key)
    if override_model:
        contract["model"] = override_model
        logger.info(f"MODEL_OVERRIDE: {role.value} → {override_model}")

    # 3. Budget Governor
    contract = budget_governor.check(role, state, contract)

    # 4. Role boundary enforcement
    allowed = contract.get("allowed_actions", [])
    if action not in allowed and "general" not in allowed:
        logger.warning(
            f"Role boundary: {role.value} cannot perform '{action}'. "
            f"Allowed: {allowed}. Proceeding with warning."
        )

    # 5. Route to provider
    provider = contract.get("provider", "anthropic")
    model = contract.get("model", "claude-haiku-4-5-20251001")

    if provider == "perplexity":
        response = await _call_perplexity(prompt, model, contract, state)
    else:
        response = await _call_anthropic(prompt, model, contract, state)

    # 6. Track cost
    estimated_cost = _estimate_cost(prompt, response, contract)
    category = _budget_category(role, state.current_stage.value)
    state.phase_costs[category] = (
        state.phase_costs.get(category, 0.0) + estimated_cost
    )
    state.total_cost_usd += estimated_cost

    return response


async def _call_anthropic(
    prompt: str, model: str, contract: dict, state: PipelineState,
    system_prompt: Optional[str] = None,
) -> tuple[str, int, int]:
    """Call Anthropic Claude API via AsyncAnthropic SDK.

    Spec: §2.2
    Falls back to offline stub when ANTHROPIC_API_KEY is absent.
    Streams when max_output_tokens > 8192 to prevent HTTP timeouts.

    Returns:
        (response_text, input_tokens, output_tokens)
        Real token counts from message.usage when API key present.
        Zero counts for stub responses.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key:
        stub = json.dumps({
            "_stub": True,
            "_model": model,
            "_prompt_length": len(prompt),
            "result": "Stub response from AI dispatch",
        })
        return stub, 0, 0

    import anthropic as sdk

    max_tokens = contract.get("max_output_tokens", 4096)
    temperature = contract.get("temperature", 0.3)
    client = sdk.AsyncAnthropic(api_key=api_key)

    # Build kwargs — system prompt is optional
    create_kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        create_kwargs["system"] = system_prompt

    try:
        if max_tokens > 8192:
            async with client.messages.stream(**create_kwargs) as stream:
                response = await stream.get_final_message()
        else:
            response = await client.messages.create(**create_kwargs)

        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text
                break

        # Real token counts from SDK response (§3.6 cost tracking)
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        logger.info(
            f"[{state.project_id}] {model}: "
            f"{in_tok} in / {out_tok} out tokens"
        )
        return text, in_tok, out_tok

    except sdk.AuthenticationError:
        logger.error("Anthropic auth failed — check ANTHROPIC_API_KEY")
        raise
    except sdk.RateLimitError as e:
        logger.warning(f"Anthropic rate limit: {e}")
        raise
    except sdk.APIConnectionError as e:
        logger.error(f"Anthropic connection/timeout error: {e}")
        raise
    except sdk.APIStatusError as e:
        logger.error(f"Anthropic API error {e.status_code}: {e.message}")
        raise


async def _call_perplexity(
    prompt: str, model: str, contract: dict, state: PipelineState,
) -> str:
    """Call Perplexity Sonar API (Scout).

    Spec: §3.1
    Auto-selects Sonar Pro for complex queries.
    """
    api_key = os.getenv("PERPLEXITY_API_KEY", "")

    # Auto-select Pro
    if any(t in prompt.lower() for t in SONAR_PRO_TRIGGERS):
        model = "sonar-pro"

    if not api_key:
        return json.dumps({
            "_stub": True,
            "_model": model,
            "result": "Stub Scout response",
        })

    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": contract.get("max_output_tokens", 2048),
                "web_search_options": {"search_context_size": "low"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _estimate_cost(prompt: str, response: str, contract: dict) -> float:
    """Estimate cost of an AI call.

    Uses token count approximation (4 chars ≈ 1 token).
    """
    input_tokens = len(prompt) / 4
    output_tokens = len(response) / 4
    cost_in = contract.get("cost_per_m_input", 1.0)
    cost_out = contract.get("cost_per_m_output", 1.0)
    return (input_tokens / 1e6 * cost_in) + (output_tokens / 1e6 * cost_out)