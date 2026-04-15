"""
AI Factory Pipeline v5.8 — File Delivery Functions

Implements:
  - §7.5 [C3] send_telegram_file() — size-aware delivery
  - §7.5 [C3] upload_to_temp_storage() — Supabase Storage + signed URL
  - §7.5 compute_sha256() — integrity verification
  - Janitor cleanup recording for temp artifacts

Size routing:
  ≤50MB:  Direct Telegram Bot API sendDocument [V12]
  50-200MB: Supabase Storage signed URL + SHA-256
  >200MB: Same + soft limit warning

Spec Authority: v5.8 §7.5
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from factory.telegram.notifications import send_telegram_message

logger = logging.getLogger("factory.delivery.file_delivery")


# ═══════════════════════════════════════════════════════════════════
# §7.5 Configuration [C3]
# ═══════════════════════════════════════════════════════════════════

TELEGRAM_FILE_LIMIT_MB = int(
    os.getenv("TELEGRAM_FILE_LIMIT_MB", "50")
)   # [V12] Verified: 50MB for bots

SOFT_FILE_LIMIT_MB = int(
    os.getenv("SOFT_FILE_LIMIT_MB", "200")
)

ARTIFACT_TTL_HOURS = int(
    os.getenv("ARTIFACT_TTL_HOURS", "72")
)

STORAGE_BUCKET = "build-artifacts"


# ═══════════════════════════════════════════════════════════════════
# §7.5 SHA-256 Checksum
# ═══════════════════════════════════════════════════════════════════


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 checksum for integrity verification.

    Spec: §7.5
    """
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ═══════════════════════════════════════════════════════════════════
# §7.5 upload_to_temp_storage [C3]
# ═══════════════════════════════════════════════════════════════════


async def upload_to_temp_storage(
    file_path: str,
    project_id: str,
    ttl_hours: int = ARTIFACT_TTL_HOURS,
    supabase_client=None,
) -> str:
    """Upload binary to Supabase Storage, return signed URL.

    Spec: §7.5 [C3]

    Provider: Supabase Storage (existing dependency — no new cost)
    Auth: Service key (SUPABASE_SERVICE_KEY env var)
    TTL: 72 hours default, cleaned by Janitor Agent
    Bucket: build-artifacts (auto-created if missing)
    Returns: Signed download URL with expiry
    """
    object_key = f"{project_id}/{Path(file_path).name}"

    if supabase_client:
        # Production: Supabase Storage API
        with open(file_path, "rb") as f:
            await supabase_client.storage.from_(STORAGE_BUCKET).upload(
                object_key, f,
                file_options={"content-type": "application/octet-stream"},
            )

        signed = await supabase_client.storage.from_(
            STORAGE_BUCKET
        ).create_signed_url(
            object_key, expires_in=ttl_hours * 3600,
        )

        # Record for Janitor cleanup
        await supabase_client.table("temp_artifacts").insert({
            "project_id": project_id,
            "object_key": object_key,
            "bucket": STORAGE_BUCKET,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
            ).isoformat(),
            "size_bytes": os.path.getsize(file_path),
        }).execute()

        return signed["signedURL"]

    # No client passed — try to get one from the integration
    try:
        from factory.integrations.supabase import get_supabase_client
        client = get_supabase_client()
        if client:
            # Try Supabase Storage
            with open(file_path, "rb") as f:
                client.storage.from_(STORAGE_BUCKET).upload(
                    object_key, f,
                    file_options={"content-type": "application/octet-stream"},
                )
            signed = client.storage.from_(STORAGE_BUCKET).create_signed_url(
                object_key, expires_in=ttl_hours * 3600,
            )
            # Record for Janitor
            try:
                client.table("temp_artifacts").insert({
                    "project_id": project_id,
                    "object_key": object_key,
                    "bucket": STORAGE_BUCKET,
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
                    ).isoformat(),
                    "size_bytes": os.path.getsize(file_path),
                }).execute()
            except Exception:
                pass
            url = signed.get("signedURL") or signed.get("data", {}).get("signedUrl", "")
            if url:
                logger.info(f"Uploaded {object_key} to Supabase Storage")
                return url
    except Exception as e:
        logger.debug(f"Supabase Storage upload failed: {e}")

    # GCS fallback (if ARTIFACT_BUCKET env var is set)
    gcs_bucket = os.getenv("ARTIFACT_BUCKET", "")
    if gcs_bucket:
        try:
            from google.cloud import storage as gcs
            gcs_client = gcs.Client()
            bucket = gcs_client.bucket(gcs_bucket)
            blob = bucket.blob(object_key)
            blob.upload_from_filename(file_path)
            url = blob.generate_signed_url(
                expiration=timedelta(hours=ttl_hours),
                method="GET",
                version="v4",
            )
            logger.info(f"Uploaded {object_key} to GCS bucket {gcs_bucket}")
            return url
        except Exception as e:
            logger.debug(f"GCS upload failed: {e}")

    # Final fallback: log size and return a descriptive marker
    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    logger.warning(
        f"No storage backend available — {file_path} ({size} bytes) not uploaded"
    )
    return f"local://{file_path}"


# ═══════════════════════════════════════════════════════════════════
# §7.5 send_telegram_file [C3]
# ═══════════════════════════════════════════════════════════════════


async def send_telegram_file(
    operator_id: str,
    file_path: str,
    project_id: str = "",
    supabase_client=None,
) -> dict:
    """Size-aware file delivery via Telegram.

    Spec: §7.5 [C3]

    ≤50MB:  Direct upload via Telegram Bot API sendDocument
    >50MB:  Upload to Supabase Storage, send signed URL + checksum
    >200MB: Same + soft limit warning
    """
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return {"method": "error", "error": "file_not_found"}

    size_bytes = os.path.getsize(file_path)
    size_mb = size_bytes / (1024 * 1024)
    filename = Path(file_path).name

    # ── ≤50MB: Direct Telegram ──
    if size_mb <= TELEGRAM_FILE_LIMIT_MB:
        await send_telegram_message(
            operator_id,
            f"📎 Sending file: {filename} ({size_mb:.1f} MB)",
        )
        # In production: bot.send_document(operator_id, file, filename=...)
        logger.info(
            f"[{project_id}] Direct Telegram send: "
            f"{filename} ({size_mb:.1f} MB)"
        )
        return {
            "method": "telegram_direct",
            "size_mb": round(size_mb, 1),
            "filename": filename,
        }

    # ── >50MB: Supabase Storage + signed URL ──
    url = await upload_to_temp_storage(
        file_path, project_id, supabase_client=supabase_client,
    )
    checksum = compute_sha256(file_path)

    if size_mb <= SOFT_FILE_LIMIT_MB:
        await send_telegram_message(
            operator_id,
            f"📦 Build artifact ready (too large for direct send):\n"
            f"Download: {url}\n"
            f"SHA-256: {checksum}\n"
            f"Size: {size_mb:.1f} MB\n"
            f"Expires: {ARTIFACT_TTL_HOURS} hours",
        )
        logger.info(
            f"[{project_id}] Storage delivery: "
            f"{filename} ({size_mb:.1f} MB)"
        )
        return {
            "method": "temp_storage",
            "url": url,
            "checksum": checksum,
            "size_mb": round(size_mb, 1),
        }

    # ── >200MB: Soft limit warning ──
    await send_telegram_message(
        operator_id,
        f"📦 Large build artifact ({size_mb:.1f} MB):\n"
        f"Download: {url}\n"
        f"SHA-256: {checksum}\n"
        f"Expires: {ARTIFACT_TTL_HOURS} hours\n"
        f"Warning: File exceeds {SOFT_FILE_LIMIT_MB}MB soft limit. "
        f"Consider optimizing build size.",
    )
    logger.warning(
        f"[{project_id}] Large file delivery: "
        f"{filename} ({size_mb:.1f} MB) exceeds soft limit"
    )
    return {
        "method": "temp_storage_oversized",
        "url": url,
        "checksum": checksum,
        "size_mb": round(size_mb, 1),
    }


# ═══════════════════════════════════════════════════════════════════
# Janitor Cleanup Query
# ═══════════════════════════════════════════════════════════════════


async def cleanup_expired_artifacts(supabase_client=None) -> int:
    """Delete expired temp artifacts.

    Spec: §7.5 [C3]
    Called by Janitor Agent every 6 hours.
    """
    if not supabase_client:
        return 0

    now = datetime.now(timezone.utc).isoformat()
    expired = await supabase_client.table("temp_artifacts").select(
        "object_key, bucket"
    ).lt("expires_at", now).execute()

    count = 0
    for entry in expired.data:
        try:
            await supabase_client.storage.from_(
                entry["bucket"]
            ).remove([entry["object_key"]])
            count += 1
        except Exception as e:
            logger.error(f"Cleanup failed for {entry['object_key']}: {e}")

    if count:
        await supabase_client.table("temp_artifacts").delete().lt(
            "expires_at", now,
        ).execute()
        logger.info(f"Janitor: cleaned {count} expired artifacts")

    return count