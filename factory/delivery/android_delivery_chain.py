"""
AI Factory Pipeline v5.6 — Android Delivery Chain

Cascading delivery for Android builds. Tries each provider in order,
falls back automatically. Enable paid options by setting env vars.

Provider cascade:

  1. Google Play Developer API — PAID ($25 one-time Google Play account)
                                 Best: direct Play Store / internal track upload
                                 Env: GOOGLE_PLAY_SERVICE_ACCOUNT_JSON + package name
  2. Firebase App Distribution — FREE (no Play account needed)
                                 Distributes to testers outside Play Store
                                 Env: FIREBASE_APP_ID_ANDROID + FIREBASE_TOKEN
  3. Airlock (Telegram)        — ALWAYS WORKS (zero config)
                                 Sends APK/AAB directly to operator via Telegram
                                 Operator manually uploads to Play Console

Switch to paid: Set GOOGLE_PLAY_SERVICE_ACCOUNT_JSON.
  The chain will automatically prefer it.

Force a specific provider: ANDROID_DELIVERY_PROVIDER=playstore|firebase|airlock

Spec Authority: v5.6 §4.7.1, ADR-016
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from factory.core.state import PipelineState

logger = logging.getLogger("factory.delivery.android_delivery_chain")


@dataclass
class AndroidDeliveryResult:
    success: bool
    provider: str              # playstore | firebase | airlock
    method: str                # api | distribution | telegram
    track: Optional[str] = None   # internal | alpha | beta | production
    manual_upload_required: bool = False
    firebase_url: Optional[str] = None
    airlock_delivered: bool = False
    version_code: Optional[int] = None
    error: str = ""
    details: dict = field(default_factory=dict)


async def deliver_android(
    artifact_path: str,         # Path to APK or AAB file
    state: "PipelineState",
    package_name: str = "",
    release_notes: str = "New release",
    track: str = "internal",    # internal | alpha | beta | production
    artifact_type: str = "aab", # aab | apk
) -> AndroidDeliveryResult:
    """Deliver an Android build through the provider cascade."""
    forced = os.getenv("ANDROID_DELIVERY_PROVIDER", "").lower()
    providers = _build_provider_list(forced)

    for provider in providers:
        logger.info(f"[android-delivery] Trying provider: {provider}")
        try:
            result = await _try_provider(
                provider, artifact_path, state,
                package_name, release_notes, track, artifact_type,
            )
            if result.success:
                logger.info(f"[android-delivery] Success via {provider}")
                return result
            logger.info(f"[android-delivery] {provider} failed: {result.error[:100]}")
        except Exception as e:
            logger.warning(f"[android-delivery] {provider} exception: {e}")
            continue

    return AndroidDeliveryResult(
        success=False,
        provider="none",
        method="none",
        error="All Android delivery providers failed",
    )


def _build_provider_list(forced: str) -> list[str]:
    if forced and forced in ("playstore", "firebase", "airlock"):
        return [forced]

    providers: list[str] = []

    # 1. Google Play API (paid $25 one-time)
    has_playstore = bool(
        os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
        or os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH")
    )
    if has_playstore:
        providers.append("playstore")

    # 2. Firebase App Distribution (free)
    has_firebase = bool(
        os.getenv("FIREBASE_APP_ID_ANDROID")
        and (os.getenv("FIREBASE_TOKEN") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    )
    if has_firebase:
        providers.append("firebase")

    # 3. Airlock — always available
    providers.append("airlock")

    return providers


async def _try_provider(
    provider: str,
    artifact_path: str,
    state: "PipelineState",
    package_name: str,
    release_notes: str,
    track: str,
    artifact_type: str,
) -> AndroidDeliveryResult:
    if provider == "playstore":
        from factory.playstore.google_api import GooglePlayAPIClient
        client = GooglePlayAPIClient(package_name=package_name)
        if artifact_type == "aab":
            result = await client.upload_aab(artifact_path, package_name=package_name, track=track)
        else:
            result = await client.upload_apk(artifact_path, package_name=package_name, track=track)

        return AndroidDeliveryResult(
            success=result.get("success", False),
            provider="playstore",
            method="api",
            track=track,
            version_code=result.get("version_code"),
            error=result.get("error", ""),
            details=result,
        )

    if provider == "firebase":
        from factory.delivery.firebase_distribution import distribute_android, check_installed
        if not await check_installed():
            return AndroidDeliveryResult(
                success=False, provider="firebase", method="distribution",
                error="Firebase CLI not installed (npm install -g firebase-tools)",
            )
        result = await distribute_android(artifact_path, release_notes=release_notes)
        return AndroidDeliveryResult(
            success=result["success"],
            provider="firebase",
            method="distribution",
            firebase_url=result.get("download_url"),
            error=result.get("error", ""),
            details=result,
        )

    if provider == "airlock":
        from factory.telegram.airlock import airlock_deliver
        airlock_result = await airlock_deliver(
            state=state, platform="android", binary_path=artifact_path,
            error="Automated Play Store upload not configured — manual upload required",
        )
        return AndroidDeliveryResult(
            success=True,
            provider="airlock",
            method="telegram",
            manual_upload_required=True,
            airlock_delivered=True,
            details=airlock_result,
        )

    return AndroidDeliveryResult(
        success=False, provider=provider, method="unknown",
        error=f"Unknown Android delivery provider: {provider}",
    )
