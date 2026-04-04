"""
AI Factory Pipeline v5.6 — GCP Secret Manager Bootstrap

Implements:
  - §7.7.1 Required secrets setup
  - Interactive prompts for each secret
  - Validates connectivity to GCP
  - Idempotent — skips existing secrets

Run: python -m scripts.setup_secrets

Spec Authority: v5.6 §7.7.1
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from getpass import getpass

from factory.config import REQUIRED_SECRETS, CONDITIONAL_SECRETS, GCP_PROJECT_ID

logger = logging.getLogger("factory.setup.secrets")


async def check_secret_exists(name: str, gcp_project: str) -> bool:
    """Check if a secret already exists in GCP Secret Manager."""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceAsyncClient()
        try:
            await client.get_secret(
                name=f"projects/{gcp_project}/secrets/{name}",
            )
            return True
        except Exception:
            return False
    except ImportError:
        logger.warning("google-cloud-secret-manager not installed")
        return False


async def store_secret(name: str, value: str, gcp_project: str) -> bool:
    """Store secret in GCP Secret Manager."""
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceAsyncClient()
        parent = f"projects/{gcp_project}"

        try:
            await client.create_secret(
                parent=parent,
                secret_id=name,
                secret={"replication": {"automatic": {}}},
            )
        except Exception:
            pass  # Already exists

        await client.add_secret_version(
            parent=f"{parent}/secrets/{name}",
            payload={"data": value.encode("utf-8")},
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store {name}: {e}")
        return False


async def setup_secrets_interactive():
    """Interactive setup of all required secrets."""
    gcp_project = GCP_PROJECT_ID or input("GCP Project ID: ").strip()

    if not gcp_project:
        print("❌ GCP_PROJECT_ID is required")
        sys.exit(1)

    print(f"\nProject: {gcp_project}")
    print(f"Required secrets: {len(REQUIRED_SECRETS)}")
    print(f"Conditional secrets: {len(CONDITIONAL_SECRETS)}")
    print()

    stored = 0
    skipped = 0
    errors = 0

    # Required secrets
    print("═══ Required Secrets ═══")
    for secret_name in REQUIRED_SECRETS:
        exists = await check_secret_exists(secret_name, gcp_project)
        if exists:
            print(f"  ✅ {secret_name} (exists)")
            skipped += 1
            continue

        value = getpass(f"  Enter {secret_name}: ").strip()
        if not value:
            print(f"  ⚠️  Skipped {secret_name}")
            continue

        if await store_secret(secret_name, value, gcp_project):
            print(f"  ✅ {secret_name} stored")
            stored += 1
        else:
            print(f"  ❌ {secret_name} failed")
            errors += 1

    # Conditional secrets
    print("\n═══ Conditional Secrets (optional) ═══")
    for secret_name in CONDITIONAL_SECRETS:
        exists = await check_secret_exists(secret_name, gcp_project)
        if exists:
            print(f"  ✅ {secret_name} (exists)")
            skipped += 1
            continue

        value = getpass(
            f"  Enter {secret_name} (or Enter to skip): ",
        ).strip()
        if not value:
            print(f"  ⏭️  Skipped {secret_name}")
            continue

        if await store_secret(secret_name, value, gcp_project):
            print(f"  ✅ {secret_name} stored")
            stored += 1
        else:
            print(f"  ❌ {secret_name} failed")
            errors += 1

    print(f"\n{'═' * 40}")
    print(f"Stored: {stored}")
    print(f"Skipped (already exist): {skipped}")
    print(f"Errors: {errors}")


async def validate_secrets(gcp_project: str = None) -> dict:
    """Validate that all required secrets exist."""
    gcp_project = gcp_project or GCP_PROJECT_ID
    result = {"present": [], "missing": [], "project": gcp_project}

    for name in REQUIRED_SECRETS:
        if await check_secret_exists(name, gcp_project):
            result["present"].append(name)
        else:
            result["missing"].append(name)

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("AI Factory Pipeline v5.6 — GCP Secret Manager Setup")
    print("=" * 50)

    if "--validate" in sys.argv:
        result = asyncio.run(validate_secrets())
        print(f"\nPresent: {len(result['present'])}")
        print(f"Missing: {len(result['missing'])}")
        if result["missing"]:
            print(f"  Missing: {', '.join(result['missing'])}")
    else:
        asyncio.run(setup_secrets_interactive())