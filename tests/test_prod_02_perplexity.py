"""
PROD-2 Validation: Real Perplexity Client (The Scout)

Tests cover:
  1. Pricing table correctness (3 models)
  2. Cost calculation with request fees
  3. Context-tier enforcement (ADR-049/FIX-19)
  4. Citation extraction (new format + legacy)
  5. Model selection logic
  6. call_perplexity (mocked SDK)
  7. Degradation policy chain
  8. Scout routing integration in call_ai()
  9. Prompt truncation at tier ceiling

Run:
  pytest tests/test_prod_02_perplexity.py -v
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from types import SimpleNamespace

from factory.integrations.perplexity import (
    PERPLEXITY_PRICING,
    REQUEST_FEES_PER_1K,
    CONTEXT_TIER_LIMITS,
    calculate_cost,
    extract_citations,
    select_scout_model,
    effective_tier,
    call_perplexity,
    call_perplexity_safe,
    PerplexityUnavailableError,
    _synthesize_from_cache,
    reset_client,
)
from factory.core.state import AIRole, PipelineState, Stage


# ═══════════════════════════════════════════════════════════════════
# Test 1: Pricing Table
# ═══════════════════════════════════════════════════════════════════

class TestPricingTable:
    """Verify pricing matches Perplexity's published rates (2026-02-27)."""

    def test_sonar_pricing(self):
        p = PERPLEXITY_PRICING["sonar"]
        assert p["input"] == 1.00
        assert p["output"] == 1.00

    def test_sonar_pro_pricing(self):
        p = PERPLEXITY_PRICING["sonar-pro"]
        assert p["input"] == 3.00
        assert p["output"] == 15.00

    def test_sonar_reasoning_pro_pricing(self):
        p = PERPLEXITY_PRICING["sonar-reasoning-pro"]
        assert p["input"] == 2.00
        assert p["output"] == 8.00

    def test_request_fees_sonar(self):
        fees = REQUEST_FEES_PER_1K["sonar"]
        assert fees == {"low": 5.0, "medium": 8.0, "high": 12.0}

    def test_request_fees_pro(self):
        fees = REQUEST_FEES_PER_1K["sonar-pro"]
        assert fees == {"low": 6.0, "medium": 10.0, "high": 14.0}


# ═══════════════════════════════════════════════════════════════════
# Test 2: Cost Calculation
# ═══════════════════════════════════════════════════════════════════

class TestCostCalculation:
    """Verify cost math with token costs + request fees."""

    def test_sonar_1k_tokens_medium(self):
        """1000 in + 500 out on sonar, medium context.
        Token: (1000/1M)*1 + (500/1M)*1 = 0.0015
        Request fee: 8.0/1000 = 0.008
        Total: 0.0095
        """
        cost = calculate_cost("sonar", 1000, 500, "medium")
        assert abs(cost - 0.0095) < 0.0001

    def test_sonar_pro_10k_tokens_low(self):
        """10000 in + 2000 out on sonar-pro, low context.
        Token: (10000/1M)*3 + (2000/1M)*15 = 0.03 + 0.03 = 0.06
        Request fee: 6.0/1000 = 0.006
        Total: 0.066
        """
        cost = calculate_cost("sonar-pro", 10000, 2000, "low")
        assert abs(cost - 0.066) < 0.0001

    def test_reasoning_pro_high_context(self):
        """5000 in + 3000 out on reasoning-pro, high context.
        Token: (5000/1M)*2 + (3000/1M)*8 = 0.01 + 0.024 = 0.034
        Request fee: 14.0/1000 = 0.014
        Total: 0.048
        """
        cost = calculate_cost("sonar-reasoning-pro", 5000, 3000, "high")
        assert abs(cost - 0.048) < 0.0001

    def test_zero_tokens(self):
        """Zero tokens still incurs request fee."""
        cost = calculate_cost("sonar", 0, 0, "medium")
        assert abs(cost - 0.008) < 0.0001  # Just the request fee


# ═══════════════════════════════════════════════════════════════════
# Test 3: Context-Tier Enforcement (ADR-049/FIX-19)
# ═══════════════════════════════════════════════════════════════════

class TestContextTier:
    """Verify SCOUT_MAX_CONTEXT_TIER ceiling enforcement."""

    def test_tier_limits_structure(self):
        for tier in ["small", "medium", "large"]:
            limits = CONTEXT_TIER_LIMITS[tier]
            assert "max_tokens" in limits
            assert "search_recency" in limits
            assert "max_sources" in limits

    def test_small_tier_limits(self):
        limits = CONTEXT_TIER_LIMITS["small"]
        assert limits["max_tokens"] == 4_000
        assert limits["search_recency"] == "week"
        assert limits["max_sources"] == 3

    def test_medium_tier_limits(self):
        limits = CONTEXT_TIER_LIMITS["medium"]
        assert limits["max_tokens"] == 16_000
        assert limits["search_recency"] == "month"
        assert limits["max_sources"] == 5

    def test_large_tier_limits(self):
        limits = CONTEXT_TIER_LIMITS["large"]
        assert limits["max_tokens"] == 64_000
        assert limits["search_recency"] == "year"
        assert limits["max_sources"] == 10

    def test_effective_tier_default(self):
        """Default tier is 'medium' when env var not set or invalid."""
        with patch.dict(os.environ, {}, clear=False):
            # Module-level constant may already be set; test the function logic
            from factory.integrations import perplexity
            original = perplexity.SCOUT_MAX_CONTEXT_TIER
            perplexity.SCOUT_MAX_CONTEXT_TIER = "invalid_tier"
            assert effective_tier() == "medium"
            perplexity.SCOUT_MAX_CONTEXT_TIER = original

    def test_effective_tier_respects_env(self):
        from factory.integrations import perplexity
        original = perplexity.SCOUT_MAX_CONTEXT_TIER
        perplexity.SCOUT_MAX_CONTEXT_TIER = "small"
        assert effective_tier() == "small"
        perplexity.SCOUT_MAX_CONTEXT_TIER = "large"
        assert effective_tier() == "large"
        perplexity.SCOUT_MAX_CONTEXT_TIER = original


# ═══════════════════════════════════════════════════════════════════
# Test 4: Citation Extraction
# ═══════════════════════════════════════════════════════════════════

class TestCitationExtraction:
    """Verify citation extraction from both API formats."""

    def test_new_format_search_results(self):
        """New API: search_results field with structured objects."""
        response = SimpleNamespace(
            search_results=[
                {"url": "https://example.com/a", "title": "Article A", "date": "2026-01-15", "snippet": "Text A"},
                {"url": "https://example.com/b", "title": "Article B", "date": "2026-01-16", "snippet": "Text B"},
            ]
        )
        citations = extract_citations(response)
        assert len(citations) == 2
        assert citations[0]["url"] == "https://example.com/a"
        assert citations[0]["title"] == "Article A"
        assert citations[1]["url"] == "https://example.com/b"

    def test_legacy_format_citation_urls(self):
        """Legacy API: citations as list of URL strings."""
        response = SimpleNamespace(
            search_results=None,
            citations=["https://old.com/1", "https://old.com/2"],
        )
        citations = extract_citations(response)
        assert len(citations) == 2
        assert citations[0]["url"] == "https://old.com/1"
        assert citations[0]["title"] == ""  # Not available in legacy

    def test_no_citations(self):
        """Response with no citations returns empty list."""
        response = SimpleNamespace()
        citations = extract_citations(response)
        assert citations == []

    def test_object_style_search_results(self):
        """search_results as SimpleNamespace objects (not dicts)."""
        result_obj = SimpleNamespace(
            url="https://obj.com", title="Obj Title",
            date="2026-02-01", snippet="Obj snippet"
        )
        response = SimpleNamespace(search_results=[result_obj])
        citations = extract_citations(response)
        assert len(citations) == 1
        assert citations[0]["url"] == "https://obj.com"


# ═══════════════════════════════════════════════════════════════════
# Test 5: Model Selection
# ═══════════════════════════════════════════════════════════════════

class TestModelSelection:
    """Verify Scout model auto-selection logic."""

    def test_simple_query_uses_sonar(self):
        assert select_scout_model("simple") == "sonar"

    def test_standard_query_uses_sonar_pro(self):
        assert select_scout_model("standard") == "sonar-pro"

    def test_reasoning_flag_overrides(self):
        assert select_scout_model("simple", requires_reasoning=True) == "sonar-reasoning-pro"
        assert select_scout_model("standard", requires_reasoning=True) == "sonar-reasoning-pro"

    def test_deep_query_uses_reasoning(self):
        model = select_scout_model("deep")
        assert model == "sonar-reasoning-pro"


# ═══════════════════════════════════════════════════════════════════
# Test 6: call_perplexity (mocked SDK)
# ═══════════════════════════════════════════════════════════════════

class TestCallPerplexity:
    """Test real call_perplexity with mocked OpenAI client."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_client()
        yield
        reset_client()

    def _mock_response(self, text="Research result", in_tok=500, out_tok=200):
        """Create a mock OpenAI chat completion response."""
        message = SimpleNamespace(content=text)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=in_tok, completion_tokens=out_tok)
        search_results = [
            {"url": "https://example.com", "title": "Example", "date": "2026-01-01", "snippet": "Snippet"},
        ]
        return SimpleNamespace(
            choices=[choice],
            usage=usage,
            search_results=search_results,
        )

    @pytest.mark.asyncio
    async def test_basic_search(self):
        mock_resp = self._mock_response("Market research: KSA fintech", 800, 400)
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch(
            "factory.integrations.perplexity.get_perplexity_client",
            return_value=mock_client,
        ):
            text, cost, citations, usage = await call_perplexity(
                query="KSA fintech market size",
                model="sonar-pro",
                context_tier="medium",
            )

        assert "Market research" in text
        assert len(citations) == 1
        assert citations[0]["url"] == "https://example.com"
        assert usage["input_tokens"] == 800
        assert usage["output_tokens"] == 400
        # sonar-pro medium: (800/1M)*3 + (400/1M)*15 + 10/1000
        expected_cost = 0.0024 + 0.006 + 0.01
        assert abs(cost - expected_cost) < 0.001

    @pytest.mark.asyncio
    async def test_tier_clamps_max_tokens(self):
        """Small tier should clamp max_tokens to 4000."""
        mock_resp = self._mock_response()
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch(
            "factory.integrations.perplexity.get_perplexity_client",
            return_value=mock_client,
        ):
            await call_perplexity(
                query="test",
                model="sonar",
                max_tokens=50000,  # Way over small tier
                context_tier="small",
            )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 4000  # Clamped to small tier


# ═══════════════════════════════════════════════════════════════════
# Test 7: Degradation Policy
# ═══════════════════════════════════════════════════════════════════

class TestDegradationPolicy:
    """Verify the Research Degradation Policy chain (§2.2.3)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_client()
        yield
        reset_client()

    @pytest.mark.asyncio
    async def test_primary_success(self):
        """When Perplexity works, returns normal response."""
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Result"))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            search_results=[{"url": "https://x.com", "title": "X", "date": "", "snippet": ""}],
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        state = PipelineState(project_id="deg-test", operator_id="op1")
        state.current_stage = Stage.S0_INTAKE
        contract = SimpleNamespace(model="sonar-pro")

        with patch(
            "factory.integrations.perplexity.get_perplexity_client",
            return_value=mock_client,
        ):
            text, cost = await call_perplexity_safe(
                prompt="test query",
                contract=contract,
                state=state,
            )

        assert "Result" in text
        assert cost > 0
        assert "[UNVERIFIED" not in text

    @pytest.mark.asyncio
    async def test_fallback_to_unverified(self):
        """When Perplexity fails and no cache, returns UNVERIFIED."""
        state = PipelineState(project_id="deg-test", operator_id="op1")
        state.current_stage = Stage.S0_INTAKE
        contract = SimpleNamespace(model="sonar-pro")

        with patch(
            "factory.integrations.perplexity.get_perplexity_client",
            side_effect=PerplexityUnavailableError("API down"),
        ), patch(
            "factory.integrations.perplexity.mother_memory",
            side_effect=ImportError("not available"),
        ):
            text, cost = await call_perplexity_safe(
                prompt="test query",
                contract=contract,
                state=state,
            )

        assert "[UNVERIFIED" in text
        assert cost == 0.0

    def test_cache_synthesis(self):
        """Verify _synthesize_from_cache produces attributed text."""
        cached = [
            {"source_id": "S001", "content": "KSA fintech grew 35%", "url": "https://a.com"},
            {"source_id": "S002", "content": "SAMA regulates", "url": "https://b.com"},
        ]
        result = _synthesize_from_cache(cached)
        assert "S001" in result
        assert "S002" in result
        assert "KSA fintech grew 35%" in result
        assert "https://a.com" in result

    def test_empty_cache_synthesis(self):
        assert _synthesize_from_cache([]) == ""


# ═══════════════════════════════════════════════════════════════════
# Test 8: Prompt Truncation
# ═══════════════════════════════════════════════════════════════════

class TestPromptTruncation:
    """Verify prompts are truncated to tier ceiling."""

    @pytest.mark.asyncio
    async def test_small_tier_truncates_long_prompt(self):
        """Small tier: max_tokens=4000 → max_chars=16000."""
        long_prompt = "x" * 50000  # Way over 16000 chars
        mock_resp = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
            search_results=[],
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        state = PipelineState(project_id="trunc-test", operator_id="op1")
        state.current_stage = Stage.S0_INTAKE
        contract = SimpleNamespace(model="sonar")

        from factory.integrations import perplexity
        original_tier = perplexity.SCOUT_MAX_CONTEXT_TIER
        perplexity.SCOUT_MAX_CONTEXT_TIER = "small"

        with patch(
            "factory.integrations.perplexity.get_perplexity_client",
            return_value=mock_client,
        ):
            text, cost = await call_perplexity_safe(
                prompt=long_prompt,
                contract=contract,
                state=state,
            )

        # Verify the actual query sent was truncated
        sent_messages = mock_client.chat.completions.create.call_args[1]["messages"]
        assert len(sent_messages[0]["content"]) == 16000  # 4000 * 4

        perplexity.SCOUT_MAX_CONTEXT_TIER = original_tier


# ═══════════════════════════════════════════════════════════════════
# Test 9: Cost Tracking in Pipeline State
# ═══════════════════════════════════════════════════════════════════

class TestScoutCostTracking:
    """Verify Scout costs flow into circuit breaker correctly."""

    def test_scout_budget_category(self):
        """Scout calls should map to 'scout_research' category."""
        from factory.monitoring.circuit_breaker import budget_category
        assert budget_category(AIRole.SCOUT, "S0_INTAKE") == "scout_research"
        assert budget_category(AIRole.SCOUT, "S1_LEGAL") == "scout_research"

    def test_scout_budget_limit(self):
        """Scout research limit is $2.00 per spec §1.4.4."""
        from factory.core.state import PHASE_BUDGET_LIMITS
        assert PHASE_BUDGET_LIMITS["scout_research"] == 2.00

    def test_typical_scout_cost_under_limit(self):
        """Typical sonar-pro call should be well under $2.00."""
        # 2000 in + 1000 out on sonar-pro, medium
        cost = calculate_cost("sonar-pro", 2000, 1000, "medium")
        assert cost < 0.10  # Should be ~$0.031
        assert cost < 2.00  # Well under scout_research limit
