"""
AI Factory Pipeline v5.6 — Secrets Management (GCP Secret Manager)

Implements:
  - §2.11 Secrets Management
  - Appendix B: Complete Secrets List (15 secrets)
  - ADR-006: GCP Secret Manager for all credentials

For local development, secrets are loaded from .env file via python-dotenv.
For production (Cloud Run), secrets are injected as environment variables
by GCP Secret Manager.

Spec Authority: v5.6 §2.11, Appendix B
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.core.secrets")


# ═══════════════════════════════════════════════════════════════════
# Appendix B — Required Secrets (15 total)
# ═══════════════════════════════════════════════════════════════════

REQUIRED_SECRETS: list[str] = [
    "ANTHROPIC_API_KEY",           # Strategist, Engineer, Quick Fix — 90d rotation
    "PERPLEXITY_API_KEY",          # Scout — 90d rotation
    "TELEGRAM_BOT_TOKEN",          # Telegram bot — 180d rotation
    "GITHUB_TOKEN",                # State persistence, CI/CD — 90d rotation
    "SUPABASE_URL",                # All persistence — 180d rotation
    "SUPABASE_SERVICE_KEY",        # All persistence — 180d rotation
    "NEO4J_URI",                   # Mother Memory — 180d rotation
    "NEO4J_PASSWORD",              # Mother Memory — 180d rotation
    "FLUTTERFLOW_API_TOKEN",       # FF stack only — 90d rotation
    "UI_TARS_ENDPOINT",            # GUI automation — N/A
    "UI_TARS_API_KEY",             # GUI automation — 90d rotation
    "APPLE_ID",                    # iOS deploy — 365d rotation
    "APP_SPECIFIC_PASSWORD",       # iOS deploy — 365d rotation
    "FIREBASE_SERVICE_ACCOUNT",    # Web deploy — 180d rotation
    "GCP_PROJECT_ID",              # Cloud Run — N/A (not a secret per se)
]

# Secrets that can be deferred (not required for initial dry-run)
DEFERRABLE_SECRETS: set[str] = {
    "FLUTTERFLOW_API_TOKEN",
    "UI_TARS_ENDPOINT",
    "UI_TARS_API_KEY",
    "APPLE_ID",
    "APP_SPECIFIC_PASSWORD",
    "FIREBASE_SERVICE_ACCOUNT",
}

# Rotation schedule per Appendix B
SECRET_ROTATION_DAYS: dict[str, int] = {
    "ANTHROPIC_API_KEY":        90,
    "PERPLEXITY_API_KEY":       90,
    "TELEGRAM_BOT_TOKEN":      180,
    "GITHUB_TOKEN":             90,
    "SUPABASE_URL":            180,
    "SUPABASE_SERVICE_KEY":    180,
    "NEO4J_URI":               180,
    "NEO4J_PASSWORD":          180,
    "FLUTTERFLOW_API_TOKEN":    90,
    "UI_TARS_API_KEY":          90,
    "APPLE_ID":                365,
    "APP_SPECIFIC_PASSWORD":   365,
    "FIREBASE_SERVICE_ACCOUNT": 180,
}


def load_dotenv_if_available() -> None:
    """Load .env file for local development.

    In production (Cloud Run), secrets come from GCP Secret Manager
    as environment variables — .env is not used.
    """
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            ".env",
        )
        if os.path.exists(env_path):
            load_dotenv(env_path)
            logger.info(f"Loaded .env from {env_path}")
        else:
            logger.debug(f"No .env file at {env_path} — using environment")
    except ImportError:
        logger.debug("python-dotenv not installed — using environment only")


def get_secret(name: str) -> Optional[str]:
    """Get a secret value from environment.

    Spec: §2.11
    In production, GCP Secret Manager injects these as env vars.
    Locally, they come from .env.

    Args:
        name: Secret name (e.g., 'ANTHROPIC_API_KEY')

    Returns:
        Secret value, or None if not set.
    """
    return os.getenv(name)


def get_secret_or_raise(name: str) -> str:
    """Get a secret or raise if missing.

    Args:
        name: Secret name.

    Returns:
        Secret value.

    Raises:
        EnvironmentError: If secret is not set.
    """
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Required secret '{name}' is not set. "
            f"Set it in .env (local) or GCP Secret Manager (production)."
        )
    return value


def validate_secrets(
    strict: bool = False,
    required_only: bool = True,
) -> dict[str, bool]:
    """Validate that all required secrets are present.

    Spec: §2.11
    Missing secrets cause startup to fail with explicit error listing
    the missing keys.

    Args:
        strict: If True, raise on any missing secret.
                If False, log warnings for deferrable secrets.
        required_only: If True, only check non-deferrable secrets.

    Returns:
        Dict mapping secret name → present (True/False).

    Raises:
        EnvironmentError: If strict=True and any required secret missing.
    """
    results: dict[str, bool] = {}
    missing: list[str] = []

    for secret_name in REQUIRED_SECRETS:
        present = os.getenv(secret_name) is not None
        results[secret_name] = present

        if not present:
            if secret_name in DEFERRABLE_SECRETS:
                if not required_only:
                    logger.warning(
                        f"Deferrable secret missing: {secret_name} "
                        f"(needed for specific features)"
                    )
            else:
                missing.append(secret_name)

    if missing:
        msg = (
            f"Missing {len(missing)} required secret(s):\n"
            + "\n".join(f"  - {s}" for s in missing)
            + "\n\nSet these in .env (local) or GCP Secret Manager (production)."
        )
        if strict:
            raise EnvironmentError(msg)
        else:
            logger.warning(msg)

    found = sum(1 for v in results.values() if v)
    logger.info(
        f"Secrets validation: {found}/{len(REQUIRED_SECRETS)} present "
        f"({len(missing)} required missing)"
    )
    return results


async def fetch_from_gcp_secret_manager(
    secret_name: str,
    project_id: Optional[str] = None,
) -> Optional[str]:
    """Fetch a secret from GCP Secret Manager.

    Spec: §2.11, ADR-006
    Used in production. Falls back to env var if GCP is unavailable.

    Args:
        secret_name: Name of the secret in GCP.
        project_id: GCP project ID (defaults to GCP_PROJECT_ID env var).

    Returns:
        Secret value, or None if not found.
    """
    if project_id is None:
        project_id = os.getenv("GCP_PROJECT_ID")

    if not project_id:
        logger.debug("GCP_PROJECT_ID not set — using env var fallback")
        return os.getenv(secret_name)

    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except ImportError:
        logger.debug("google-cloud-secret-manager not installed — using env var")
        return os.getenv(secret_name)
    except Exception as e:
        logger.warning(f"GCP Secret Manager error for {secret_name}: {e}")
        return os.getenv(secret_name)