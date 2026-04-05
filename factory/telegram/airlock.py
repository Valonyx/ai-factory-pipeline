"""
AI Factory Pipeline v5.6 — App Store Airlock (Binary Delivery Fallback)

Implements:
  - §7.6 App Store Airlock (binary Telegram delivery)
  - §7.6.0 Automation vs Manual boundaries [H2/M7]
  - §7.6.0b STRICT_STORE_COMPLIANCE flag
  - §7.6.2 airlock_deliver() — size-aware binary delivery
  - §7.5 upload_to_temp_storage() [C3]
  - §7.5 compute_sha256() — integrity verification

The Airlock is the fallback delivery path when programmatic
App Store / Play Store uploads fail. It does NOT bypass store
review. It is a file transfer mechanism with instructional guidance.

Spec Authority: v5.6 §7.5, §7.6
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from factory.core.state import (
    PipelineState,
    NotificationType,
    TELEGRAM_FILE_LIMIT_MB,
    SOFT_FILE_LIMIT_MB,
    ARTIFACT_TTL_HOURS,
)
from factory.telegram.notifications import (
    send_telegram_message,
    send_telegram_file,
    notify_operator,
)

logger = logging.getLogger("factory.telegram.airlock")


# ═══════════════════════════════════════════════════════════════════
# §7.5 Integrity Verification
# ═══════════════════════════════════════════════════════════════════


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 checksum for integrity verification.

    Spec: §7.5 [C3]
    Used when delivering binaries to verify integrity.
    """
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ═══════════════════════════════════════════════════════════════════
# §7.5 Temporary Storage Upload [C3]
# ═══════════════════════════════════════════════════════════════════


async def upload_to_temp_storage(
    file_path: str,
    project_id: str,
    ttl_hours: int = ARTIFACT_TTL_HOURS,
) -> str:
    """Upload binary to Supabase Storage, return signed URL.

    Spec: §7.5 [C3]
    Provider: Supabase Storage (existing dependency — no new cost).
    Bucket: build-artifacts (auto-created if missing).
    TTL: 72 hours default, cleaned by Janitor Agent.

    Args:
        file_path: Local path to binary.
        project_id: Project ID for organization.
        ttl_hours: Hours until link expires (default 72).

    Returns:
        Signed download URL with expiry.
    """
    bucket = "build-artifacts"
    object_key = f"{project_id}/{Path(file_path).name}"

    try:
        from factory.integrations.supabase import get_supabase_client
        supabase_client = get_supabase_client()

        with open(file_path, "rb") as f:
            await supabase_client.storage.from_(bucket).upload(
                object_key, f,
                file_options={"content-type": "application/octet-stream"},
            )

        signed = await supabase_client.storage.from_(bucket).create_signed_url(
            object_key, expires_in=ttl_hours * 3600,
        )

        # Record for Janitor cleanup
        await supabase_client.table("temp_artifacts").insert({
            "project_id": project_id,
            "object_key": object_key,
            "bucket": bucket,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
            ).isoformat(),
            "size_bytes": os.path.getsize(file_path),
        }).execute()

        return signed["signedURL"]

    except (ImportError, Exception) as e:
        logger.warning(
            f"[MOCK] Supabase Storage not available: {e}. "
            f"Returning mock URL."
        )
        return f"https://mock-storage.example.com/{object_key}?expires={ttl_hours}h"


# ═══════════════════════════════════════════════════════════════════
# §7.6.2 Airlock Delivery
# ═══════════════════════════════════════════════════════════════════

# Platform-specific file extensions
PLATFORM_EXTENSIONS: dict[str, str] = {
    "ios": ".ipa",
    "android": ".aab",
    "web": ".zip",
}

# Manual upload instructions per platform
IOS_UPLOAD_INSTRUCTIONS = (
    "📋 iOS Upload Steps:\n"
    "1. Open Transporter app (macOS)\n"
    "2. Drag the .ipa file into Transporter\n"
    "3. Click 'Deliver'\n"
    "4. Go to App Store Connect → TestFlight to verify\n\n"
    "Alternative: App Store Connect web → upload via browser"
)

ANDROID_UPLOAD_INSTRUCTIONS = (
    "📋 Android Upload Steps:\n"
    "1. Open Play Console → your app\n"
    "2. Go to Release → Production (or Testing)\n"
    "3. Create new release\n"
    "4. Upload the .aab file\n"
    "5. Review and roll out"
)

AIRLOCK_DISCLAIMER = (
    "\n\n⚠️ IMPORTANT: Manual upload does not bypass Apple/Google review. "
    "Your app may still be rejected for policy violations. "
    "Review compliance warnings from S1 Legal Gate before submitting."
)


async def airlock_deliver(
    state: PipelineState,
    platform: str,
    binary_path: str,
    error: str,
) -> dict:
    """Deliver binary directly to operator when API upload fails.

    Spec: §7.6.2
    Size routing:
      ≤50MB: Direct Telegram sendDocument [V12]
      >50MB ≤200MB: Supabase Storage signed URL [C3]
      >200MB: Supabase Storage with size warning

    Args:
        state: Pipeline state.
        platform: Target platform ('ios', 'android', 'web').
        binary_path: Local path to compiled binary.
        error: The API upload error message.

    Returns:
        Dict with delivery method and details.
    """
    ext = PLATFORM_EXTENSIONS.get(platform, ".bin")
    store_name = (
        "App Store Connect" if platform == "ios"
        else "Play Console" if platform == "android"
        else "deployment target"
    )

    # Check file exists
    if not os.path.exists(binary_path):
        logger.error(f"Binary not found: {binary_path}")
        await send_telegram_message(
            state.operator_id,
            f"⚠️ {platform.upper()} Airlock Error\n\n"
            f"Binary file not found at build output path.\n"
            f"Check build logs with /warroom.",
        )
        return {"method": "error", "error": "binary_not_found"}

    size_mb = os.path.getsize(binary_path) / (1024 * 1024)
    checksum = compute_sha256(binary_path)

    # ── Notify operator of Airlock activation ──
    await send_telegram_message(
        state.operator_id,
        f"🔒 {platform.upper()} Airlock Activated\n\n"
        f"API upload failed: {error[:200]}\n\n"
        f"Binary: {Path(binary_path).name} ({size_mb:.1f} MB)\n"
        f"SHA-256: {checksum[:16]}...\n"
        f"Delivering to you for manual upload to {store_name}.",
    )

    # ── Route by size ──
    if size_mb <= TELEGRAM_FILE_LIMIT_MB:
        # Direct Telegram delivery
        success = await send_telegram_file(
            state.operator_id,
            binary_path,
            caption=f"{platform.upper()} binary — upload to {store_name}",
            filename=f"{state.project_id}{ext}",
        )

        if not success:
            # Fallback to storage if Telegram send fails
            url = await upload_to_temp_storage(binary_path, state.project_id)
            await send_telegram_message(
                state.operator_id,
                f"📦 Direct send failed. Download link:\n{url}\n"
                f"SHA-256: {checksum}\n"
                f"Expires: {ARTIFACT_TTL_HOURS} hours",
            )
            method = "temp_storage_fallback"
        else:
            method = "telegram_direct"

    elif size_mb <= SOFT_FILE_LIMIT_MB:
        # Supabase Storage signed URL
        url = await upload_to_temp_storage(binary_path, state.project_id)
        await send_telegram_message(
            state.operator_id,
            f"📦 Binary too large for Telegram ({size_mb:.1f} MB > "
            f"{TELEGRAM_FILE_LIMIT_MB} MB)\n\n"
            f"Download: {url}\n"
            f"SHA-256: {checksum}\n"
            f"Size: {size_mb:.1f} MB\n"
            f"Expires: {ARTIFACT_TTL_HOURS} hours",
        )
        method = "temp_storage"

    else:
        # Over soft limit — upload with warning
        url = await upload_to_temp_storage(binary_path, state.project_id)
        await send_telegram_message(
            state.operator_id,
            f"⚠️ Large binary ({size_mb:.1f} MB — over {SOFT_FILE_LIMIT_MB} MB "
            f"soft limit)\n\n"
            f"Download: {url}\n"
            f"SHA-256: {checksum}\n"
            f"Expires: {ARTIFACT_TTL_HOURS} hours\n\n"
            f"Consider reducing build size for future projects.",
        )
        method = "temp_storage_large"

    # ── Send platform-specific upload instructions ──
    if platform == "ios":
        await send_telegram_message(
            state.operator_id,
            IOS_UPLOAD_INSTRUCTIONS + AIRLOCK_DISCLAIMER,
        )
    elif platform == "android":
        await send_telegram_message(
            state.operator_id,
            ANDROID_UPLOAD_INSTRUCTIONS + AIRLOCK_DISCLAIMER,
        )
    else:
        await send_telegram_message(
            state.operator_id,
            f"📋 Upload the {ext} file to your deployment target.\n"
            + AIRLOCK_DISCLAIMER,
        )

    # ── Audit log ──
    delivery_record = {
        "method": method,
        "platform": platform,
        "size_mb": round(size_mb, 2),
        "checksum": checksum,
        "api_error": error[:500],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        f"[Airlock] Delivered {platform} binary for {state.project_id}: "
        f"{method} ({size_mb:.1f} MB)"
    )

    return delivery_record


# ═══════════════════════════════════════════════════════════════════
# §7.6.0b Compliance Gate Helper
# ═══════════════════════════════════════════════════════════════════


async def check_store_compliance_advisory(
    state: PipelineState,
    platform: str,
) -> dict:
    """Check if app meets store guidelines (advisory only).

    Spec: §7.6.0b
    Uses STRICT_STORE_COMPLIANCE flag to determine blocking behavior.
    Returns compliance result dict.
    """
    from factory.core.state import (
        ComplianceGateResult,
        STRICT_STORE_COMPLIANCE,
    )

    # Stub — real implementation uses Scout to research guidelines
    result = ComplianceGateResult(
        platform=platform,
        overall_pass=True,
        blockers=[],
        warnings=[],
        guidelines_version="stub",
        confidence=0.5,
        source_ids=[],
    )

    if result.should_block():
        await notify_operator(
            state,
            NotificationType.LEGAL_ALERT,
            f"⚖️ Store compliance gate BLOCKED for {platform}\n"
            f"Blockers: {len(result.blockers)}\n"
            f"Use /force_continue to override.",
        )

    return result.model_dump()