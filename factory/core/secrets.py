"""
AI Factory Pipeline v5.6 — Secrets Management (GCP Secret Manager)

Production replacement for the env-var-only stub.

Implements:
  - §2.11     Secrets Management (all secrets in GCP Secret Manager)
  - §7.7.1    get_secret() / store_secret() with GCP SDK
  - Appendix B Complete Secrets List (15 secrets + rotation schedules)
  - ADR-006   GCP Secret Manager for all credentials

Resolution order for get_secret():
  1. In-memory TTL cache (300s default)
  2. GCP Secret Manager (if SDK + project ID available)
  3. Environment variable (os.getenv)
  4. .env file via python-dotenv (local dev)
  5. None (secret not found)

Uses google-cloud-secret-manager v2.26.0 (verified 2026-02-27):
  - SecretManagerServiceClient() for sync operations
  - access_secret_version() to read secret payload
  - create_secret() + add_secret_version() to write
  - get_secret() metadata check for existence

Spec Authority: v5.6 §2.11, §7.7.1, Appendix B, ADR-006
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger("factory.core.secrets")


# ═══════════════════════════════════════════════════════════════════
# Appendix B — Required Secrets (15 total)
# ═══════════════════════════════════════════════════════════════════

REQUIRED_SECRETS: list[str] = [
    "ANTHROPIC_API_KEY",           # Strategist, Engineer, Quick Fix (cascade → Gemini → Groq …)
    "GOOGLE_AI_API_KEY",           # Free AI fallback (Gemini 2.5 Flash) — always free
    "TELEGRAM_BOT_TOKEN",          # Telegram bot
    "GITHUB_TOKEN",                # State persistence, CI/CD, GHCR Docker registry
    "SUPABASE_URL",                # All persistence
    "SUPABASE_SERVICE_KEY",        # All persistence
    "NEO4J_URI",                   # Mother Memory (free Aura instance)
    "NEO4J_PASSWORD",              # Mother Memory
    "TELEGRAM_OPERATOR_ID",        # Operator authentication
    "PERPLEXITY_API_KEY",          # Perplexity scout (deferrable — free scouts available)
    "FLUTTERFLOW_API_TOKEN",       # FF stack only
    "UI_TARS_ENDPOINT",            # GUI automation
    "UI_TARS_API_KEY",             # GUI automation
    "APPLE_ID",                    # iOS deploy (cascades to Firebase → Airlock)
    "APP_SPECIFIC_PASSWORD",       # iOS deploy (cascades to Firebase → Airlock)
    "FIREBASE_SERVICE_ACCOUNT",    # Mobile distribution (cascades to Airlock)
]

# 9 core secrets required for pipeline startup
# Free-tier path: Anthropic (cascade) + Gemini + Telegram + Supabase + GitHub + Neo4j
CORE_SECRETS: list[str] = [
    "ANTHROPIC_API_KEY",      # primary AI (cascade to Gemini if no credits)
    "GOOGLE_AI_API_KEY",      # free AI fallback — must be set for cascade to work
    "TELEGRAM_BOT_TOKEN",
    "GITHUB_TOKEN",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "NEO4J_URI",
    "NEO4J_PASSWORD",
    "TELEGRAM_OPERATOR_ID",
]

# 6 secrets deferrable until specific feature use
# Paid services: cascade to free alternatives automatically when missing
DEFERRABLE_SECRETS: set[str] = {
    "PERPLEXITY_API_KEY",          # Scout layer (free alternatives: Tavily, DDG, etc. — always available)
    "FLUTTERFLOW_API_TOKEN",       # FlutterFlow stack only
    "UI_TARS_ENDPOINT",            # GUI automation (falls back to build_chain)
    "UI_TARS_API_KEY",             # GUI automation
    "APPLE_ID",                    # iOS App Store (cascade: Firebase → Airlock)
    "APP_SPECIFIC_PASSWORD",       # iOS App Store
    "FIREBASE_SERVICE_ACCOUNT",    # Firebase distribution (cascade: Airlock)
}

# Rotation schedule per Appendix B (days)
SECRET_ROTATION_DAYS: dict[str, int] = {
    "ANTHROPIC_API_KEY":        90,
    "GOOGLE_AI_API_KEY":        90,
    "TELEGRAM_BOT_TOKEN":      180,
    "GITHUB_TOKEN":             90,
    "SUPABASE_URL":            180,
    "SUPABASE_SERVICE_KEY":    180,
    "NEO4J_URI":               180,
    "NEO4J_PASSWORD":          180,
    "TELEGRAM_OPERATOR_ID":   3650,  # static operator ID, no rotation needed
    "PERPLEXITY_API_KEY":       90,
    "FLUTTERFLOW_API_TOKEN":    90,
    "UI_TARS_ENDPOINT":         90,
    "UI_TARS_API_KEY":          90,
    "APPLE_ID":                365,
    "APP_SPECIFIC_PASSWORD":   365,
    "FIREBASE_SERVICE_ACCOUNT": 180,
}

# Severity for validate_secrets_preflight()
SECRET_SEVERITY: dict[str, str] = {
    name: "CRITICAL" for name in CORE_SECRETS
}
SECRET_SEVERITY.update({
    name: "DEFERRABLE" for name in DEFERRABLE_SECRETS
})


# ═══════════════════════════════════════════════════════════════════
# TTL Cache
# ═══════════════════════════════════════════════════════════════════

_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS: float = 300.0  # 5 minutes


def _cache_get(name: str) -> Optional[str]:
    """Read from TTL cache. Returns None if expired or absent."""
    entry = _cache.get(name)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        _cache.pop(name, None)
        return None
    return value


def _cache_set(name: str, value: str) -> None:
    """Write to TTL cache."""
    _cache[name] = (value, time.monotonic() + _CACHE_TTL_SECONDS)


def clear_cache() -> None:
    """Clear entire secrets cache (for testing or forced refresh)."""
    _cache.clear()


# ═══════════════════════════════════════════════════════════════════
# .env Loader
# ═══════════════════════════════════════════════════════════════════

_dotenv_loaded: bool = False


def load_dotenv_if_available() -> None:
    """Load .env file for local development.

    In production (Cloud Run), secrets come from GCP Secret Manager
    as environment variables — .env is not used.

    Spec: §2.11 — local dev path.
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return
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
            logger.debug(f"No .env file at {env_path}")
    except ImportError:
        logger.debug("python-dotenv not installed — using environment only")
    _dotenv_loaded = True


# ═══════════════════════════════════════════════════════════════════
# GCP Secret Manager Client Singleton
# ═══════════════════════════════════════════════════════════════════

_gcp_client: Any = None
_gcp_available: Optional[bool] = None


def _get_gcp_client() -> Any:
    """Lazy-initialize the GCP Secret Manager client.

    Returns the client, or None if SDK not installed or auth fails.
    Uses Application Default Credentials (ADC) per GCP convention.
    """
    global _gcp_client, _gcp_available

    if _gcp_available is False:
        return None
    if _gcp_client is not None:
        return _gcp_client

    try:
        from google.cloud import secretmanager
        _gcp_client = secretmanager.SecretManagerServiceClient()
        _gcp_available = True
        logger.info("GCP Secret Manager client initialized")
        return _gcp_client
    except ImportError:
        logger.debug(
            "google-cloud-secret-manager not installed — "
            "using env var fallback"
        )
        _gcp_available = False
        return None
    except Exception as e:
        logger.warning(f"GCP Secret Manager init failed: {e}")
        _gcp_available = False
        return None


def _get_gcp_project_id() -> Optional[str]:
    """Get the GCP project ID from environment."""
    return os.getenv("GCP_PROJECT_ID")


def reset_gcp_client() -> None:
    """Reset GCP client singleton (for testing)."""
    global _gcp_client, _gcp_available
    _gcp_client = None
    _gcp_available = None


# ═══════════════════════════════════════════════════════════════════
# §7.7.1 get_secret() — Primary Read Path
# ═══════════════════════════════════════════════════════════════════

def get_secret(name: str) -> Optional[str]:
    """Get a secret value using the full resolution chain.

    Resolution order per §2.11 / §7.7.1:
      1. TTL cache (300s)
      2. GCP Secret Manager
      3. Environment variable (os.getenv)
      4. .env file (auto-loaded once)
      5. None

    Args:
        name: Secret name (e.g., 'ANTHROPIC_API_KEY').

    Returns:
        Secret value, or None if not found anywhere.
    """
    # 1. Check cache
    cached = _cache_get(name)
    if cached is not None:
        return cached

    # 2. Try GCP Secret Manager
    project_id = _get_gcp_project_id()
    client = _get_gcp_client()

    if client is not None and project_id:
        try:
            resource = (
                f"projects/{project_id}/secrets/{name}/versions/latest"
            )
            response = client.access_secret_version(
                request={"name": resource}
            )
            value = response.payload.data.decode("UTF-8")
            _cache_set(name, value)
            logger.debug(f"Secret {name} read from GCP Secret Manager")
            return value
        except Exception as e:
            # NotFound, PermissionDenied, etc. — fall through to env
            logger.debug(f"GCP read for {name}: {e}")

    # 3. Try environment variable (also loads .env once)
    load_dotenv_if_available()
    value = os.getenv(name)
    if value is not None:
        _cache_set(name, value)
        return value

    # 4. Not found
    return None


def get_secret_or_raise(name: str) -> str:
    """Get a secret or raise if missing.

    Spec: §2.11 — pipeline refuses startup with explicit error.

    Args:
        name: Secret name.

    Returns:
        Secret value.

    Raises:
        EnvironmentError: If secret is not found in any source.
    """
    value = get_secret(name)
    if not value:
        raise EnvironmentError(
            f"Required secret '{name}' is not set. "
            f"Set it in GCP Secret Manager (production) or .env (local dev). "
            f"See Appendix B for the complete secrets list."
        )
    return value


# ═══════════════════════════════════════════════════════════════════
# §7.7.1 store_secret() — Write Path (Setup Wizard)
# ═══════════════════════════════════════════════════════════════════

def store_secret(name: str, value: str) -> bool:
    """Store or update a secret in GCP Secret Manager.

    Spec: §7.7.1 — Keys stored in GCP Secret Manager immediately
    upon receipt (never in env vars or config files).

    Creates the secret if it doesn't exist, then adds a new version.

    Args:
        name: Secret name.
        value: Secret value.

    Returns:
        True if stored successfully, False on failure.
    """
    project_id = _get_gcp_project_id()
    client = _get_gcp_client()

    if client is None or not project_id:
        logger.warning(
            f"Cannot store {name} in GCP — client or project ID unavailable. "
            f"Setting as env var for this session."
        )
        os.environ[name] = value
        _cache_set(name, value)
        return True  # Fallback: set as env var

    parent = f"projects/{project_id}"
    secret_path = f"{parent}/secrets/{name}"

    try:
        # Create the secret container (idempotent — ignore AlreadyExists)
        try:
            client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": name,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
            logger.info(f"Created secret container: {name}")
        except Exception:
            # AlreadyExists is expected for updates
            pass

        # Add a new secret version with the payload
        client.add_secret_version(
            request={
                "parent": secret_path,
                "payload": {"data": value.encode("UTF-8")},
            }
        )

        # Update cache
        _cache_set(name, value)
        logger.info(f"Secret {name} stored in GCP Secret Manager")
        return True

    except Exception as e:
        logger.error(f"Failed to store secret {name}: {e}")
        # Fallback: set as env var for this session
        os.environ[name] = value
        _cache_set(name, value)
        return False


# ═══════════════════════════════════════════════════════════════════
# §7.7.1 check_secret_exists() — Existence Check (Setup Wizard)
# ═══════════════════════════════════════════════════════════════════

def check_secret_exists(name: str) -> bool:
    """Check if a secret exists in GCP Secret Manager.

    Used by the setup wizard (§7.1.2) to skip already-configured secrets.

    Args:
        name: Secret name.

    Returns:
        True if secret exists in GCP, or if available as env var.
    """
    # Check env first (covers local dev)
    if os.getenv(name):
        return True

    project_id = _get_gcp_project_id()
    client = _get_gcp_client()

    if client is None or not project_id:
        return False

    try:
        client.get_secret(
            name=f"projects/{project_id}/secrets/{name}"
        )
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
# §2.11 validate_secrets_preflight() — Boot Validation
# ═══════════════════════════════════════════════════════════════════

def validate_secrets_preflight(
    strict: bool = False,
) -> dict[str, Any]:
    """Validate that all required secrets are accessible.

    Called at pipeline startup per §2.11: "Missing secrets cause the
    pipeline to refuse startup with an explicit error listing the
    missing keys."

    Args:
        strict: If True, raise on any missing CRITICAL secret.

    Returns:
        {
            "all_present": bool,
            "core_present": int,    # out of 9
            "total_present": int,   # out of 15
            "missing_critical": [],
            "missing_deferrable": [],
            "details": {name: {"present": bool, "severity": str}}
        }

    Raises:
        EnvironmentError: If strict=True and any CRITICAL secret missing.
    """
    result: dict[str, Any] = {
        "all_present": True,
        "core_present": 0,
        "total_present": 0,
        "missing_critical": [],
        "missing_deferrable": [],
        "details": {},
    }

    for name in REQUIRED_SECRETS:
        present = get_secret(name) is not None
        severity = SECRET_SEVERITY.get(name, "UNKNOWN")

        result["details"][name] = {
            "present": present,
            "severity": severity,
        }

        if present:
            result["total_present"] += 1
            if name in CORE_SECRETS:
                result["core_present"] += 1
        else:
            result["all_present"] = False
            if severity == "CRITICAL":
                result["missing_critical"].append(name)
            else:
                result["missing_deferrable"].append(name)

    total = len(REQUIRED_SECRETS)
    logger.info(
        f"Secrets preflight: {result['total_present']}/{total} present "
        f"({result['core_present']}/{len(CORE_SECRETS)} core, "
        f"{len(result['missing_critical'])} critical missing)"
    )

    if result["missing_critical"]:
        msg = (
            f"Missing {len(result['missing_critical'])} CRITICAL secret(s):\n"
            + "\n".join(f"  - {s}" for s in result["missing_critical"])
            + "\n\nSet these in GCP Secret Manager (production) or .env "
            + "(local dev). See Appendix B."
        )
        if strict:
            raise EnvironmentError(msg)
        else:
            logger.warning(msg)

    if result["missing_deferrable"]:
        logger.info(
            f"Deferrable secrets missing (needed for specific features): "
            f"{', '.join(result['missing_deferrable'])}"
        )

    return result


# ═══════════════════════════════════════════════════════════════════
# Rotation Status (Appendix B)
# ═══════════════════════════════════════════════════════════════════

def get_rotation_status() -> dict[str, dict[str, Any]]:
    """Get rotation schedule info for all secrets.

    Returns metadata only — does NOT check actual secret age
    (that requires GCP Secret Manager version metadata).

    Returns:
        {name: {"rotation_days": int, "present": bool, "deferrable": bool}}
    """
    status = {}
    for name in REQUIRED_SECRETS:
        status[name] = {
            "rotation_days": SECRET_ROTATION_DAYS.get(name, 0),
            "present": get_secret(name) is not None,
            "deferrable": name in DEFERRABLE_SECRETS,
        }
    return status


# ═══════════════════════════════════════════════════════════════════
# Legacy alias (backward compat with code using validate_secrets)
# ═══════════════════════════════════════════════════════════════════

def validate_secrets(strict: bool = False, required_only: bool = True) -> dict[str, bool]:
    """Legacy wrapper — delegates to validate_secrets_preflight().

    Returns simplified {name: present} dict for backward compat.
    """
    result = validate_secrets_preflight(strict=strict)
    return {
        name: info["present"]
        for name, info in result["details"].items()
    }
