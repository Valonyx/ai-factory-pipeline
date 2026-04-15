"""
AI Factory Pipeline v5.8 — Delivery Module

File delivery, Airlock fallback, app store uploads, handoff intelligence.
"""

from factory.delivery.file_delivery import (
    compute_sha256,
    upload_to_temp_storage,
    send_telegram_file,
    cleanup_expired_artifacts,
    TELEGRAM_FILE_LIMIT_MB,
    SOFT_FILE_LIMIT_MB,
    ARTIFACT_TTL_HOURS,
    STORAGE_BUCKET,
)

from factory.delivery.airlock import (
    airlock_deliver,
    get_airlock_summary,
    AIRLOCK_DISCLAIMER,
    IOS_UPLOAD_STEPS,
    ANDROID_UPLOAD_STEPS,
    PLATFORM_EXTENSIONS,
)

from factory.delivery.app_store import (
    attempt_store_upload,
    check_upload_status,
)

from factory.delivery.handoff_docs import (
    generate_handoff_intelligence_pack,
    store_handoff_docs_in_memory,
    PER_PROJECT_DOCS,
    PER_PROGRAM_DOCS,
)

__all__ = [
    # File Delivery
    "compute_sha256", "upload_to_temp_storage", "send_telegram_file",
    "cleanup_expired_artifacts",
    "TELEGRAM_FILE_LIMIT_MB", "SOFT_FILE_LIMIT_MB", "ARTIFACT_TTL_HOURS",
    # Airlock
    "airlock_deliver", "get_airlock_summary", "AIRLOCK_DISCLAIMER",
    "IOS_UPLOAD_STEPS", "ANDROID_UPLOAD_STEPS",
    # App Store
    "attempt_store_upload", "check_upload_status",
    # Handoff Docs
    "generate_handoff_intelligence_pack", "store_handoff_docs_in_memory",
    "PER_PROJECT_DOCS", "PER_PROGRAM_DOCS",
]