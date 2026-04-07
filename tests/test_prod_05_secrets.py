"""
PROD-5 Validation: Real GCP Secret Manager + Service Verifiers

Tests cover:
  1. Appendix B constants (15 secrets, 9 core, 6 deferrable)
  2. TTL cache (set, get, expiry)
  3. get_secret() env var fallback
  4. get_secret_or_raise() missing secret
  5. store_secret() env var fallback (no GCP)
  6. check_secret_exists() env var path
  7. validate_secrets_preflight() — all missing
  8. validate_secrets_preflight() — core present
  9. validate_secrets_preflight() — strict mode raises
  10. Rotation status metadata
  11. SECRET_SEVERITY mapping
  12. Cache clearing
  13. get_secret() resolution order (cache first)
  14. Verify functions exist and are callable
  15. verify_all_services() returns structured results

Run:
  pytest tests/test_prod_05_secrets.py -v
"""

from __future__ import annotations

import os
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from factory.core.secrets import (
    REQUIRED_SECRETS,
    CORE_SECRETS,
    DEFERRABLE_SECRETS,
    SECRET_ROTATION_DAYS,
    SECRET_SEVERITY,
    get_secret,
    get_secret_or_raise,
    store_secret,
    check_secret_exists,
    validate_secrets_preflight,
    get_rotation_status,
    clear_cache,
    _cache_get,
    _cache_set,
    _CACHE_TTL_SECONDS,
    reset_gcp_client,
)
from factory.setup.verify import (
    verify_anthropic,
    verify_perplexity,
    verify_supabase,
    verify_neo4j,
    verify_github,
    verify_all_services,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_state():
    """Clear caches and reset GCP client before each test."""
    clear_cache()
    reset_gcp_client()
    yield
    clear_cache()
    reset_gcp_client()


# ═══════════════════════════════════════════════════════════════════
# Test 1: Appendix B Constants
# ═══════════════════════════════════════════════════════════════════

class TestAppendixBConstants:
    def test_15_required_secrets(self):
        """Appendix B specifies ≥15 secrets total (16 after adding PERPLEXITY_API_KEY)."""
        assert len(REQUIRED_SECRETS) >= 15

    def test_9_core_secrets(self):
        """9 core secrets required for pipeline startup."""
        assert len(CORE_SECRETS) == 9

    def test_6_deferrable_secrets(self):
        """≥6 secrets deferrable until specific feature use (7 after adding PERPLEXITY_API_KEY)."""
        assert len(DEFERRABLE_SECRETS) >= 6

    def test_core_is_subset_of_required(self):
        """All core secrets must be in required list."""
        for s in CORE_SECRETS:
            assert s in REQUIRED_SECRETS

    def test_deferrable_is_subset_of_required(self):
        """All deferrable secrets must be in required list."""
        for s in DEFERRABLE_SECRETS:
            assert s in REQUIRED_SECRETS

    def test_core_and_deferrable_cover_all(self):
        """Core + deferrable must cover all required secrets (deferrable may include optional extras)."""
        covered = set(CORE_SECRETS) | DEFERRABLE_SECRETS
        assert set(REQUIRED_SECRETS) <= covered

    def test_rotation_schedule_complete(self):
        """All secrets with rotation schedules should be in required."""
        for name in SECRET_ROTATION_DAYS:
            assert name in REQUIRED_SECRETS

    def test_known_secrets_present(self):
        """Core secrets from spec must exist in required list."""
        assert "ANTHROPIC_API_KEY" in REQUIRED_SECRETS
        assert "GOOGLE_AI_API_KEY" in REQUIRED_SECRETS   # free AI fallback
        assert "TELEGRAM_BOT_TOKEN" in REQUIRED_SECRETS
        assert "TELEGRAM_OPERATOR_ID" in REQUIRED_SECRETS
        assert "SUPABASE_URL" in REQUIRED_SECRETS
        assert "NEO4J_URI" in REQUIRED_SECRETS
        assert "GITHUB_TOKEN" in REQUIRED_SECRETS


# ═══════════════════════════════════════════════════════════════════
# Test 2: TTL Cache
# ═══════════════════════════════════════════════════════════════════

class TestTTLCache:
    def test_cache_set_and_get(self):
        _cache_set("TEST_KEY", "test_value")
        assert _cache_get("TEST_KEY") == "test_value"

    def test_cache_miss(self):
        assert _cache_get("NONEXISTENT") is None

    def test_cache_expiry(self):
        """Expired entries return None."""
        from factory.core import secrets as mod
        original_ttl = mod._CACHE_TTL_SECONDS
        try:
            mod._CACHE_TTL_SECONDS = 0.01  # 10ms TTL
            _cache_set("SHORT", "value")
            time.sleep(0.02)
            assert _cache_get("SHORT") is None
        finally:
            mod._CACHE_TTL_SECONDS = original_ttl

    def test_clear_cache(self):
        _cache_set("A", "1")
        _cache_set("B", "2")
        clear_cache()
        assert _cache_get("A") is None
        assert _cache_get("B") is None


# ═══════════════════════════════════════════════════════════════════
# Test 3: get_secret() Env Var Fallback
# ═══════════════════════════════════════════════════════════════════

class TestGetSecret:
    def test_env_var_fallback(self):
        """get_secret() returns env var when GCP unavailable."""
        with patch.dict(os.environ, {"TEST_SECRET": "from_env"}):
            val = get_secret("TEST_SECRET")
            assert val == "from_env"

    def test_missing_returns_none(self):
        """get_secret() returns None for absent secret."""
        val = get_secret("DEFINITELY_NOT_SET_XYZZY")
        assert val is None

    def test_cache_is_populated(self):
        """get_secret() populates cache on first read."""
        with patch.dict(os.environ, {"CACHED_TEST": "cached_val"}):
            get_secret("CACHED_TEST")
            # Second read should come from cache
            assert _cache_get("CACHED_TEST") == "cached_val"

    def test_cache_hit_skips_env(self):
        """Cache hit returns value without checking env."""
        _cache_set("DIRECT_CACHE", "from_cache")
        # Even without env var, cache should return the value
        val = get_secret("DIRECT_CACHE")
        assert val == "from_cache"


# ═══════════════════════════════════════════════════════════════════
# Test 4: get_secret_or_raise()
# ═══════════════════════════════════════════════════════════════════

class TestGetSecretOrRaise:
    def test_returns_value_when_present(self):
        with patch.dict(os.environ, {"RAISE_TEST": "value"}):
            assert get_secret_or_raise("RAISE_TEST") == "value"

    def test_raises_when_missing(self):
        with pytest.raises(EnvironmentError, match="Required secret"):
            get_secret_or_raise("MISSING_SECRET_XYZ")


# ═══════════════════════════════════════════════════════════════════
# Test 5: store_secret() Env Var Fallback
# ═══════════════════════════════════════════════════════════════════

class TestStoreSecret:
    def test_store_sets_env_when_no_gcp(self):
        """Without GCP, store_secret() sets env var."""
        result = store_secret("STORED_TEST", "stored_value")
        assert result is True
        assert os.getenv("STORED_TEST") == "stored_value"
        # Clean up
        os.environ.pop("STORED_TEST", None)

    def test_store_updates_cache(self):
        """store_secret() should populate cache."""
        store_secret("STORE_CACHE", "cached")
        assert _cache_get("STORE_CACHE") == "cached"
        os.environ.pop("STORE_CACHE", None)


# ═══════════════════════════════════════════════════════════════════
# Test 6: check_secret_exists()
# ═══════════════════════════════════════════════════════════════════

class TestCheckSecretExists:
    def test_exists_via_env(self):
        with patch.dict(os.environ, {"EXISTS_TEST": "val"}):
            assert check_secret_exists("EXISTS_TEST") is True

    def test_not_exists(self):
        assert check_secret_exists("NOT_EXISTS_XYZZY") is False


# ═══════════════════════════════════════════════════════════════════
# Test 7-9: validate_secrets_preflight()
# ═══════════════════════════════════════════════════════════════════

class TestValidateSecretsPreflight:
    def test_all_missing(self):
        """With no env vars set, all should be missing."""
        # Mock get_secret to return None for everything — simulates a fresh machine
        # without fighting the cache, .env auto-load, or GCP fallback.
        with patch("factory.core.secrets.get_secret", return_value=None):
            result = validate_secrets_preflight(strict=False)
        assert result["all_present"] is False
        assert result["core_present"] == 0
        assert len(result["missing_critical"]) == len(CORE_SECRETS)
        assert len(result["details"]) == len(REQUIRED_SECRETS)

    def test_core_present(self):
        """Set all core secrets, verify counts."""
        def mock_get_secret(name):
            return "test" if name in CORE_SECRETS else None
        with patch("factory.core.secrets.get_secret", side_effect=mock_get_secret):
            result = validate_secrets_preflight(strict=False)
            assert result["core_present"] == len(CORE_SECRETS)
            assert len(result["missing_critical"]) == 0
            assert len(result["missing_deferrable"]) == len(DEFERRABLE_SECRETS)

    def test_strict_mode_raises(self):
        """Strict mode raises when critical secrets missing."""
        with patch("factory.core.secrets.get_secret", return_value=None):
            with pytest.raises(EnvironmentError, match="CRITICAL"):
                validate_secrets_preflight(strict=True)

    def test_all_present(self):
        """Set all secrets, verify all_present is True."""
        env_overrides = {name: "test" for name in REQUIRED_SECRETS}
        with patch.dict(os.environ, env_overrides):
            result = validate_secrets_preflight(strict=False)
            assert result["all_present"] is True
            assert result["total_present"] == len(REQUIRED_SECRETS)
            assert result["core_present"] == 9


# ═══════════════════════════════════════════════════════════════════
# Test 10-11: Rotation Status & Severity
# ═══════════════════════════════════════════════════════════════════

class TestRotationAndSeverity:
    def test_rotation_status_has_all_secrets(self):
        status = get_rotation_status()
        assert len(status) >= 15
        for name in REQUIRED_SECRETS:
            assert name in status

    def test_rotation_days_positive(self):
        """All rotation periods should be > 0."""
        for days in SECRET_ROTATION_DAYS.values():
            assert days > 0

    def test_severity_mapping_complete(self):
        """Every required secret must have a severity."""
        for name in REQUIRED_SECRETS:
            assert name in SECRET_SEVERITY
            assert SECRET_SEVERITY[name] in ("CRITICAL", "DEFERRABLE")

    def test_core_are_critical(self):
        for name in CORE_SECRETS:
            assert SECRET_SEVERITY[name] == "CRITICAL"

    def test_deferrable_are_deferrable(self):
        for name in DEFERRABLE_SECRETS:
            assert SECRET_SEVERITY[name] == "DEFERRABLE"


# ═══════════════════════════════════════════════════════════════════
# Test 12-13: Cache Clearing & Resolution Order
# ═══════════════════════════════════════════════════════════════════

class TestCacheAndResolution:
    def test_cache_clear_empties_all(self):
        _cache_set("X", "1")
        _cache_set("Y", "2")
        assert _cache_get("X") == "1"
        clear_cache()
        assert _cache_get("X") is None
        assert _cache_get("Y") is None

    def test_cache_takes_priority_over_env(self):
        """Cache should be read before env var."""
        _cache_set("PRIORITY_TEST", "from_cache")
        with patch.dict(os.environ, {"PRIORITY_TEST": "from_env"}):
            val = get_secret("PRIORITY_TEST")
            assert val == "from_cache"


# ═══════════════════════════════════════════════════════════════════
# Test 14-15: Verify Functions
# ═══════════════════════════════════════════════════════════════════

class TestVerifyFunctions:
    def test_verify_functions_are_callable(self):
        """All 5 verify functions must be async callables."""
        import asyncio
        assert asyncio.iscoroutinefunction(verify_anthropic)
        assert asyncio.iscoroutinefunction(verify_perplexity)
        assert asyncio.iscoroutinefunction(verify_supabase)
        assert asyncio.iscoroutinefunction(verify_neo4j)
        assert asyncio.iscoroutinefunction(verify_github)

    def test_verify_functions_require_secrets(self):
        """All verify functions should raise when secret is missing."""
        import asyncio

        with patch("factory.core.secrets.get_secret", return_value=None):
            for fn in [verify_anthropic, verify_perplexity, verify_neo4j,
                        verify_github]:
                with pytest.raises(EnvironmentError):
                    asyncio.get_event_loop().run_until_complete(fn())

    @pytest.mark.asyncio
    async def test_verify_all_returns_structured(self):
        """verify_all_services() should return dict for all 5 services."""
        results = await verify_all_services()
        assert len(results) == 5
        assert "Anthropic" in results
        assert "Perplexity" in results
        assert "Supabase" in results
        assert "Neo4j" in results
        assert "GitHub" in results

        for name, result in results.items():
            assert "service" in result
            assert "status" in result
            assert result["status"] in ("connected", "failed")
