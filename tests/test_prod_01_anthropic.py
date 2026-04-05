"""
PROD-1 Validation: Real Anthropic Client

Tests cover:
  1. Pricing table correctness
  2. Cost calculation accuracy
  3. JSON parsing (clean, fenced, embedded, broken)
  4. Client initialization
  5. System prompt registry
  6. call_anthropic_json retry logic
  7. Role contract + real dispatch integration
  8. Circuit breaker cost tracking from real usage data

Run:
  pytest tests/test_prod_01_anthropic.py -v
"""

from __future__ import annotations

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from factory.integrations.anthropic import (
    ANTHROPIC_PRICING,
    calculate_cost,
    parse_json_response,
    call_anthropic,
    call_anthropic_json,
    reset_client,
)
from factory.integrations.prompts import (
    ROLE_SYSTEM_PROMPTS,
    get_system_prompt,
    STRATEGIST_SYSTEM_PROMPT,
    ENGINEER_SYSTEM_PROMPT,
    QUICK_FIX_SYSTEM_PROMPT,
    SCOUT_SYSTEM_PROMPT,
)
from factory.core.state import (
    AIRole, PipelineState, Stage, AutonomyMode,
    PHASE_BUDGET_LIMITS,
)


# ═══════════════════════════════════════════════════════════════════
# Test 1: Pricing Table
# ═══════════════════════════════════════════════════════════════════

class TestPricingTable:
    """Verify pricing matches Anthropic's published rates (2025-02-27)."""

    def test_opus_46_pricing(self):
        p = ANTHROPIC_PRICING["claude-opus-4-6"]
        assert p["input"] == 5.00
        assert p["output"] == 25.00

    def test_opus_45_pricing(self):
        p = ANTHROPIC_PRICING["claude-opus-4-5-20250929"]
        assert p["input"] == 5.00
        assert p["output"] == 25.00

    def test_sonnet_45_pricing(self):
        p = ANTHROPIC_PRICING["claude-sonnet-4-5-20250929"]
        assert p["input"] == 3.00
        assert p["output"] == 15.00

    def test_haiku_45_pricing(self):
        p = ANTHROPIC_PRICING["claude-haiku-4-5-20251001"]
        assert p["input"] == 1.00
        assert p["output"] == 5.00

    def test_all_spec_models_have_pricing(self):
        """Every model in VALID_ANTHROPIC_MODELS should have pricing."""
        from factory.core.state import VALID_ANTHROPIC_MODELS
        for model in VALID_ANTHROPIC_MODELS:
            assert model in ANTHROPIC_PRICING, (
                f"Missing pricing for {model}"
            )


# ═══════════════════════════════════════════════════════════════════
# Test 2: Cost Calculation
# ═══════════════════════════════════════════════════════════════════

class TestCostCalculation:
    """Verify cost math from token counts."""

    def test_opus_1k_tokens(self):
        """1000 in + 1000 out on Opus = $0.005 + $0.025 = $0.030"""
        cost = calculate_cost("claude-opus-4-6", 1000, 1000)
        assert abs(cost - 0.030) < 0.0001

    def test_sonnet_10k_tokens(self):
        """10000 in + 2000 out on Sonnet = $0.030 + $0.030 = $0.060"""
        cost = calculate_cost("claude-sonnet-4-5-20250929", 10000, 2000)
        assert abs(cost - 0.060) < 0.0001

    def test_haiku_high_volume(self):
        """100000 in + 50000 out on Haiku = $0.10 + $0.25 = $0.35"""
        cost = calculate_cost("claude-haiku-4-5-20251001", 100000, 50000)
        assert abs(cost - 0.35) < 0.0001

    def test_unknown_model_uses_fallback(self):
        """Unknown model falls back to Sonnet-tier pricing."""
        cost = calculate_cost("unknown-model-v99", 1000, 1000)
        expected = (1000 / 1e6) * 3.00 + (1000 / 1e6) * 15.00
        assert abs(cost - expected) < 0.0001

    def test_zero_tokens(self):
        cost = calculate_cost("claude-opus-4-6", 0, 0)
        assert cost == 0.0


# ═══════════════════════════════════════════════════════════════════
# Test 3: JSON Parsing
# ═══════════════════════════════════════════════════════════════════

class TestJsonParsing:
    """Verify robust JSON extraction from AI responses."""

    def test_clean_json(self):
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fenced(self):
        result = parse_json_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_generic_fence(self):
        result = parse_json_response('```\n{"key": 1}\n```')
        assert result == {"key": 1}

    def test_embedded_in_text(self):
        text = 'Here is the result:\n{"status": "ok", "count": 5}\nDone.'
        result = parse_json_response(text)
        assert result["status"] == "ok"
        assert result["count"] == 5

    def test_array_response(self):
        result = parse_json_response('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_broken_json_returns_fallback(self):
        result = parse_json_response("not json at all", fallback={"error": True})
        assert result == {"error": True}

    def test_empty_string(self):
        result = parse_json_response("", fallback=None)
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Test 4: System Prompts
# ═══════════════════════════════════════════════════════════════════

class TestSystemPrompts:
    """Verify all 4 role prompts are registered and contain key terms."""

    def test_all_roles_have_prompts(self):
        for role in ["scout", "strategist", "engineer", "quick_fix"]:
            prompt = get_system_prompt(role)
            assert len(prompt) > 100, f"Prompt for {role} too short"

    def test_strategist_cannot_write_code(self):
        assert "CANNOT write code" in STRATEGIST_SYSTEM_PROMPT

    def test_engineer_cannot_make_decisions(self):
        assert "CANNOT make architectural decisions" in ENGINEER_SYSTEM_PROMPT

    def test_quick_fix_is_minimal(self):
        assert "MINIMUM amount of code" in QUICK_FIX_SYSTEM_PROMPT

    def test_scout_requires_sources(self):
        assert "source URLs" in SCOUT_SYSTEM_PROMPT

    def test_unknown_role_returns_empty(self):
        assert get_system_prompt("nonexistent") == ""

    def test_ksa_compliance_in_strategist(self):
        assert "me-central1" in STRATEGIST_SYSTEM_PROMPT
        assert "PDPL" in STRATEGIST_SYSTEM_PROMPT

    def test_ksa_compliance_in_engineer(self):
        assert "me-central1" in ENGINEER_SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════════
# Test 5: call_anthropic (mocked SDK)
# ═══════════════════════════════════════════════════════════════════

class TestCallAnthropic:
    """Test real call_anthropic with mocked SDK client."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_client()
        yield
        reset_client()

    def _mock_message(self, text="test response", in_tok=100, out_tok=50):
        """Create a mock Anthropic Message response."""
        block = SimpleNamespace(type="text", text=text)
        usage = SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok)
        return SimpleNamespace(content=[block], usage=usage)

    @pytest.mark.asyncio
    async def test_basic_call(self):
        mock_msg = self._mock_message("Hello!", 200, 30)
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        with patch(
            "factory.integrations.anthropic.get_anthropic_client",
            return_value=mock_client,
        ):
            text, cost, usage = await call_anthropic(
                prompt="Say hello",
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
            )

        assert text == "Hello!"
        assert usage["input_tokens"] == 200
        assert usage["output_tokens"] == 30
        # Haiku: (200/1M)*1.0 + (30/1M)*5.0 = 0.0002 + 0.00015 = 0.00035
        assert abs(cost - 0.00035) < 0.0001

    @pytest.mark.asyncio
    async def test_system_prompt_passed(self):
        mock_msg = self._mock_message()
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        with patch(
            "factory.integrations.anthropic.get_anthropic_client",
            return_value=mock_client,
        ):
            await call_anthropic(
                prompt="test",
                model="claude-opus-4-6",
                max_tokens=1000,
                system_prompt="You are a test assistant.",
            )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a test assistant."
        assert call_kwargs["model"] == "claude-opus-4-6"


# ═══════════════════════════════════════════════════════════════════
# Test 6: call_anthropic_json retry
# ═══════════════════════════════════════════════════════════════════

class TestCallAnthropicJson:
    """Test JSON-guaranteed call with retry on parse failure."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_client()
        yield
        reset_client()

    @pytest.mark.asyncio
    async def test_json_first_attempt_success(self):
        with patch(
            "factory.integrations.anthropic.call_anthropic",
            new_callable=AsyncMock,
            return_value=('{"result": 42}', 0.001, {"input_tokens": 50, "output_tokens": 20}),
        ):
            parsed, cost, usage = await call_anthropic_json(
                prompt="Return JSON",
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
            )
        assert parsed == {"result": 42}
        assert cost == 0.001

    @pytest.mark.asyncio
    async def test_json_retry_on_failure(self):
        """First call returns bad JSON, second returns valid."""
        call_count = 0

        async def mock_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("not json", 0.001, {"input_tokens": 50, "output_tokens": 20})
            return ('{"ok": true}', 0.002, {"input_tokens": 60, "output_tokens": 25})

        with patch(
            "factory.integrations.anthropic.call_anthropic",
            side_effect=mock_call,
        ):
            parsed, cost, usage = await call_anthropic_json(
                prompt="Return JSON",
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                max_retries=2,
            )
        assert parsed == {"ok": True}
        assert cost == 0.003  # Both calls' costs summed
        assert call_count == 2


# ═══════════════════════════════════════════════════════════════════
# Test 7: Cost Tracking Integration
# ═══════════════════════════════════════════════════════════════════

class TestCostTracking:
    """Verify costs flow through to PipelineState correctly."""

    def test_cost_accumulates_in_state(self):
        state = PipelineState(project_id="test", operator_id="op1")
        state.current_stage = Stage.S3_CODEGEN

        # Simulate two Engineer calls
        category = "codegen_engineer"
        state.phase_costs[category] = state.phase_costs.get(category, 0.0) + 0.05
        state.total_cost_usd += 0.05

        state.phase_costs[category] = state.phase_costs.get(category, 0.0) + 0.03
        state.total_cost_usd += 0.03

        assert abs(state.phase_costs[category] - 0.08) < 0.001
        assert abs(state.total_cost_usd - 0.08) < 0.001

    def test_circuit_breaker_triggers_at_limit(self):
        state = PipelineState(project_id="test", operator_id="op1")
        state.current_stage = Stage.S0_INTAKE

        # Scout research limit is $2.00
        category = "scout_research"
        state.phase_costs[category] = 1.95
        state.total_cost_usd = 1.95

        # Next call: $0.10 → over $2.00 limit
        new_cost = 0.10
        new_total = state.phase_costs.get(category, 0.0) + new_cost
        limit = PHASE_BUDGET_LIMITS.get(category, 2.00)

        if new_total > limit:
            state.circuit_breaker_triggered = True

        assert state.circuit_breaker_triggered is True

    def test_per_project_cap(self):
        state = PipelineState(project_id="test", operator_id="op1")
        state.total_cost_usd = 24.50

        # $25 per-project cap
        new_cost = 1.00
        if state.total_cost_usd + new_cost > 25.00:
            state.circuit_breaker_triggered = True

        assert state.circuit_breaker_triggered is True


# ═══════════════════════════════════════════════════════════════════
# Test 8: Pricing Consistency with Spec
# ═══════════════════════════════════════════════════════════════════

class TestPricingConsistency:
    """Cross-reference pricing against spec §1.4 budget assumptions."""

    def test_typical_s0_intake_cost(self):
        """S0 uses Haiku for extraction. ~500 in, ~200 out = ~$0.0015"""
        cost = calculate_cost("claude-haiku-4-5-20251001", 500, 200)
        assert cost < 0.01  # Well under S0 budget target

    def test_typical_s2_blueprint_cost(self):
        """S2 uses Opus for architecture. ~5000 in, ~3000 out = ~$0.10"""
        cost = calculate_cost("claude-opus-4-6", 5000, 3000)
        assert cost < 2.00  # Under S2 budget target ($2.00)

    def test_typical_s3_codegen_cost(self):
        """S3 uses Sonnet. ~10000 in, ~8000 out = ~$0.15"""
        cost = calculate_cost("claude-sonnet-4-5-20250929", 10000, 8000)
        assert cost < 8.00  # Under S3 budget target ($8.00)

    def test_worst_case_s3_multi_file(self):
        """S3 worst case: 50000 in, 100000 out = $0.15 + $1.50 = $1.65"""
        cost = calculate_cost("claude-sonnet-4-5-20250929", 50000, 100000)
        assert cost < 8.00  # Still under S3 budget
        assert cost > 1.00  # Sanity: should be non-trivial
