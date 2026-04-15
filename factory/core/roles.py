"""
AI Factory Pipeline v5.8 — AI Role Enforcement & Dispatcher

Implements:
  - §2.2.1 Role Contracts (Eyes vs. Hands Doctrine)
  - §2.2.2 Unified AI Dispatcher (call_ai)
  - §2.2.3 Research Degradation Policy (No Ungrounded Facts) [C5]
  - §2.2.4 War Room Escalation (war_room_escalate)
  - §2.14  Budget Governor integration (pre-dispatch check)
  - §3.6   Circuit Breaker integration (post-dispatch cost tracking)

Spec Authority: v5.8 §2.2, §2.14, §3.6
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from factory.core.state import (
    AIRole,
    BudgetExceeded,
    BudgetExhaustedError,
    BudgetIntakeBlockedError,
    NotificationType,
    PHASE_BUDGET_LIMITS,
    PipelineState,
    RoleContract,
    RoleViolationError,
    ROLE_CONTRACTS,
    MODEL_CONFIG,
    MODEL_OVERRIDES,
    VALID_ANTHROPIC_MODELS,
    WarRoomLevel,
    Stage,
    BUDGET_GUARDRAILS,
    SCOUT_MAX_CONTEXT_TIER,
    CONTEXT_TIER_LIMITS,
    RESEARCH_DEGRADATION_POLICY,
    UserSpaceViolation,
)

logger = logging.getLogger("factory.core.roles")


# ═══════════════════════════════════════════════════════════════════
# Budget Governor Placeholder
# Full implementation in intelligence/circuit_breaker.py (Part 9).
# This stub allows call_ai() to compile without the full governor.
# ═══════════════════════════════════════════════════════════════════


class _StubBudgetGovernor:
    """Stub Budget Governor — returns contract unchanged.

    Replaced by real BudgetGovernor in intelligence/circuit_breaker.py.
    """
    async def check(
        self, role: AIRole, state: PipelineState, contract: RoleContract,
        notify_fn=None,
    ) -> RoleContract:
        return contract


budget_governor: Any = _StubBudgetGovernor()


def set_budget_governor(governor: Any) -> None:
    """Replace stub governor with real implementation at startup.

    Called from factory/main.py after intelligence module loads.
    """
    global budget_governor
    budget_governor = governor


# ═══════════════════════════════════════════════════════════════════
# §2.2.2 Unified AI Dispatcher
# ═══════════════════════════════════════════════════════════════════


async def call_ai(
    role: AIRole,
    prompt: str,
    state: PipelineState,
    action: str = "general",
) -> str:
    """Unified AI call dispatcher with role enforcement and cost tracking.

    Spec: §2.2.2
    Every AI call in the pipeline goes through this function.

    Precedence chain (ADR-043/044):
      operator MODEL_OVERRIDE > Budget Governor > MODEL_CONFIG default

    Args:
        role: Which AI role to use (SCOUT, STRATEGIST, ENGINEER, QUICK_FIX).
        prompt: The prompt to send.
        state: Current pipeline state (mutated for cost tracking).
        action: What kind of action (general, write_code, plan_architecture,
                decide_legal). Enforced against role contract.

    Returns:
        str: The AI model's response text.

    Raises:
        RoleViolationError: If role attempts unauthorized action.
        BudgetExceeded: If circuit breaker fires.
        BudgetExhaustedError: If BLACK tier reached.
        BudgetIntakeBlockedError: If RED tier blocks new intake.
    """
    contract = ROLE_CONTRACTS[role]

    # ── Step 1: Apply operator MODEL_OVERRIDE (highest precedence) ──
    if role != AIRole.SCOUT:
        role_key = role.value
        override_model = MODEL_OVERRIDES.get(role_key)
        if override_model:
            if override_model in VALID_ANTHROPIC_MODELS:
                logger.warning(
                    f"Model override active: {role.value} → {override_model} "
                    f"(default was {contract.model})"
                )
                contract = RoleContract(
                    role=contract.role,
                    model=override_model,
                    can_read_web=contract.can_read_web,
                    can_write_code=contract.can_write_code,
                    can_write_files=contract.can_write_files,
                    can_plan_architecture=contract.can_plan_architecture,
                    can_decide_legal=contract.can_decide_legal,
                    can_manage_war_room=contract.can_manage_war_room,
                    max_output_tokens=contract.max_output_tokens,
                )
            else:
                logger.error(
                    f"Invalid model override '{override_model}' for {role.value}. "
                    f"Valid: {VALID_ANTHROPIC_MODELS}. Using default: {contract.model}"
                )

    # ── Step 2: Budget Governor check (§2.14) ──
    try:
        from factory.telegram.notifications import send_telegram_message as _tg_send
        contract = await budget_governor.check(
            role, state, contract, notify_fn=_tg_send,
        )
    except BudgetIntakeBlockedError:
        logger.warning(f"RED tier: intake blocked for {state.project_id}")
        raise
    except BudgetExhaustedError:
        logger.critical(f"BLACK tier: budget exhausted")
        raise

    # ── Step 3: Enforce role boundaries ──
    if action == "write_code" and not contract.can_write_code:
        raise RoleViolationError(
            f"{role.value} (model={contract.model}) attempted to write code. "
            f"Only ENGINEER and QUICK_FIX roles can write code."
        )
    if action == "plan_architecture" and not contract.can_plan_architecture:
        raise RoleViolationError(
            f"{role.value} attempted to plan architecture. "
            f"Only STRATEGIST can plan architecture."
        )
    if action == "decide_legal" and not contract.can_decide_legal:
        raise RoleViolationError(
            f"{role.value} attempted legal decision. "
            f"Only STRATEGIST can make legal decisions."
        )

    # ── Step 4: Inject unified context so any provider has full project memory ──
    from factory.core.context_bridge import inject_context
    prompt = inject_context(prompt, state)

    # ── Step 5: Route to provider ──
    if role == AIRole.SCOUT:
        response, cost = await _call_perplexity_safe(prompt, contract, state)
    else:
        response, cost = await _call_anthropic(prompt, contract, state, action)

    # ── Step 6: Track cost against circuit breaker (§3.6) ──
    phase = state.current_stage.value
    state.phase_costs[phase] = state.phase_costs.get(phase, 0.0) + cost
    state.total_cost_usd += cost

    # Per-project cap check
    if state.total_cost_usd > BUDGET_GUARDRAILS["per_project_cap_usd"]:
        state.circuit_breaker_triggered = True
        logger.warning(
            f"[{state.project_id}] Per-project cap exceeded: "
            f"${state.total_cost_usd:.2f} > "
            f"${BUDGET_GUARDRAILS['per_project_cap_usd']:.2f}"
        )

    # Per-role/phase limit check
    role_key = _phase_budget_key(role, state)
    role_limit = PHASE_BUDGET_LIMITS.get(role_key, 2.00)
    if state.phase_costs.get(phase, 0.0) > role_limit:
        state.circuit_breaker_triggered = True
        logger.warning(
            f"[{state.project_id}] Phase budget exceeded for {role_key}: "
            f"${state.phase_costs[phase]:.2f} > ${role_limit:.2f}"
        )

    # ── Step 7: Persist Strategist decisions to Mother Memory ──
    # Key planning outputs are stored so any future provider has institutional memory.
    # Skip in mock mode to prevent background tasks from connecting to real backends.
    if role == AIRole.STRATEGIST and len(response) > 50 and \
            os.getenv("AI_PROVIDER", "").lower() != "mock":
        try:
            from factory.memory.mother_memory import store_pipeline_decision
            import asyncio
            asyncio.create_task(store_pipeline_decision(
                project_id=state.project_id,
                stage=phase,
                decision_type=f"strategist_{action}",
                content=response[:1500],
                operator_id=state.operator_id or "",
            ))
        except Exception:
            pass  # never block pipeline over memory write

    return response


def _phase_budget_key(role: AIRole, state: PipelineState) -> str:
    """Map (role, stage) to the PHASE_BUDGET_LIMITS key.

    Spec: §3.6 — per-role phase limits
    """
    mapping = {
        AIRole.SCOUT:      "scout_research",
        AIRole.STRATEGIST: "strategist_planning",
        AIRole.ENGINEER:   "codegen_engineer",
        AIRole.QUICK_FIX:  "war_room_debug",
    }
    return mapping.get(role, "scout_research")


# ═══════════════════════════════════════════════════════════════════
# Provider Calls
# ═══════════════════════════════════════════════════════════════════

# Cost rates per model: (input_$/M, output_$/M)
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-opus-4-6":            (5.00, 25.00),
    "claude-opus-4-5-20250929":   (3.00, 15.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "claude-sonnet-4-20250514":   (3.00, 15.00),
    "claude-haiku-4-5-20251001":  (0.80,  4.00),
}


async def _call_anthropic(
    prompt: str,
    contract: "RoleContract",
    state: Optional["PipelineState"] = None,
    action: str = "general",
) -> tuple[str, float]:
    """Call AI provider using ModeRouter + cascading provider chain.

    Spec: §2.2.2, v5.8 §Phase1.5
    Provider selection is driven by the active MasterMode via ModeRouter:
      BASIC    — free providers only (gemini → groq → openrouter → cerebras)
      BALANCED — paid for CRITICAL calls, cheapest paid for STANDARD, free for BULK
      CUSTOM   — operator-specified provider preference, balanced fallback
      TURBO    — highest-performance provider (anthropic opus first); upgrades
                 all anthropic calls to claude-opus-4-6

    QuotaTracker (v5.8) records every call for monthly quota enforcement.
    Old ProviderChain kept in sync for backwards-compatibility with ScoutOrchestrator.
    """
    from factory.integrations.provider_chain import (
        ai_chain, is_quota_error, is_auth_error, parse_retry_delay,
    )
    from factory.core.mode_router import (
        MasterMode, AI_PROVIDERS, ChainContext, CallCriticality, ModeRouter,
    )
    from factory.core.quota_tracker import get_quota_tracker

    # CI / test mock shortcut — preserve existing test infrastructure
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return (f"[MOCK:{contract.role.value}] {prompt[:80]}", 0.0001)

    # ── Resolve active master mode + context from pipeline state ──
    _CRITICALITY_MAP: dict[str, CallCriticality] = {
        "write_code":        CallCriticality.CRITICAL,
        "plan_architecture": CallCriticality.CRITICAL,
        "decide_legal":      CallCriticality.CRITICAL,
        "general":           CallCriticality.STANDARD,
    }

    master_mode = MasterMode.BALANCED
    project_spend = 0.0
    project_id = ""
    stage_name = ""
    if state is not None:
        master_mode = getattr(state, "master_mode", MasterMode.BALANCED)
        project_spend = getattr(state, "total_cost_usd", 0.0)
        project_id = getattr(state, "project_id", "")
        stage_name = (
            state.current_stage.value
            if getattr(state, "current_stage", None) else ""
        )

    qt = get_quota_tracker()
    router = ModeRouter(
        mode=master_mode,
        quota_tracker=qt,
        current_project_spend=project_spend,
        current_monthly_spend=project_spend,
    )
    ctx = ChainContext(
        chain_name="ai",
        criticality=_CRITICALITY_MAP.get(action, CallCriticality.STANDARD),
        stage=stage_name,
        action=action,
        project_id=project_id,
        estimated_tokens=max(len(prompt) // 4, 100),
    )

    # ── ModeRouter-driven provider loop ──
    current_provider = await router.select(AI_PROVIDERS, ctx)
    tried: set[str] = set()

    while current_provider and current_provider.name not in tried:
        tried.add(current_provider.name)
        provider_name = current_provider.name

        # TURBO mode: upgrade anthropic calls to opus for maximum output quality
        effective_contract = contract
        if master_mode == MasterMode.TURBO and provider_name == "anthropic":
            try:
                effective_contract = RoleContract(
                    role=contract.role,
                    model="claude-opus-4-6",
                    can_read_web=contract.can_read_web,
                    can_write_code=contract.can_write_code,
                    can_write_files=contract.can_write_files,
                    can_plan_architecture=contract.can_plan_architecture,
                    can_decide_legal=contract.can_decide_legal,
                    can_manage_war_room=contract.can_manage_war_room,
                    max_output_tokens=contract.max_output_tokens,
                )
            except Exception:
                pass  # keep original contract on any error

        try:
            result = await _call_single_ai_provider(
                provider_name, prompt, effective_contract
            )
            text, cost = result

            # Record usage in v5.8 QuotaTracker (non-fatal, async)
            tokens_est = max(len(prompt) // 4 + len(text) // 4, 10)
            try:
                await qt.record_usage(
                    provider_name, tokens=tokens_est, cost_usd=cost
                )
            except Exception:
                pass  # quota recording never blocks the pipeline

            # Keep old ProviderChain in sync for ScoutOrchestrator compatibility
            ai_chain.mark_success(provider_name)
            if len(tried) > 1:
                logger.info(
                    f"[ModeRouter/{master_mode.value}] AI call succeeded on: "
                    f"{provider_name} (after {len(tried) - 1} fallback(s))"
                )
            return result

        except Exception as e:
            err = str(e)
            if is_quota_error(err):
                reset_in = parse_retry_delay(err)
                ai_chain.mark_quota_exhausted(provider_name, reset_in)
                logger.warning(
                    f"[ModeRouter/{master_mode.value}] {provider_name} quota "
                    f"exhausted — requesting next provider from router"
                )
                next_p = await router.on_quota_exhausted(
                    current_provider, AI_PROVIDERS, ctx
                )
                if next_p.name == provider_name:
                    # Router signalled halt (BASIC: all free exhausted)
                    break
                current_provider = next_p
            elif is_auth_error(err):
                ai_chain.mark_error(provider_name, f"auth: {err[:80]}")
                logger.error(
                    f"[ModeRouter] {provider_name} auth failed — trying next"
                )
                remaining = [p for p in AI_PROVIDERS if p.name not in tried]
                if not remaining:
                    break
                current_provider = await router.select(remaining, ctx)
            else:
                ai_chain.mark_error(provider_name, err[:80])
                logger.warning(
                    f"[ModeRouter] {provider_name} error: {err[:80]} — trying next"
                )
                remaining = [p for p in AI_PROVIDERS if p.name not in tried]
                if not remaining:
                    break
                current_provider = await router.select(remaining, ctx)

    # All providers exhausted
    mode_hint = (
        " Use /switch_mode to change execution mode."
        if master_mode == MasterMode.BASIC else ""
    )
    logger.error(
        f"[ModeRouter/{master_mode.value}] All AI providers exhausted.{mode_hint}"
    )
    return (f"[all-providers-exhausted] {prompt[:80]}", 0.0)


async def _call_single_ai_provider(
    provider: str,
    prompt: str,
    contract: "RoleContract",
) -> tuple[str, float]:
    """Dispatch to a specific AI provider implementation."""
    if provider == "anthropic":
        return await _call_anthropic_direct(prompt, contract)
    if provider == "gemini":
        from factory.integrations.gemini import call_gemini
        return await call_gemini(prompt, contract)
    if provider == "groq":
        from factory.integrations.groq_provider import call_groq
        return await call_groq(prompt, contract)
    if provider == "openrouter":
        from factory.integrations.openrouter_provider import call_openrouter
        return await call_openrouter(prompt, contract)
    if provider == "cerebras":
        from factory.integrations.cerebras_provider import call_cerebras
        return await call_cerebras(prompt, contract)
    if provider == "together":
        from factory.integrations.together_provider import call_together
        return await call_together(prompt, contract)
    if provider == "mistral":
        from factory.integrations.mistral_provider import call_mistral
        return await call_mistral(prompt, contract)
    if provider == "mock":
        return (f"[MOCK:{contract.role.value}] {prompt[:80]}", 0.0001)
    raise ValueError(f"Unknown AI provider: {provider}")


async def _call_anthropic_direct(
    prompt: str, contract: "RoleContract",
) -> tuple[str, float]:
    """Direct Anthropic API call (no fallback logic here)."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    import anthropic as sdk
    max_tokens = contract.max_output_tokens
    client = sdk.AsyncAnthropic(api_key=api_key)

    if max_tokens > 8192:
        async with client.messages.stream(
            model=contract.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = await stream.get_final_message()
    else:
        response = await client.messages.create(
            model=contract.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

    text = next((b.text for b in response.content if b.type == "text"), "")
    cost_in, cost_out = _MODEL_COSTS.get(contract.model, (3.00, 15.00))
    cost = (
        response.usage.input_tokens / 1_000_000 * cost_in
        + response.usage.output_tokens / 1_000_000 * cost_out
    )
    return text, cost


async def _call_perplexity_safe(
    prompt: str, contract: RoleContract, state: PipelineState,
) -> tuple[str, float]:
    """Scout research via the ScoutOrchestrator.

    Spec: §2.2.3 [C5], §3.1, ADR-049, FIX-19

    The ScoutOrchestrator handles everything:
      • Query classification (domain, stakes, freshness, KSA flag)
      • Domain-optimal provider routing (not a fixed waterfall)
      • Parallel fusion for high-stakes queries (2 providers + AI synthesis)
      • Shared Mother Memory cache (all providers, 4h TTL)
      • Exa grounding for legal/compliance/security queries
      • Per-provider confidence calibration
      • Telegram alert when confidence is low on a high-stakes result

    Dev note (NB3-DEV-004): Orchestrator added 2026-04 replacing manual chain loop.
    """
    if os.getenv("SCOUT_PROVIDER", "").lower() == "mock":
        return (f"[MOCK:scout] {prompt[:80]}", 0.0001)

    from factory.integrations.scout_orchestrator import get_scout_orchestrator
    return await get_scout_orchestrator().research(prompt, state, contract)


async def _call_single_scout_provider(
    provider: str,
    prompt: str,
    contract: "RoleContract",
    state: "PipelineState",
    domain: str = "general",
) -> tuple[str, float]:
    """Dispatch to a specific Scout provider implementation."""
    if provider == "perplexity":
        from factory.integrations.perplexity import call_perplexity_safe
        return await call_perplexity_safe(
            prompt=prompt, contract=contract, state=state, tier=SCOUT_MAX_CONTEXT_TIER,
        )
    if provider == "tavily":
        from factory.integrations.tavily_scout import call_tavily_scout
        return await call_tavily_scout(prompt, contract, state)
    if provider == "brave":
        from factory.integrations.brave_scout import call_brave
        return await call_brave(prompt, contract, state)
    if provider == "duckduckgo":
        from factory.integrations.duckduckgo_search import call_duckduckgo_search
        return await call_duckduckgo_search(prompt, contract, state)
    if provider == "exa":
        from factory.integrations.exa_scout import call_exa_scout
        return await call_exa_scout(prompt, contract, state)
    if provider == "wikipedia":
        from factory.integrations.wikipedia_scout import call_wikipedia_scout
        return await call_wikipedia_scout(prompt, contract, state)
    if provider == "hackernews":
        from factory.integrations.hackernews_scout import call_hackernews_scout
        return await call_hackernews_scout(prompt, contract, state)
    if provider == "searxng":
        from factory.integrations.searxng_scout import call_searxng
        return await call_searxng(prompt, contract, state, domain=domain)
    if provider == "reddit":
        from factory.integrations.reddit_scout import call_reddit
        return await call_reddit(prompt, contract, state, domain=domain)
    if provider == "stackoverflow":
        from factory.integrations.stackoverflow_scout import call_stackoverflow
        return await call_stackoverflow(prompt, contract, state, domain=domain)
    if provider == "github_search":
        from factory.integrations.github_search_scout import call_github_search
        return await call_github_search(prompt, contract, state, domain=domain)
    if provider == "ai_scout":
        from factory.integrations.ai_scout import call_ai_scout
        return await call_ai_scout(prompt, contract, state)
    raise ValueError(f"Unknown Scout provider: {provider}")


# ═══════════════════════════════════════════════════════════════════
# §2.2.4 War Room Escalation
# ═══════════════════════════════════════════════════════════════════


async def war_room_escalate(
    state: PipelineState,
    error: str,
    error_context: dict,
    current_level: WarRoomLevel = WarRoomLevel.L1_QUICK_FIX,
) -> dict:
    """War Room escalation ladder: L1 → L2 → L3.

    Spec: §2.2.4
    Each level is tried in order. Returns resolution dict.

    Args:
        state: Pipeline state.
        error: Error message.
        error_context: Dict with file_content, files, test_cmd, etc.
        current_level: Starting escalation level.

    Returns:
        dict: {resolved: bool, level: int, fix_applied: str}
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Level 1: Quick Fix (Haiku) ──
    if current_level <= WarRoomLevel.L1_QUICK_FIX:
        try:
            fix = await call_ai(
                role=AIRole.QUICK_FIX,
                prompt=(
                    f"Fix this error with minimal changes.\n"
                    f"Error: {error}\n\n"
                    f"Context:\n{error_context.get('file_content', '')[:4000]}"
                ),
                state=state,
                action="write_code",
            )
            success = await _apply_and_test_fix(fix, error_context)
            if success:
                state.war_room_history.append({
                    "level": 1, "error": error[:300],
                    "resolved": True, "timestamp": now,
                })
                return {"resolved": True, "level": 1, "fix_applied": fix[:200]}
        except (BudgetExceeded, RoleViolationError) as e:
            logger.warning(f"L1 skipped: {e}")

    # ── Level 2: Researched Fix (Scout → Engineer) ──
    if current_level <= WarRoomLevel.L2_RESEARCHED:
        try:
            research = await call_ai(
                role=AIRole.SCOUT,
                prompt=(
                    f"Find the solution for this error in official documentation.\n"
                    f"Error: {error}\n"
                    f"Stack: {state.selected_stack}\n"
                    f"Return: exact fix steps, relevant docs URLs, known issues."
                ),
                state=state,
                action="general",
            )
            fix = await call_ai(
                role=AIRole.ENGINEER,
                prompt=(
                    f"Apply this researched fix.\n\n"
                    f"Error: {error}\n"
                    f"Research findings:\n{research}\n\n"
                    f"File content:\n{error_context.get('file_content', '')[:8000]}\n\n"
                    f"Return the corrected file content."
                ),
                state=state,
                action="write_code",
            )
            success = await _apply_and_test_fix(fix, error_context)
            if success:
                state.war_room_history.append({
                    "level": 2, "error": error[:300],
                    "research": research[:500],
                    "resolved": True, "timestamp": now,
                })
                return {"resolved": True, "level": 2, "fix_applied": fix[:200]}
        except (BudgetExceeded, RoleViolationError) as e:
            logger.warning(f"L2 skipped: {e}")

    # ── Level 3: War Room (Opus orchestrates) ──
    state.war_room_active = True
    try:
        war_room_plan_str = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=(
                f"WAR ROOM ACTIVATED.\n\n"
                f"Error that survived L1 and L2: {error}\n\n"
                f"Stack: {state.selected_stack}\n"
                f"Metadata: {state.project_metadata}\n"
                f"Files involved: {list(error_context.get('files', {}).keys())}\n\n"
                f"Instructions:\n"
                f"1. Map the dependency tree of the failing component.\n"
                f"2. Identify the root cause (not the symptom).\n"
                f"3. Order specific CLI cleanup commands if needed.\n"
                f"4. Produce a file-by-file rewrite plan.\n\n"
                f"Return JSON:\n"
                f'{{"root_cause": "...", "cleanup_commands": [...], '
                f'"rewrite_plan": [{{"file": "...", "issue": "...", "fix": "..."}}]}}'
            ),
            state=state,
            action="plan_architecture",
        )

        try:
            plan = json.loads(war_room_plan_str)
        except json.JSONDecodeError:
            plan = {"root_cause": "parse_error", "cleanup_commands": [], "rewrite_plan": []}

        # Execute cleanup commands (user-space enforced)
        from factory.core.user_space import enforce_user_space
        for cmd in plan.get("cleanup_commands", []):
            try:
                validated_cmd = enforce_user_space(cmd)
                logger.info(f"[War Room] Cleanup: {validated_cmd}")
                # Actual execution deferred to execution.py
            except UserSpaceViolation as e:
                logger.warning(f"[War Room] Blocked cleanup command: {e}")

        # Execute file-by-file rewrites
        for rewrite in plan.get("rewrite_plan", []):
            fix = await call_ai(
                role=AIRole.ENGINEER,
                prompt=(
                    f"Rewrite per War Room plan.\n\n"
                    f"File: {rewrite.get('file', '?')}\n"
                    f"Issue: {rewrite.get('issue', '?')}\n"
                    f"Required fix: {rewrite.get('fix', '?')}\n\n"
                    f"Current content:\n"
                    f"{error_context.get('files', {}).get(rewrite.get('file', ''), 'N/A')[:8000]}"
                ),
                state=state,
                action="write_code",
            )
            logger.info(f"[War Room] Rewrote: {rewrite.get('file', '?')}")

        success = await _run_tests(error_context)

    except Exception as e:
        logger.error(f"War Room L3 failed: {e}")
        success = False
        plan = {"root_cause": str(e)}

    state.war_room_active = False
    state.war_room_history.append({
        "level": 3, "error": error[:300], "plan": plan,
        "resolved": success, "timestamp": now,
    })
    return {"resolved": success, "level": 3, "plan": plan}


# ═══════════════════════════════════════════════════════════════════
# Stub helpers (replaced by real implementations in later parts)
# ═══════════════════════════════════════════════════════════════════


async def _apply_and_test_fix(fix: str, error_context: dict) -> bool:
    """Apply fix and run tests. Stub for P0 — real in pipeline/war_room.py.

    Spec: §8.10 Contract 3 (apply_and_test_fix)
    """
    logger.info("[MOCK] apply_and_test_fix — returning True for dry-run")
    return True


async def _run_tests(error_context: dict) -> bool:
    """Run test suite. Stub for P0.

    Spec: §4.6
    """
    logger.info("[MOCK] run_tests — returning True for dry-run")
    return True