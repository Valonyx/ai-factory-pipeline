"""
AI Factory Pipeline v5.8 — Master Execution Mode Router

The Mode Router is the single source of truth for HOW to pick a
provider/option in any chain. Every chain (AI, Scout, Image, UI, Build,
Deploy) calls router.select() and the Mode Router enforces the active
mode's selection rules.

Four Master Modes:
  BASIC    — free-only, auto-cascade, auto-recover, $0 enforced
  BALANCED — smart paid for CRITICAL, free for BULK, default mode
  CUSTOM   — operator picks every provider, pauses on exhaustion
  TURBO    — max performance, ignore cost, cascade by quality

Usage:
    router = ModeRouter(mode=MasterMode.BALANCED, ...)
    provider = await router.select(candidates, context)

Spec Authority: v5.8 §Phase 1.5
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("factory.core.mode_router")


# ═══════════════════════════════════════════════════════════════════
# Master Mode Enum
# ═══════════════════════════════════════════════════════════════════

class MasterMode(str, Enum):
    """Four master execution modes controlling provider selection.

    Spec: v5.8 §Phase 1.5
    """
    BASIC    = "basic"     # Free-only, auto-cascade, $0 cost
    BALANCED = "balanced"  # Smart paid for critical, free for bulk [DEFAULT]
    CUSTOM   = "custom"    # Operator picks every provider
    TURBO    = "turbo"     # Max performance, ignore costs

    @classmethod
    def from_string(cls, s: str) -> "MasterMode":
        try:
            return cls(s.lower())
        except ValueError:
            return cls.BALANCED

    @property
    def emoji(self) -> str:
        return {
            MasterMode.BASIC:    "🆓",
            MasterMode.BALANCED: "⚖️",
            MasterMode.CUSTOM:   "🎛",
            MasterMode.TURBO:    "🚀",
        }[self]

    @property
    def label(self) -> str:
        return {
            MasterMode.BASIC:    "Basic (Free)",
            MasterMode.BALANCED: "Balanced",
            MasterMode.CUSTOM:   "Custom",
            MasterMode.TURBO:    "Turbo",
        }[self]


# ═══════════════════════════════════════════════════════════════════
# Provider Tier & Call Criticality
# ═══════════════════════════════════════════════════════════════════

class ProviderTier(str, Enum):
    """Cost tier of a provider."""
    FREE          = "free"
    PAID_CHEAP    = "paid_cheap"
    PAID_PREMIUM  = "paid_premium"


class CallCriticality(str, Enum):
    """Criticality of an individual AI call site.

    CRITICAL  — architecture decisions, legal verification, codegen core
    STANDARD  — most calls (planning, synthesis, explanation)
    BULK      — repetitive content, boilerplate, bulk authoring
    """
    CRITICAL = "critical"
    STANDARD = "standard"
    BULK     = "bulk"


# ═══════════════════════════════════════════════════════════════════
# Provider Descriptor
# ═══════════════════════════════════════════════════════════════════

class ProviderDescriptor:
    """Describes one provider option for a given chain."""

    def __init__(
        self,
        name: str,
        tier: ProviderTier,
        free_quality_rank: int = 99,   # lower = better quality among free options
        performance_rank: int = 99,    # lower = better absolute performance (all tiers)
        cost_per_1k_tokens: float = 0.0,
        model_id: Optional[str] = None,
    ):
        self.name = name
        self.tier = tier
        self.free_quality_rank = free_quality_rank
        self.performance_rank = performance_rank
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self.model_id = model_id or name

    @property
    def is_free(self) -> bool:
        return self.tier == ProviderTier.FREE

    def __repr__(self) -> str:
        return f"Provider({self.name}, {self.tier.value}, perf={self.performance_rank})"


# ═══════════════════════════════════════════════════════════════════
# Chain Context
# ═══════════════════════════════════════════════════════════════════

class ChainContext:
    """Context for a provider selection request."""

    def __init__(
        self,
        chain_name: str,
        criticality: CallCriticality = CallCriticality.STANDARD,
        stage: str = "",
        action: str = "",
        project_id: str = "",
        estimated_tokens: int = 0,
    ):
        self.chain_name = chain_name
        self.criticality = criticality
        self.stage = stage
        self.action = action
        self.project_id = project_id
        self.estimated_tokens = estimated_tokens


# ═══════════════════════════════════════════════════════════════════
# Mode Router
# ═══════════════════════════════════════════════════════════════════

class ModeRouter:
    """Single source of truth for provider selection in any chain.

    Every AI/Scout/Image/Build/Deploy chain calls router.select()
    instead of picking providers directly.

    Spec: v5.8 §Phase 1.5
    """

    # Absolute monthly safety ceiling — never bypassed by any mode
    ABSOLUTE_CEILING_USD: float = 800.0
    ABSOLUTE_CEILING_WARN_PCT: float = 0.90  # warn at 90%

    def __init__(
        self,
        mode: MasterMode,
        custom_prefs: Optional[dict] = None,
        quota_tracker=None,         # QuotaTracker instance (from quota_tracker.py)
        telegram_bridge=None,       # TelegramBridge for operator pause messages
        project_budget_usd: float = 25.0,
        monthly_cap_usd: float = 80.0,
        current_project_spend: float = 0.0,
        current_monthly_spend: float = 0.0,
    ):
        self.mode = mode
        self.custom_prefs = custom_prefs or {}
        self.quota_tracker = quota_tracker
        self.telegram_bridge = telegram_bridge
        self.project_budget_usd = project_budget_usd
        self.monthly_cap_usd = monthly_cap_usd
        self.current_project_spend = current_project_spend
        self.current_monthly_spend = current_monthly_spend

        # Upgrade poller task handle
        self._upgrade_poller: Optional[asyncio.Task] = None

    # ── Public API ──────────────────────────────────────────────────

    async def select(
        self,
        candidates: list[ProviderDescriptor],
        context: ChainContext,
    ) -> ProviderDescriptor:
        """Return the provider to use right now, per active mode rules.

        Args:
            candidates: Ordered list of available providers for this chain.
            context: Call-site context (criticality, stage, etc.).

        Returns:
            The selected ProviderDescriptor.
        """
        available = self._filter_available(candidates, context)

        if not available:
            # Last resort: return first candidate regardless
            logger.warning(
                f"[ModeRouter/{self.mode}] No available providers for "
                f"{context.chain_name} — using first candidate"
            )
            return candidates[0] if candidates else self._null_provider()

        if self.mode == MasterMode.BASIC:
            return self._select_basic(available, context)
        elif self.mode == MasterMode.BALANCED:
            return self._select_balanced(available, context)
        elif self.mode == MasterMode.CUSTOM:
            return await self._select_custom(available, context)
        elif self.mode == MasterMode.TURBO:
            return self._select_turbo(available, context)
        else:
            return self._select_balanced(available, context)

    async def on_quota_exhausted(
        self,
        exhausted: ProviderDescriptor,
        candidates: list[ProviderDescriptor],
        context: ChainContext,
    ) -> ProviderDescriptor:
        """Called when a provider hits its limit mid-run.

        Behavior per mode:
          BASIC    — auto-cascade to next free option; halt if all free exhausted
          BALANCED — auto-cascade; downgrade STANDARD/BULK to free if needed
          CUSTOM   — pause pipeline, send Telegram prompt for operator decision
          TURBO    — auto-cascade to next by performance regardless of cost
        """
        logger.warning(
            f"[ModeRouter/{self.mode}] {exhausted.name} exhausted in "
            f"{context.chain_name} at {context.stage}"
        )

        if self.quota_tracker:
            self.quota_tracker.mark_exhausted(exhausted.name)

        remaining = [p for p in candidates if p.name != exhausted.name]
        available = self._filter_available(remaining, context)

        if self.mode == MasterMode.CUSTOM:
            return await self._custom_pause_and_choose(
                exhausted, available, context
            )

        if self.mode == MasterMode.BASIC:
            free_available = [p for p in available if p.is_free]
            if not free_available:
                await self._halt_all_free_exhausted(context)
                return exhausted  # caller should handle halt
            return min(free_available, key=lambda p: p.free_quality_rank)

        if self.mode == MasterMode.TURBO:
            if available:
                return min(available, key=lambda p: p.performance_rank)
            return exhausted

        # BALANCED
        return await self.select(remaining, context)

    async def maybe_upgrade(
        self,
        current: ProviderDescriptor,
        candidates: list[ProviderDescriptor],
        context: ChainContext,
    ) -> Optional[ProviderDescriptor]:
        """Check if a previously-better provider has reset and upgrade.

        Called by the upgrade poller periodically during a run.
        Returns the new provider if an upgrade is available, else None.
        """
        if not self.quota_tracker:
            return None

        # Get providers that just reset
        reset_providers = self.quota_tracker.poll_resets()
        if not reset_providers:
            return None

        reset_names = {p for p in reset_providers}
        newly_available = [
            p for p in candidates
            if p.name in reset_names and p.name != current.name
        ]

        if not newly_available:
            return None

        if self.mode == MasterMode.BASIC:
            # Upgrade if a better free option reset
            better_free = [
                p for p in newly_available
                if p.is_free and p.free_quality_rank < current.free_quality_rank
            ]
            if better_free:
                best = min(better_free, key=lambda p: p.free_quality_rank)
                logger.info(
                    f"[ModeRouter/BASIC] Upgrading {current.name} → {best.name} "
                    f"(quota reset)"
                )
                return best

        elif self.mode == MasterMode.TURBO:
            # Upgrade if a higher-performance provider reset
            better = [
                p for p in newly_available
                if p.performance_rank < current.performance_rank
            ]
            if better:
                best = min(better, key=lambda p: p.performance_rank)
                logger.info(
                    f"[ModeRouter/TURBO] Upgrading {current.name} → {best.name} "
                    f"(provider reset)"
                )
                return best

        return None

    def start_upgrade_poller(self, candidates: list[ProviderDescriptor], context: ChainContext) -> None:
        """Start background task that polls for provider resets.

        BASIC mode: polls every 60s.
        TURBO mode: polls every 30s.
        """
        interval = 30 if self.mode == MasterMode.TURBO else 60
        if self._upgrade_poller and not self._upgrade_poller.done():
            return

        async def _poll():
            while True:
                await asyncio.sleep(interval)
                try:
                    if self.quota_tracker:
                        self.quota_tracker.poll_resets()
                except Exception as e:
                    logger.debug(f"[ModeRouter] Upgrade poller error: {e}")

        try:
            loop = asyncio.get_running_loop()
            self._upgrade_poller = loop.create_task(_poll())
        except RuntimeError:
            pass  # No event loop running

    def stop_upgrade_poller(self) -> None:
        """Cancel the upgrade poller on pipeline completion."""
        if self._upgrade_poller and not self._upgrade_poller.done():
            self._upgrade_poller.cancel()

    # ── Mode Selection Logic ─────────────────────────────────────────

    def _select_basic(
        self,
        available: list[ProviderDescriptor],
        context: ChainContext,
    ) -> ProviderDescriptor:
        """BASIC: best available free option by free_quality_rank."""
        free = [p for p in available if p.is_free]
        if free:
            return min(free, key=lambda p: p.free_quality_rank)
        # No free options available — should have been caught upstream
        logger.warning(
            f"[ModeRouter/BASIC] No free providers in {context.chain_name}"
        )
        return available[0]

    def _select_balanced(
        self,
        available: list[ProviderDescriptor],
        context: ChainContext,
    ) -> ProviderDescriptor:
        """BALANCED: paid for CRITICAL, cheapest-paid for STANDARD, free for BULK."""
        if context.criticality == CallCriticality.CRITICAL:
            # Best paid premium option
            premium = [p for p in available if p.tier == ProviderTier.PAID_PREMIUM]
            if premium:
                return min(premium, key=lambda p: p.performance_rank)
            # Fall through to cheapest paid
            paid = [p for p in available if not p.is_free]
            if paid:
                return min(paid, key=lambda p: p.cost_per_1k_tokens)

        elif context.criticality == CallCriticality.STANDARD:
            # Cheapest paid option that meets quality bar
            paid = [p for p in available if not p.is_free]
            if paid:
                return min(paid, key=lambda p: p.cost_per_1k_tokens)
            # Fall back to free
            free = [p for p in available if p.is_free]
            if free:
                return min(free, key=lambda p: p.free_quality_rank)

        elif context.criticality == CallCriticality.BULK:
            # Free first
            free = [p for p in available if p.is_free]
            if free:
                return min(free, key=lambda p: p.free_quality_rank)
            # Paid fallback
            paid = [p for p in available if not p.is_free]
            if paid:
                return min(paid, key=lambda p: p.cost_per_1k_tokens)

        # Fallback
        return available[0]

    async def _select_custom(
        self,
        available: list[ProviderDescriptor],
        context: ChainContext,
    ) -> ProviderDescriptor:
        """CUSTOM: use operator-specified preference, else default to BALANCED."""
        pref = self.custom_prefs.get(context.chain_name)
        if pref:
            for p in available:
                if p.name == pref:
                    return p
        # Preference not available — use BALANCED selection
        return self._select_balanced(available, context)

    def _select_turbo(
        self,
        available: list[ProviderDescriptor],
        context: ChainContext,
    ) -> ProviderDescriptor:
        """TURBO: highest performance regardless of cost."""
        return min(available, key=lambda p: p.performance_rank)

    # ── Availability Filter ──────────────────────────────────────────

    def _filter_available(
        self,
        candidates: list[ProviderDescriptor],
        context: ChainContext,
    ) -> list[ProviderDescriptor]:
        """Filter to providers that are currently usable.

        Checks: quota tracker availability + mode cost rules.
        """
        result = []
        for p in candidates:
            # BASIC mode: only free providers
            if self.mode == MasterMode.BASIC and not p.is_free:
                continue
            # Quota check
            if self.quota_tracker and not self.quota_tracker.is_available(p.name):
                continue
            # Budget check (skip for TURBO, checked against absolute ceiling only)
            if self.mode != MasterMode.TURBO:
                if not self._within_budget(p, context):
                    continue
            result.append(p)
        return result

    def _within_budget(self, p: ProviderDescriptor, context: ChainContext) -> bool:
        """Check if using this provider stays within budget caps."""
        estimated_cost = (
            p.cost_per_1k_tokens * context.estimated_tokens / 1000
            if context.estimated_tokens > 0
            else p.cost_per_1k_tokens * 0.5  # rough estimate
        )
        if self.current_project_spend + estimated_cost > self.project_budget_usd:
            return False
        if self.current_monthly_spend + estimated_cost > self.monthly_cap_usd:
            return False
        return True

    # ── Operator Communication ───────────────────────────────────────

    async def _halt_all_free_exhausted(self, context: ChainContext) -> None:
        """BASIC mode: halt with ETA message when all free options exhausted."""
        eta = "unknown"
        if self.quota_tracker:
            soonest = self.quota_tracker.soonest_reset()
            if soonest:
                eta = soonest.strftime("%Y-%m-%d %H:%M UTC")

        msg = (
            f"⏳ All free providers exhausted for {context.chain_name}.\n\n"
            f"Waiting for quota reset.\n"
            f"ETA: {eta}\n\n"
            f"Use /switch_mode to change execution mode and continue now."
        )
        logger.warning(f"[ModeRouter/BASIC] {msg}")
        if self.telegram_bridge:
            await self.telegram_bridge.send_message(msg)

    async def _custom_pause_and_choose(
        self,
        exhausted: ProviderDescriptor,
        available: list[ProviderDescriptor],
        context: ChainContext,
    ) -> ProviderDescriptor:
        """CUSTOM mode: pause pipeline, let operator choose alternative."""
        options_text = "\n".join([
            f"  {i+1}. {p.name} — {p.tier.value} — "
            f"~${p.cost_per_1k_tokens:.4f}/1K tokens"
            for i, p in enumerate(available)
        ])
        extra = len(available) + 1
        msg = (
            f"⏸ Provider exhausted: *{exhausted.name}* ({context.chain_name})\n\n"
            f"Remaining options:\n{options_text}\n"
            f"  {extra}. ⏳ Wait for {exhausted.name} reset\n"
            f"  {extra + 1}. ⏹ Halt project\n\n"
            f"Reply with number to continue."
        )
        logger.info(f"[ModeRouter/CUSTOM] Pausing for operator decision: {context.chain_name}")

        if self.telegram_bridge:
            choice = await self.telegram_bridge.ask_operator(msg, timeout=3600)
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(available):
                    return available[idx]
            except (ValueError, TypeError):
                pass

        # Default: use first available
        return available[0] if available else exhausted

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _null_provider() -> ProviderDescriptor:
        return ProviderDescriptor(
            name="mock",
            tier=ProviderTier.FREE,
            free_quality_rank=999,
            performance_rank=999,
        )

    def status_summary(self) -> str:
        """Return human-readable status for /mode command."""
        return (
            f"{self.mode.emoji} Mode: *{self.mode.label}*\n"
            f"Project spend: ${self.current_project_spend:.4f} / ${self.project_budget_usd:.2f}\n"
            f"Monthly spend: ${self.current_monthly_spend:.4f} / ${self.monthly_cap_usd:.2f}"
        )


# ═══════════════════════════════════════════════════════════════════
# Pre-defined Provider Catalogs (per chain)
# ═══════════════════════════════════════════════════════════════════

# AI Chain — ordered by performance_rank (1=best)
AI_PROVIDERS: list[ProviderDescriptor] = [
    # ── Tier 1: Premium paid ──────────────────────────────────────────
    ProviderDescriptor("anthropic",         ProviderTier.PAID_PREMIUM,
                       free_quality_rank=99, performance_rank=1,
                       cost_per_1k_tokens=0.015, model_id="claude-opus-4-6"),
    # ── Tier 2: Ultra-premium NIM (reasoning + scale) ─────────────────
    ProviderDescriptor("kimi_k2",           ProviderTier.PAID_CHEAP,
                       free_quality_rank=99, performance_rank=2,
                       cost_per_1k_tokens=0.002, model_id="moonshotai/kimi-k2.5"),
    ProviderDescriptor("nvidia_nim_405b",   ProviderTier.PAID_CHEAP,
                       free_quality_rank=99, performance_rank=3,
                       cost_per_1k_tokens=0.005, model_id="meta/llama-3.1-405b-instruct"),
    # ── Tier 3: Free high-quality ────────────────────────────────────
    ProviderDescriptor("gemini",            ProviderTier.FREE,
                       free_quality_rank=1,  performance_rank=4,
                       cost_per_1k_tokens=0.0001, model_id="gemini-2.5-pro"),
    ProviderDescriptor("together",          ProviderTier.PAID_CHEAP,
                       free_quality_rank=99, performance_rank=5,
                       cost_per_1k_tokens=0.0009),
    ProviderDescriptor("mistral",           ProviderTier.PAID_CHEAP,
                       free_quality_rank=99, performance_rank=6,
                       cost_per_1k_tokens=0.0007),
    # ── Tier 4: Free mid-quality (70B range) ─────────────────────────
    ProviderDescriptor("groq",              ProviderTier.FREE,
                       free_quality_rank=2,  performance_rank=7,
                       cost_per_1k_tokens=0.0, model_id="llama-3.3-70b-versatile"),
    ProviderDescriptor("nvidia_nim_mixtral", ProviderTier.FREE,
                       free_quality_rank=3,  performance_rank=8,
                       cost_per_1k_tokens=0.0, model_id="mistralai/mixtral-8x22b-instruct-v0.1"),
    ProviderDescriptor("nvidia_nim_gemma27b", ProviderTier.FREE,
                       free_quality_rank=4,  performance_rank=9,
                       cost_per_1k_tokens=0.0, model_id="google/gemma-3-27b-it"),
    ProviderDescriptor("nvidia_nim",        ProviderTier.FREE,
                       free_quality_rank=5,  performance_rank=10,
                       cost_per_1k_tokens=0.0001, model_id="meta/llama-3.3-70b-instruct"),
    ProviderDescriptor("sambanova",         ProviderTier.FREE,
                       free_quality_rank=6,  performance_rank=11,
                       cost_per_1k_tokens=0.0, model_id="Meta-Llama-3.3-70B-Instruct"),
    # ── Tier 5: Free standard ────────────────────────────────────────
    ProviderDescriptor("openrouter",        ProviderTier.FREE,
                       free_quality_rank=7,  performance_rank=12,
                       cost_per_1k_tokens=0.0, model_id="meta-llama/llama-3.1-8b-instruct:free"),
    ProviderDescriptor("cerebras",          ProviderTier.FREE,
                       free_quality_rank=8,  performance_rank=13,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("cloudflare",        ProviderTier.FREE,
                       free_quality_rank=9,  performance_rank=14,
                       cost_per_1k_tokens=0.0, model_id="llama-3.1-8b-instruct"),
    ProviderDescriptor("github_models",     ProviderTier.FREE,
                       free_quality_rank=10, performance_rank=15,
                       cost_per_1k_tokens=0.0, model_id="meta-llama-3.1-70b-instruct"),
    # ── Tier 6: Free fast/lightweight ────────────────────────────────
    ProviderDescriptor("nvidia_nim_fast",   ProviderTier.FREE,
                       free_quality_rank=11, performance_rank=16,
                       cost_per_1k_tokens=0.0, model_id="meta/llama-3.1-8b-instruct"),
    ProviderDescriptor("mock",              ProviderTier.FREE,
                       free_quality_rank=99, performance_rank=99,
                       cost_per_1k_tokens=0.0),
]

# Scout Chain — ordered by performance_rank (1=best)
SCOUT_PROVIDERS: list[ProviderDescriptor] = [
    ProviderDescriptor("perplexity",  ProviderTier.PAID_CHEAP,
                       free_quality_rank=99, performance_rank=1,
                       cost_per_1k_tokens=0.005),
    ProviderDescriptor("brave",       ProviderTier.PAID_CHEAP,
                       free_quality_rank=99, performance_rank=2,
                       cost_per_1k_tokens=0.003),
    ProviderDescriptor("tavily",      ProviderTier.FREE,
                       free_quality_rank=1,  performance_rank=3,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("exa",         ProviderTier.FREE,
                       free_quality_rank=2,  performance_rank=4,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("searxng",     ProviderTier.FREE,
                       free_quality_rank=3,  performance_rank=5,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("duckduckgo",  ProviderTier.FREE,
                       free_quality_rank=4,  performance_rank=6,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("wikipedia",   ProviderTier.FREE,
                       free_quality_rank=5,  performance_rank=7,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("hackernews",  ProviderTier.FREE,
                       free_quality_rank=6,  performance_rank=8,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("reddit",      ProviderTier.FREE,
                       free_quality_rank=7,  performance_rank=9,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("stackoverflow", ProviderTier.FREE,
                       free_quality_rank=8,  performance_rank=10,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("github_search", ProviderTier.FREE,
                       free_quality_rank=9,  performance_rank=11,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("ai_scout",    ProviderTier.FREE,
                       free_quality_rank=10, performance_rank=12,
                       cost_per_1k_tokens=0.0),
]

# Image Chain
IMAGE_PROVIDERS: list[ProviderDescriptor] = [
    ProviderDescriptor("pollinations", ProviderTier.FREE,
                       free_quality_rank=1, performance_rank=2,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("huggingface",  ProviderTier.FREE,
                       free_quality_rank=2, performance_rank=3,
                       cost_per_1k_tokens=0.0),
    ProviderDescriptor("together",     ProviderTier.PAID_CHEAP,
                       free_quality_rank=99, performance_rank=1,
                       cost_per_1k_tokens=0.004),
]

# Catalog lookup
PROVIDER_CATALOGS: dict[str, list[ProviderDescriptor]] = {
    "ai":     AI_PROVIDERS,
    "scout":  SCOUT_PROVIDERS,
    "image":  IMAGE_PROVIDERS,
}


# ═══════════════════════════════════════════════════════════════════
# Telegram UX — Mode Selection Message
# ═══════════════════════════════════════════════════════════════════

def mode_selection_message(app_name: str) -> str:
    """Return the Telegram mode selection prompt sent in S0."""
    return (
        f"⚙️ Choose execution mode for *{app_name}*:\n\n"
        f"1. 🆓 *Basic* — Free providers only, auto-cascade, $0 cost\n"
        f"2. ⚖️ *Balanced* — Smart mix, paid for critical work, ~$5–25/project "
        f"\\[DEFAULT]\n"
        f"3. 🎛 *Custom* — You pick every provider, manual fallback decisions\n"
        f"4. 🚀 *Turbo* — Max performance, ignore costs, premium everything\n\n"
        f"Reply with a number (or press Enter for Balanced)."
    )


def parse_mode_selection(user_input: str) -> MasterMode:
    """Parse operator's mode choice from Telegram message."""
    s = user_input.strip()
    if s in ("1", "basic"):
        return MasterMode.BASIC
    elif s in ("2", "balanced", ""):
        return MasterMode.BALANCED
    elif s in ("3", "custom"):
        return MasterMode.CUSTOM
    elif s in ("4", "turbo"):
        return MasterMode.TURBO
    return MasterMode.BALANCED
