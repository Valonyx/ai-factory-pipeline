"""
AI Factory Pipeline v5.8 — Consolidated Configuration

Implements:
  - §8.9 Environment Variable Reference (all env vars)
  - §2.6 Model configuration (Strategist/Engineer/QuickFix/Scout)
  - §2.14 Budget Governor config
  - §7.5 File delivery config
  - §7.6 Compliance config

Single source of truth. All modules import from here.

Spec Authority: v5.8 §8.9, §2.6, §2.14
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
# Pipeline Identity
# ═══════════════════════════════════════════════════════════════════

PIPELINE_VERSION = "5.8"
PIPELINE_FULL_VERSION = "5.8.0"


# ═══════════════════════════════════════════════════════════════════
# §7.7.1 GCP / Infrastructure
# ═══════════════════════════════════════════════════════════════════

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")


# ═══════════════════════════════════════════════════════════════════
# §2.6 AI Model Configuration
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ModelConfig:
    """AI model identifiers per §2.6."""

    # Anthropic models
    strategist: str = os.getenv(
        "STRATEGIST_MODEL_OVERRIDE",
        os.getenv("STRATEGIST_MODEL", "claude-opus-4-6"),
    )
    engineer: str = os.getenv(
        "ENGINEER_MODEL_OVERRIDE",
        os.getenv("ENGINEER_MODEL", "claude-sonnet-4-5-20250929"),
    )
    quick_fix: str = os.getenv(
        "QUICKFIX_MODEL_OVERRIDE",
        os.getenv("QUICKFIX_MODEL", "claude-haiku-4-5-20251001"),
    )
    gui_supervisor: str = os.getenv(
        "GUI_SUPERVISOR_MODEL", "claude-haiku-4-5-20251001",
    )

    # Perplexity models (Scout)
    scout: str = os.getenv("SCOUT_MODEL", "sonar-pro")
    scout_reasoning: str = os.getenv(
        "SCOUT_REASONING_MODEL", "sonar-reasoning-pro",
    )
    scout_context_tier: str = os.getenv(
        "SCOUT_MAX_CONTEXT_TIER", "medium",
    )   # small|medium|large [FIX-19]


MODELS = ModelConfig()


# ═══════════════════════════════════════════════════════════════════
# §2.14 Budget Governor
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BudgetConfig:
    """Budget thresholds and limits per §2.14."""

    enabled: bool = os.getenv(
        "BUDGET_GOVERNOR_ENABLED", "true",
    ).lower() == "true"

    # Per-project alerts (USD)
    project_alert_first: float = 8.0
    project_alert_second: float = 15.0

    # Monthly budget
    monthly_budget_usd: float = float(
        os.getenv("MONTHLY_BUDGET_USD", "300")
    )
    monthly_alert_pct: float = 0.85   # 85% alert

    # Graduated tiers (% of monthly budget)
    green_pct: float = 0.0
    amber_pct: float = 80.0
    red_pct: float = 95.0
    black_pct: float = 100.0

    # Circuit breaker per-phase limit
    circuit_breaker_usd: float = 2.0

    # Per-project cap (USD)
    project_cap_usd: float = 25.0

    # SAR conversion rate
    sar_rate: float = 3.75


BUDGET = BudgetConfig()


# ═══════════════════════════════════════════════════════════════════
# §7.5 File Delivery
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DeliveryConfig:
    """File delivery thresholds per §7.5 [C3]."""

    telegram_file_limit_mb: int = int(
        os.getenv("TELEGRAM_FILE_LIMIT_MB", "50"),
    )   # [V12] Verified: 50MB for bots
    soft_file_limit_mb: int = int(
        os.getenv("SOFT_FILE_LIMIT_MB", "200"),
    )
    artifact_ttl_hours: int = int(
        os.getenv("ARTIFACT_TTL_HOURS", "72"),
    )
    storage_bucket: str = "build-artifacts"


DELIVERY = DeliveryConfig()


# ═══════════════════════════════════════════════════════════════════
# §7.6 Compliance
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ComplianceConfig:
    """Store compliance settings per §7.6."""

    strict_store_compliance: bool = os.getenv(
        "STRICT_STORE_COMPLIANCE", "false",
    ).lower() == "true"

    confidence_threshold: float = float(
        os.getenv("COMPLIANCE_CONFIDENCE_THRESHOLD", "0.7"),
    )

    # Deploy window (AST = UTC+3)
    deploy_window_start_hour: int = int(
        os.getenv("DEPLOY_WINDOW_START_HOUR", "6"),
    )
    deploy_window_end_hour: int = int(
        os.getenv("DEPLOY_WINDOW_END_HOUR", "23"),
    )

    @property
    def deploy_window_start(self) -> int:
        return self.deploy_window_start_hour

    @property
    def deploy_window_end(self) -> int:
        return self.deploy_window_end_hour


COMPLIANCE = ComplianceConfig()


# ═══════════════════════════════════════════════════════════════════
# §6.7 Vector Backend
# ═══════════════════════════════════════════════════════════════════

VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "pgvector")


# ═══════════════════════════════════════════════════════════════════
# §4.7 App Store Credentials (FIX-21)
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AppStoreConfig:
    """App store credentials per §4.7 [FIX-21]."""

    # iOS
    api_key: str = os.getenv("APP_STORE_API_KEY", "")
    issuer_id: str = os.getenv("APP_STORE_ISSUER_ID", "")

    # Android
    play_service_account: str = os.getenv(
        "PLAY_CONSOLE_SERVICE_ACCOUNT", "",
    )

    @property
    def ios_configured(self) -> bool:
        return bool(self.api_key and self.issuer_id)

    @property
    def android_configured(self) -> bool:
        return bool(self.play_service_account)


APP_STORE = AppStoreConfig()


# ═══════════════════════════════════════════════════════════════════
# §7.7.1 Required Secrets
# ═══════════════════════════════════════════════════════════════════

REQUIRED_SECRETS = [
    "ANTHROPIC_API_KEY",
    "PERPLEXITY_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "NEO4J_URI",
    "NEO4J_PASSWORD",
    "GITHUB_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "GCP_PROJECT_ID",
]

CONDITIONAL_SECRETS = [
    "APPLE_API_KEY_ID",
    "APPLE_API_ISSUER_ID",
    "FLUTTERFLOW_API_TOKEN",
    "PLAY_CONSOLE_SERVICE_ACCOUNT",
]


# ═══════════════════════════════════════════════════════════════════
# War Room
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class WarRoomConfig:
    """War Room limits per §2.2.4."""

    max_l1_attempts: int = 1
    max_l2_attempts: int = 1
    max_l3_attempts: int = 1
    max_retry_cycles: int = 3
    gui_failure_threshold: int = 3

    # Context char limits per level
    l1_file_context_chars: int = 4000
    l2_file_context_chars: int = 8000
    l3_file_context_chars: int = 8000


WAR_ROOM = WarRoomConfig()


# ═══════════════════════════════════════════════════════════════════
# Data Residency
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DataResidencyConfig:
    """KSA data residency per §2.8 PDPL."""

    primary_region: str = "me-central1"   # GCP Dammam
    allowed_regions: tuple = (
        "me-central1",    # GCP Dammam
        "me-central2",    # GCP Doha
        "me-south1",      # GCP (fallback)
        "me-west1",       # GCP Milan (fallback)
    )


DATA_RESIDENCY = DataResidencyConfig()


# Convenience aggregate for modules that import a single config object
PIPELINE_CONFIG = {
    "version": PIPELINE_FULL_VERSION,
    "models": MODELS,
    "budget": BUDGET,
    "delivery": DELIVERY,
    "data_residency": DATA_RESIDENCY,
}


# ═══════════════════════════════════════════════════════════════════
# Utility: Validate Required Config
# ═══════════════════════════════════════════════════════════════════


def validate_required_config() -> list[str]:
    """Check required configuration. Returns list of missing items."""
    missing = []

    if not GCP_PROJECT_ID:
        missing.append("GCP_PROJECT_ID")

    # Check model strings are non-empty
    if not MODELS.strategist:
        missing.append("STRATEGIST_MODEL")
    if not MODELS.engineer:
        missing.append("ENGINEER_MODEL")
    if not MODELS.quick_fix:
        missing.append("QUICKFIX_MODEL")

    return missing


def get_config_summary() -> dict:
    """Return config summary for diagnostics."""
    return {
        "version": PIPELINE_FULL_VERSION,
        "gcp_project": GCP_PROJECT_ID[:8] + "..." if GCP_PROJECT_ID else "(not set)",
        "models": {
            "strategist": MODELS.strategist,
            "engineer": MODELS.engineer,
            "quick_fix": MODELS.quick_fix,
            "scout": MODELS.scout,
        },
        "budget": {
            "enabled": BUDGET.enabled,
            "monthly_usd": BUDGET.monthly_budget_usd,
        },
        "compliance": {
            "strict": COMPLIANCE.strict_store_compliance,
            "confidence_threshold": COMPLIANCE.confidence_threshold,
        },
        "delivery": {
            "telegram_limit_mb": DELIVERY.telegram_file_limit_mb,
            "artifact_ttl_hours": DELIVERY.artifact_ttl_hours,
        },
        "data_residency": DATA_RESIDENCY.primary_region,
        "vector_backend": VECTOR_BACKEND,
        "app_store": {
            "ios_configured": APP_STORE.ios_configured,
            "android_configured": APP_STORE.android_configured,
        },
    }