"""Tests for factory.config (P10 Configuration)."""

from factory.config import (
    PIPELINE_VERSION, PIPELINE_FULL_VERSION,
    MODELS, BUDGET, DELIVERY, COMPLIANCE, DATA_RESIDENCY,
    WAR_ROOM, APP_STORE, VECTOR_BACKEND,
    REQUIRED_SECRETS, CONDITIONAL_SECRETS,
    validate_required_config, get_config_summary,
)


class TestVersions:
    def test_version(self):
        assert PIPELINE_VERSION == "5.8"
        assert PIPELINE_FULL_VERSION == "5.8.0"


class TestModels:
    def test_defaults(self):
        assert MODELS.strategist == "claude-opus-4-6"
        assert MODELS.engineer == "claude-sonnet-4-5-20250929"
        assert MODELS.quick_fix == "claude-haiku-4-5-20251001"
        assert MODELS.scout == "sonar-pro"

    def test_frozen(self):
        with pytest.raises(Exception):
            MODELS.strategist = "changed"


class TestBudget:
    def test_defaults(self):
        assert BUDGET.enabled is True
        assert BUDGET.monthly_budget_usd == 300.0
        assert BUDGET.circuit_breaker_usd == 2.0
        assert BUDGET.sar_rate == 3.75

    def test_tiers(self):
        assert BUDGET.green_pct == 0.0
        assert BUDGET.amber_pct == 80.0
        assert BUDGET.red_pct == 95.0
        assert BUDGET.black_pct == 100.0


class TestDelivery:
    def test_defaults(self):
        assert DELIVERY.telegram_file_limit_mb == 50
        assert DELIVERY.artifact_ttl_hours == 72


class TestDataResidency:
    def test_primary(self):
        assert DATA_RESIDENCY.primary_region == "me-central1"
        assert len(DATA_RESIDENCY.allowed_regions) == 4


class TestConfigSummary:
    def test_summary(self):
        s = get_config_summary()
        assert s["version"] == "5.8.0"
        assert "models" in s
        assert "budget" in s


class TestSecrets:
    def test_required(self):
        assert len(REQUIRED_SECRETS) >= 9
        assert len(CONDITIONAL_SECRETS) >= 4


import pytest