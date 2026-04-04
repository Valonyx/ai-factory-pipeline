"""
AI Factory Pipeline v5.6 — App Store Upload Attempts

Implements:
  - §7.6.0a Automation vs Manual Boundaries
  - FIX-21 iOS 5-step submission protocol
  - Google Play Developer API upload
  - Automatic Airlock fallback on failure

The pipeline ATTEMPTS programmatic upload. If it fails,
the Airlock delivers the binary to the operator via Telegram.

Spec Authority: v5.6 §7.6.0a, FIX-21
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from factory.core.state import PipelineState
from factory.delivery.airlock import airlock_deliver

logger = logging.getLogger("factory.delivery.app_store")


# ═══════════════════════════════════════════════════════════════════
# §7.6.0a Upload Dispatcher
# ═══════════════════════════════════════════════════════════════════


async def attempt_store_upload(
    state: PipelineState,
    platform: str,
    binary_path: str,
) -> dict:
    """Attempt programmatic store upload; fall back to Airlock.

    Spec: §7.6.0a

    Returns: {"success": bool, "method": str, ...}
    """
    try:
        if platform == "ios":
            result = await _upload_ios(state, binary_path)
        elif platform == "android":
            result = await _upload_android(state, binary_path)
        else:
            return {"success": False, "error": f"Unknown platform: {platform}"}

        if result.get("success"):
            logger.info(
                f"[{state.project_id}] Store upload success: {platform}"
            )
            return result

        # API upload failed → Airlock fallback
        logger.warning(
            f"[{state.project_id}] Store upload failed: "
            f"{result.get('error', 'unknown')} → Airlock"
        )
        airlock_result = await airlock_deliver(
            state, platform, binary_path,
            error=result.get("error", "API upload failed"),
        )
        return {
            "success": False,
            "method": "airlock",
            "api_error": result.get("error"),
            "airlock": airlock_result,
        }

    except Exception as e:
        logger.error(
            f"[{state.project_id}] Store upload exception: {e} → Airlock"
        )
        airlock_result = await airlock_deliver(
            state, platform, binary_path, error=str(e),
        )
        return {
            "success": False,
            "method": "airlock",
            "api_error": str(e),
            "airlock": airlock_result,
        }


# ═══════════════════════════════════════════════════════════════════
# FIX-21 iOS 5-Step Submission Protocol
# ═══════════════════════════════════════════════════════════════════


async def _upload_ios(
    state: PipelineState,
    binary_path: str,
) -> dict:
    """iOS App Store Connect upload via Transporter CLI or API.

    Spec: FIX-21 — 5-step submission protocol

    Steps:
      1. Validate App Store Connect credentials
      2. Check binary (.ipa) exists and is signed
      3. Upload via Transporter CLI (xcrun altool)
      4. Wait for processing
      5. Verify upload in App Store Connect

    In stub mode: simulates upload.
    """
    # Step 1: Validate credentials (read fresh — not at import time)
    api_key = os.getenv("APP_STORE_API_KEY", "")
    issuer_id = os.getenv("APP_STORE_ISSUER_ID", "")

    if not api_key or not issuer_id:
        return {
            "success": False,
            "error": "Missing APP_STORE_API_KEY or APP_STORE_ISSUER_ID",
            "step": 1,
        }

    # Step 2: Validate binary
    if not os.path.exists(binary_path):
        return {
            "success": False,
            "error": f"Binary not found: {binary_path}",
            "step": 2,
        }

    if not binary_path.endswith(".ipa"):
        return {
            "success": False,
            "error": f"Expected .ipa, got: {binary_path}",
            "step": 2,
        }

    # Steps 3-5: Stub (production uses Transporter CLI)
    logger.info(
        f"[{state.project_id}] iOS upload stub: {binary_path}"
    )

    return {
        "success": True,
        "method": "transporter_cli",
        "platform": "ios",
        "binary": binary_path,
        "stub": True,
    }


# ═══════════════════════════════════════════════════════════════════
# Google Play Developer API Upload
# ═══════════════════════════════════════════════════════════════════


async def _upload_android(
    state: PipelineState,
    binary_path: str,
) -> dict:
    """Google Play Console upload via Developer API.

    Spec: §7.6.0a

    In stub mode: simulates upload.
    """
    # Validate credentials (read fresh — not at import time)
    service_account = os.getenv("PLAY_CONSOLE_SERVICE_ACCOUNT", "")

    if not service_account:
        return {
            "success": False,
            "error": "Missing PLAY_CONSOLE_SERVICE_ACCOUNT",
        }

    # Validate binary
    if not os.path.exists(binary_path):
        return {
            "success": False,
            "error": f"Binary not found: {binary_path}",
        }

    if not binary_path.endswith(".aab"):
        return {
            "success": False,
            "error": f"Expected .aab, got: {binary_path}",
        }

    # Stub: simulate upload
    logger.info(
        f"[{state.project_id}] Android upload stub: {binary_path}"
    )

    return {
        "success": True,
        "method": "play_developer_api",
        "platform": "android",
        "binary": binary_path,
        "stub": True,
    }


# ═══════════════════════════════════════════════════════════════════
# Upload Status Check
# ═══════════════════════════════════════════════════════════════════


async def check_upload_status(
    platform: str,
    upload_id: str,
) -> dict:
    """Check status of a previous upload attempt.

    In production: queries App Store Connect / Play Console API.
    """
    return {
        "platform": platform,
        "upload_id": upload_id,
        "status": "processing",
        "stub": True,
    }
