"""
AI Factory Pipeline v5.8 — App Store Airlock (Binary Delivery Fallback)

Implements:
  - §7.6.2 airlock_deliver() — Telegram binary delivery
  - iOS / Android upload instructions
  - Policy vs access disclaimer
  - FIX-22 Airlock scope clarification

The Airlock is the fallback delivery path when programmatic
App Store / Play Store uploads fail. It packages the compiled
binary and delivers it to the operator via Telegram for manual
submission.

Spec Authority: v5.8 §7.6
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from factory.core.state import PipelineState
from factory.telegram.notifications import send_telegram_message
from factory.delivery.file_delivery import (
    send_telegram_file,
    upload_to_temp_storage,
    TELEGRAM_FILE_LIMIT_MB,
)

logger = logging.getLogger("factory.delivery.airlock")


# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

PLATFORM_EXTENSIONS = {
    "ios": ".ipa",
    "android": ".aab",
}

AIRLOCK_DISCLAIMER = (
    "⚠️ IMPORTANT: Manual upload does not bypass Apple/Google review. "
    "Your app may still be rejected for policy violations. "
    "Review compliance warnings from S1 Legal Gate before submitting."
)

IOS_UPLOAD_STEPS = (
    "📋 iOS Upload Steps:\n"
    "1. Open Transporter app (macOS)\n"
    "2. Drag the .ipa file into Transporter\n"
    "3. Click 'Deliver'\n"
    "4. Go to App Store Connect > TestFlight to verify"
)

ANDROID_UPLOAD_STEPS = (
    "📋 Android Upload Steps:\n"
    "1. Open Play Console > your app\n"
    "2. Go to Release > Production (or Testing)\n"
    "3. Create new release\n"
    "4. Upload the .aab file\n"
    "5. Review and roll out"
)


# ═══════════════════════════════════════════════════════════════════
# §7.6.2 Airlock Delivery
# ═══════════════════════════════════════════════════════════════════


async def airlock_deliver(
    state: PipelineState,
    platform: str,
    binary_path: str,
    error: str,
) -> dict:
    """Deliver binary to operator when API upload fails.

    Spec: §7.6.2

    When API upload fails, deliver binary directly to operator
    via Telegram. Operator drag-and-drops to App Store Connect /
    Play Console.
    """
    ext = PLATFORM_EXTENSIONS.get(platform, ".bin")
    store_name = (
        "App Store Connect" if platform == "ios"
        else "Play Console"
    )

    if not os.path.exists(binary_path):
        logger.error(f"Airlock: binary not found: {binary_path}")
        await send_telegram_message(
            state.operator_id,
            f"🔒 {platform.upper()} Airlock\n\n"
            f"API upload failed: {error[:200]}\n\n"
            f"❌ Binary file not found at expected path.\n"
            f"This may indicate a build failure. Check /warroom.",
        )
        return {"method": "error", "error": "binary_not_found"}

    size_mb = os.path.getsize(binary_path) / (1024 * 1024)

    # ── Large binary: Supabase Storage ──
    if size_mb > TELEGRAM_FILE_LIMIT_MB:
        upload_url = await upload_to_temp_storage(
            binary_path, state.project_id,
        )
        await send_telegram_message(
            state.operator_id,
            f"📦 {platform.upper()} binary too large for Telegram "
            f"({size_mb:.1f} MB)\n"
            f"Download: {upload_url}\n"
            f"Link expires in 24 hours.\n\n"
            f"Upload to {store_name} manually.",
        )
        await _send_upload_instructions(state.operator_id, platform)
        await send_telegram_message(state.operator_id, AIRLOCK_DISCLAIMER)

        logger.info(
            f"[{state.project_id}] Airlock: {platform} via temp storage "
            f"({size_mb:.1f} MB)"
        )
        return {"method": "temp_storage", "url": upload_url}

    # ── Standard binary: Telegram direct ──
    await send_telegram_message(
        state.operator_id,
        f"🔒 {platform.upper()} Airlock\n\n"
        f"API upload failed: {error[:200]}\n\n"
        f"Sending you the {ext} file. Upload manually to "
        f"{store_name}.",
    )

    await send_telegram_file(
        state.operator_id, binary_path, state.project_id,
    )

    await _send_upload_instructions(state.operator_id, platform)
    await send_telegram_message(state.operator_id, AIRLOCK_DISCLAIMER)

    logger.info(
        f"[{state.project_id}] Airlock: {platform} via Telegram "
        f"({size_mb:.1f} MB)"
    )
    return {
        "method": "telegram",
        "size_mb": round(size_mb, 1),
    }


async def _send_upload_instructions(
    operator_id: str, platform: str,
) -> None:
    """Send platform-specific upload instructions."""
    if platform == "ios":
        await send_telegram_message(operator_id, IOS_UPLOAD_STEPS)
    else:
        await send_telegram_message(operator_id, ANDROID_UPLOAD_STEPS)


# ═══════════════════════════════════════════════════════════════════
# Airlock Status
# ═══════════════════════════════════════════════════════════════════


def get_airlock_summary(state: PipelineState) -> dict:
    """Get airlock delivery summary from project metadata."""
    deliveries = state.project_metadata.get("airlock_deliveries", [])
    return {
        "total_deliveries": len(deliveries),
        "platforms": list(set(d.get("platform", "") for d in deliveries)),
        "methods": list(set(d.get("method", "") for d in deliveries)),
    }
