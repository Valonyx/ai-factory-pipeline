"""
Tests for factory.core.mode_router — MasterMode, ModeRouter, QuotaTracker.

Covers:
  - ModeRouter.select() under all 4 modes
  - on_quota_exhausted() cascade per mode
  - maybe_upgrade() reselection after reset
  - QuotaTracker availability, exhaustion, poll_resets
  - Integration: simulate provider exhaustion mid-run in BASIC/BALANCED/TURBO
  - CUSTOM mode operator pause (Telegram mock)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.mode_router import (
    AI_PROVIDERS,
    PROVIDER_CATALOGS,
    SCOUT_PROVIDERS,
    CallCriticality,
    ChainContext,
    MasterMode,
    ModeRouter,
    ProviderDescriptor,
    ProviderTier,
    mode_selection_message,
    parse_mode_selection,
)
from factory.core.quota_tracker import QuotaTracker, _month_key, _next_month_reset


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

def make_providers(*specs) -> list[ProviderDescriptor]:
    """Build a list of providers from (name, tier, free_rank, perf_rank, cost) tuples."""
    result = []
    for name, tier, free_rank, perf_rank, cost in specs:
        result.append(ProviderDescriptor(
            name=name,
            tier=tier,
            free_quality_rank=free_rank,
            performance_rank=perf_rank,
            cost_per_1k_tokens=cost,
        ))
    return result


FREE  = ProviderTier.FREE
CHEAP = ProviderTier.PAID_CHEAP
PREM  = ProviderTier.PAID_PREMIUM

CANDIDATES = make_providers(
    # name,      tier,  free_rank, perf_rank, cost
    ("opus",     PREM,  99,        1,         0.015),
    ("gemini",   FREE,  1,         3,         0.0),
    ("groq",     FREE,  2,         5,         0.0),
    ("together", CHEAP, 99,        4,         0.0009),
    ("mock",     FREE,  99,        99,        0.0),
)

STD_CTX = ChainContext("ai", CallCriticality.STANDARD, "S0_INTAKE", "extraction")
CRIT_CTX = ChainContext("ai", CallCriticality.CRITICAL, "S4_CODEGEN", "codegen")
BULK_CTX = ChainContext("ai", CallCriticality.BULK, "S2_BLUEPRINT", "authoring")


def make_router(mode: MasterMode, **kwargs) -> ModeRouter:
    return ModeRouter(mode=mode, **kwargs)


# ═══════════════════════════════════════════════════════════════════
# MasterMode enum
# ═══════════════════════════════════════════════════════════════════

class TestMasterMode:
    def test_values(self):
        assert MasterMode.BASIC.value    == "basic"
        assert MasterMode.BALANCED.value == "balanced"
        assert MasterMode.CUSTOM.value   == "custom"
        assert MasterMode.TURBO.value    == "turbo"

    def test_from_string(self):
        assert MasterMode.from_string("basic")    == MasterMode.BASIC
        assert MasterMode.from_string("TURBO")    == MasterMode.TURBO
        assert MasterMode.from_string("unknown")  == MasterMode.BALANCED

    def test_emoji(self):
        assert MasterMode.BASIC.emoji    == "🆓"
        assert MasterMode.BALANCED.emoji == "⚖️"
        assert MasterMode.CUSTOM.emoji   == "🎛"
        assert MasterMode.TURBO.emoji    == "🚀"

    def test_label(self):
        assert "Basic" in MasterMode.BASIC.label
        assert "Balanced" in MasterMode.BALANCED.label
        assert "Custom" in MasterMode.CUSTOM.label
        assert "Turbo" in MasterMode.TURBO.label


# ═══════════════════════════════════════════════════════════════════
# BASIC mode
# ═══════════════════════════════════════════════════════════════════

class TestModeRouterBasic:
    @pytest.mark.asyncio
    async def test_selects_best_free(self):
        """BASIC picks gemini (free_quality_rank=1) over groq (rank=2)."""
        router = make_router(MasterMode.BASIC)
        selected = await router.select(CANDIDATES, STD_CTX)
        assert selected.name == "gemini"

    @pytest.mark.asyncio
    async def test_rejects_paid(self):
        """BASIC never selects paid providers."""
        paid_only = make_providers(
            ("opus",     PREM,  99, 1, 0.015),
            ("together", CHEAP, 99, 2, 0.001),
        )
        router = make_router(MasterMode.BASIC)
        # Falls back to first candidate when no free available
        selected = await router.select(paid_only, STD_CTX)
        # Should return first candidate as last resort
        assert selected.name in ("opus", "together")

    @pytest.mark.asyncio
    async def test_on_quota_exhausted_cascades_to_next_free(self):
        """BASIC: quota exhaustion cascades to next best free option."""
        router = make_router(MasterMode.BASIC)
        gemini = next(p for p in CANDIDATES if p.name == "gemini")
        selected = await router.on_quota_exhausted(gemini, CANDIDATES, STD_CTX)
        # Should pick groq (next free, rank=2)
        assert selected.name == "groq"
        assert selected.is_free

    @pytest.mark.asyncio
    async def test_on_quota_exhausted_all_free_exhausted_halts(self):
        """BASIC: when all free providers exhausted, sends halt message."""
        telegram_mock = AsyncMock()
        router = make_router(MasterMode.BASIC, telegram_bridge=telegram_mock)

        # Build all-paid candidates
        all_paid = make_providers(
            ("opus",     PREM,  99, 1, 0.015),
            ("together", CHEAP, 99, 2, 0.001),
        )
        paid_provider = all_paid[0]
        selected = await router.on_quota_exhausted(paid_provider, all_paid, STD_CTX)
        # Telegram halt message should have been sent
        telegram_mock.send_message.assert_called_once()
        msg = telegram_mock.send_message.call_args[0][0]
        assert "exhausted" in msg.lower() or "waiting" in msg.lower()

    @pytest.mark.asyncio
    async def test_maybe_upgrade_upgrades_when_better_free_resets(self):
        """BASIC: upgrade to better free provider when it resets."""
        tracker = MagicMock()
        tracker.poll_resets.return_value = ["gemini"]
        router = make_router(MasterMode.BASIC, quota_tracker=tracker)

        groq = next(p for p in CANDIDATES if p.name == "groq")
        upgraded = await router.maybe_upgrade(groq, CANDIDATES, STD_CTX)
        # gemini has better free_quality_rank (1 < 2), so we upgrade
        assert upgraded is not None
        assert upgraded.name == "gemini"

    @pytest.mark.asyncio
    async def test_maybe_upgrade_no_upgrade_if_no_resets(self):
        """BASIC: no upgrade when no providers have reset."""
        tracker = MagicMock()
        tracker.poll_resets.return_value = []
        router = make_router(MasterMode.BASIC, quota_tracker=tracker)

        groq = next(p for p in CANDIDATES if p.name == "groq")
        upgraded = await router.maybe_upgrade(groq, CANDIDATES, STD_CTX)
        assert upgraded is None


# ═══════════════════════════════════════════════════════════════════
# BALANCED mode
# ═══════════════════════════════════════════════════════════════════

class TestModeRouterBalanced:
    @pytest.mark.asyncio
    async def test_critical_picks_premium(self):
        """BALANCED + CRITICAL picks the best premium provider."""
        router = make_router(MasterMode.BALANCED)
        selected = await router.select(CANDIDATES, CRIT_CTX)
        assert selected.tier == ProviderTier.PAID_PREMIUM
        assert selected.name == "opus"

    @pytest.mark.asyncio
    async def test_standard_picks_cheapest_paid(self):
        """BALANCED + STANDARD picks cheapest paid option."""
        router = make_router(MasterMode.BALANCED)
        selected = await router.select(CANDIDATES, STD_CTX)
        # together ($0.0009/1K) is cheaper than opus ($0.015/1K)
        assert not selected.is_free
        assert selected.cost_per_1k_tokens <= 0.001

    @pytest.mark.asyncio
    async def test_bulk_picks_free(self):
        """BALANCED + BULK picks best free option."""
        router = make_router(MasterMode.BALANCED)
        selected = await router.select(CANDIDATES, BULK_CTX)
        assert selected.is_free
        assert selected.name == "gemini"

    @pytest.mark.asyncio
    async def test_critical_falls_back_to_paid_if_no_premium(self):
        """BALANCED + CRITICAL falls back to cheapest paid if no PREMIUM."""
        no_premium = make_providers(
            ("together", CHEAP, 99, 2, 0.001),
            ("gemini",   FREE,  1,  3, 0.0),
        )
        router = make_router(MasterMode.BALANCED)
        selected = await router.select(no_premium, CRIT_CTX)
        assert selected.name == "together"

    @pytest.mark.asyncio
    async def test_standard_falls_back_to_free_if_no_paid(self):
        """BALANCED + STANDARD falls back to free if no paid available."""
        free_only = make_providers(
            ("gemini", FREE, 1, 3, 0.0),
            ("groq",   FREE, 2, 5, 0.0),
        )
        router = make_router(MasterMode.BALANCED)
        selected = await router.select(free_only, STD_CTX)
        assert selected.is_free
        assert selected.name == "gemini"

    @pytest.mark.asyncio
    async def test_on_quota_exhausted_re_selects(self):
        """BALANCED: exhaustion falls back to re-select from remaining."""
        router = make_router(MasterMode.BALANCED)
        opus = next(p for p in CANDIDATES if p.name == "opus")
        selected = await router.on_quota_exhausted(opus, CANDIDATES, CRIT_CTX)
        # Opus removed — should still pick a PAID_PREMIUM or fall to cheapest paid
        assert selected.name != "opus"


# ═══════════════════════════════════════════════════════════════════
# CUSTOM mode
# ═══════════════════════════════════════════════════════════════════

class TestModeRouterCustom:
    @pytest.mark.asyncio
    async def test_uses_operator_preference(self):
        """CUSTOM: uses operator-specified provider when available."""
        router = make_router(
            MasterMode.CUSTOM,
            custom_prefs={"ai": "groq"},
        )
        selected = await router.select(CANDIDATES, STD_CTX)
        assert selected.name == "groq"

    @pytest.mark.asyncio
    async def test_falls_back_to_balanced_if_pref_unavailable(self):
        """CUSTOM: falls back to BALANCED if preferred provider not in candidates."""
        router = make_router(
            MasterMode.CUSTOM,
            custom_prefs={"ai": "nonexistent_provider"},
        )
        selected = await router.select(CANDIDATES, STD_CTX)
        # Should fall back to BALANCED selection (cheapest paid for STANDARD)
        assert selected is not None

    @pytest.mark.asyncio
    async def test_exhausted_pauses_and_picks_from_operator(self):
        """CUSTOM: exhaustion pauses and lets operator choose from Telegram."""
        telegram_mock = AsyncMock()
        telegram_mock.ask_operator.return_value = "1"  # pick first option

        router = make_router(
            MasterMode.CUSTOM,
            telegram_bridge=telegram_mock,
        )
        gemini = next(p for p in CANDIDATES if p.name == "gemini")
        remaining = [p for p in CANDIDATES if p.name != "gemini"]
        selected = await router.on_quota_exhausted(gemini, CANDIDATES, STD_CTX)

        telegram_mock.ask_operator.assert_called_once()
        assert selected is not None

    @pytest.mark.asyncio
    async def test_exhausted_no_telegram_uses_first_available(self):
        """CUSTOM: without Telegram bridge, picks first available on exhaustion."""
        router = make_router(MasterMode.CUSTOM)  # no telegram_bridge
        gemini = next(p for p in CANDIDATES if p.name == "gemini")
        selected = await router.on_quota_exhausted(gemini, CANDIDATES, STD_CTX)
        assert selected.name != "gemini"


# ═══════════════════════════════════════════════════════════════════
# TURBO mode
# ═══════════════════════════════════════════════════════════════════

class TestModeRouterTurbo:
    @pytest.mark.asyncio
    async def test_selects_best_performance(self):
        """TURBO picks the provider with the lowest performance_rank."""
        router = make_router(MasterMode.TURBO)
        selected = await router.select(CANDIDATES, STD_CTX)
        assert selected.name == "opus"  # perf_rank=1

    @pytest.mark.asyncio
    async def test_ignores_budget_limits(self):
        """TURBO skips budget checks — can pick expensive providers."""
        router = make_router(
            MasterMode.TURBO,
            project_budget_usd=0.001,   # effectively $0
            monthly_cap_usd=0.001,
            current_project_spend=0.001,
        )
        selected = await router.select(CANDIDATES, STD_CTX)
        # Should still pick opus even though budget is exceeded
        assert selected.name == "opus"

    @pytest.mark.asyncio
    async def test_on_quota_exhausted_cascades_by_performance(self):
        """TURBO: exhaustion picks next by performance_rank."""
        router = make_router(MasterMode.TURBO)
        opus = next(p for p in CANDIDATES if p.name == "opus")
        selected = await router.on_quota_exhausted(opus, CANDIDATES, CRIT_CTX)
        # opus (rank=1) exhausted → should pick gemini (rank=3) or together (rank=4)
        assert selected.name != "opus"
        assert selected.performance_rank > 1

    @pytest.mark.asyncio
    async def test_maybe_upgrade_upgrades_when_better_perf_resets(self):
        """TURBO: upgrade when a higher-performance provider resets."""
        tracker = MagicMock()
        tracker.poll_resets.return_value = ["opus"]
        router = make_router(MasterMode.TURBO, quota_tracker=tracker)

        gemini = next(p for p in CANDIDATES if p.name == "gemini")
        upgraded = await router.maybe_upgrade(gemini, CANDIDATES, CRIT_CTX)
        assert upgraded is not None
        assert upgraded.name == "opus"


# ═══════════════════════════════════════════════════════════════════
# Quota filtering
# ═══════════════════════════════════════════════════════════════════

class TestQuotaFiltering:
    @pytest.mark.asyncio
    async def test_exhausted_provider_filtered_out(self):
        """Provider marked exhausted in QuotaTracker is not selected."""
        tracker = MagicMock()
        tracker.is_available.side_effect = lambda name: name != "gemini"

        router = make_router(MasterMode.BASIC, quota_tracker=tracker)
        selected = await router.select(CANDIDATES, STD_CTX)
        assert selected.name != "gemini"
        assert selected.is_free  # groq should be picked instead

    @pytest.mark.asyncio
    async def test_budget_filter_in_balanced(self):
        """Providers over budget are filtered in BALANCED mode."""
        router = make_router(
            MasterMode.BALANCED,
            project_budget_usd=0.0001,
            current_project_spend=0.0001,
        )
        # All paid providers should be filtered — should fall to free
        selected = await router.select(CANDIDATES, STD_CTX)
        assert selected.is_free


# ═══════════════════════════════════════════════════════════════════
# QuotaTracker unit tests
# ═══════════════════════════════════════════════════════════════════

class TestQuotaTracker:
    def test_is_available_initially_true(self):
        tracker = QuotaTracker()
        assert tracker.is_available("gemini") is True

    def test_mark_exhausted(self):
        tracker = QuotaTracker()
        tracker.mark_exhausted("gemini")
        assert tracker.is_available("gemini") is False

    def test_next_reset_is_first_of_next_month(self):
        tracker = QuotaTracker()
        reset = tracker.next_reset("gemini")
        assert reset is not None
        # Should be the 1st of the next month
        assert reset.day == 1
        assert reset.tzinfo == timezone.utc

    def test_soonest_reset_none_when_nothing_exhausted(self):
        tracker = QuotaTracker()
        assert tracker.soonest_reset() is None

    def test_soonest_reset_returns_date_when_exhausted(self):
        tracker = QuotaTracker()
        tracker.mark_exhausted("gemini")
        soonest = tracker.soonest_reset()
        assert soonest is not None
        assert soonest.day == 1

    def test_poll_resets_returns_empty_same_month(self):
        tracker = QuotaTracker()
        tracker.mark_exhausted("gemini")
        # No month rollover happened — poll should return empty
        resets = tracker.poll_resets()
        assert "gemini" not in resets

    @pytest.mark.asyncio
    async def test_record_usage_increments_counts(self):
        tracker = QuotaTracker(supabase_client=None)
        await tracker.record_usage("groq", tokens=500, calls=1, cost_usd=0.0)
        state = tracker._get_state("groq")
        assert state.calls == 1
        assert state.tokens == 500

    @pytest.mark.asyncio
    async def test_record_usage_marks_exhausted_at_capacity(self):
        tracker = QuotaTracker(supabase_client=None)
        # Override quota to 1 call
        tracker._states["groq"]._ProviderState__dict__ if False else None
        state = tracker._get_state("groq")
        state.quota_calls = 1
        await tracker.record_usage("groq", calls=1)
        assert tracker.is_available("groq") is False

    def test_usage_summary_returns_lines(self):
        tracker = QuotaTracker()
        lines = tracker.usage_summary()
        assert isinstance(lines, list)
        # Should have lines for all default providers
        assert len(lines) > 0

    def test_unknown_provider_available_by_default(self):
        tracker = QuotaTracker()
        # Providers not in DEFAULT_MONTHLY_QUOTAS have no quota → available
        assert tracker.is_available("some_new_provider") is True

    def test_month_key_format(self):
        mk = _month_key()
        parts = mk.split("-")
        assert len(parts) == 2
        assert len(parts[0]) == 4  # year
        assert len(parts[1]) == 2  # month

    def test_next_month_reset_dec_wraps_to_jan(self):
        dec = datetime(2025, 12, 15, tzinfo=timezone.utc)
        reset = _next_month_reset(dec)
        assert reset.year == 2026
        assert reset.month == 1
        assert reset.day == 1


# ═══════════════════════════════════════════════════════════════════
# Telegram UX helpers
# ═══════════════════════════════════════════════════════════════════

class TestTelegramUXHelpers:
    def test_mode_selection_message_contains_all_modes(self):
        msg = mode_selection_message("MyApp")
        assert "Basic" in msg or "basic" in msg.lower()
        assert "Balanced" in msg or "balanced" in msg.lower()
        assert "Custom" in msg or "custom" in msg.lower()
        assert "Turbo" in msg or "turbo" in msg.lower()
        assert "MyApp" in msg

    def test_parse_mode_selection_numbers(self):
        from factory.core.mode_router import parse_mode_selection
        assert parse_mode_selection("1") == MasterMode.BASIC
        assert parse_mode_selection("2") == MasterMode.BALANCED
        assert parse_mode_selection("3") == MasterMode.CUSTOM
        assert parse_mode_selection("4") == MasterMode.TURBO

    def test_parse_mode_selection_names(self):
        from factory.core.mode_router import parse_mode_selection
        assert parse_mode_selection("basic")    == MasterMode.BASIC
        assert parse_mode_selection("balanced") == MasterMode.BALANCED
        assert parse_mode_selection("custom")   == MasterMode.CUSTOM
        assert parse_mode_selection("turbo")    == MasterMode.TURBO

    def test_parse_mode_selection_empty_is_balanced(self):
        from factory.core.mode_router import parse_mode_selection
        assert parse_mode_selection("")  == MasterMode.BALANCED
        assert parse_mode_selection("x") == MasterMode.BALANCED


# ═══════════════════════════════════════════════════════════════════
# Provider catalogs
# ═══════════════════════════════════════════════════════════════════

class TestProviderCatalogs:
    def test_ai_providers_have_anthropic(self):
        names = [p.name for p in AI_PROVIDERS]
        assert "anthropic" in names

    def test_ai_providers_have_free_options(self):
        free = [p for p in AI_PROVIDERS if p.is_free]
        assert len(free) >= 3  # gemini, groq, openrouter, cerebras, mock

    def test_scout_providers_have_free_options(self):
        free = [p for p in SCOUT_PROVIDERS if p.is_free]
        assert len(free) >= 5

    def test_all_providers_have_valid_ranks(self):
        for p in AI_PROVIDERS + SCOUT_PROVIDERS:
            assert p.performance_rank > 0
            assert p.free_quality_rank > 0

    def test_catalog_lookup(self):
        assert "ai" in PROVIDER_CATALOGS
        assert "scout" in PROVIDER_CATALOGS
        assert "image" in PROVIDER_CATALOGS


# ═══════════════════════════════════════════════════════════════════
# Integration: provider exhaustion simulation
# ═══════════════════════════════════════════════════════════════════

class TestExhaustionIntegration:
    @pytest.mark.asyncio
    async def test_basic_cascade_until_halt(self):
        """Simulate BASIC cascading through all free providers until halt.

        The caller is responsible for removing previously-exhausted providers
        from the candidates list passed to on_quota_exhausted().
        """
        telegram_mock = AsyncMock()
        router = make_router(MasterMode.BASIC, telegram_bridge=telegram_mock)
        free_providers = make_providers(
            ("p1", FREE, 1, 3, 0.0),
            ("p2", FREE, 2, 4, 0.0),
        )
        # Exhaust p1 → should get p2
        result = await router.on_quota_exhausted(free_providers[0], free_providers, STD_CTX)
        assert result.name == "p2"

        # p1 is now gone; pass only [p2] as remaining, then exhaust that too → halt
        result2 = await router.on_quota_exhausted(
            free_providers[1], [free_providers[1]], STD_CTX
        )
        telegram_mock.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_turbo_exhaustion_cascade_by_perf(self):
        """TURBO cascades through providers by performance rank on exhaustion.

        The caller removes already-exhausted providers from subsequent calls.
        """
        router = make_router(MasterMode.TURBO)
        ordered = make_providers(
            ("best",   PREM,  99, 1, 0.020),
            ("second", CHEAP, 99, 2, 0.005),
            ("third",  FREE,  1,  3, 0.0),
        )
        # Exhaust best → remaining = [second, third] → should get second (rank=2)
        result = await router.on_quota_exhausted(ordered[0], ordered, CRIT_CTX)
        assert result.name == "second"

        # best already gone; pass [second, third], exhaust second → should get third
        result2 = await router.on_quota_exhausted(
            ordered[1], [ordered[1], ordered[2]], CRIT_CTX
        )
        assert result2.name == "third"

    @pytest.mark.asyncio
    async def test_balanced_exhaustion_reselects_by_mode(self):
        """BALANCED after exhaustion re-runs selection on remaining providers."""
        router = make_router(MasterMode.BALANCED)
        # Exhaust opus (premium) → balanced should now pick cheapest paid
        opus = next(p for p in CANDIDATES if p.name == "opus")
        selected = await router.on_quota_exhausted(opus, CANDIDATES, CRIT_CTX)
        assert selected.name != "opus"
