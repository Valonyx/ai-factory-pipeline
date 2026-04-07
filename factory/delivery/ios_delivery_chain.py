"""
AI Factory Pipeline v5.6 — iOS Delivery Chain

Cascading delivery for iOS builds. Tries each provider in order and
falls back automatically. When a paid account becomes available,
enabling it requires only setting the relevant env vars.

Provider cascade (highest quality → most resilient):

  1. App Store Connect API  — PAID ($99/year Apple Dev account)
                              Best: real App Store / TestFlight delivery
                              Env: APP_STORE_API_KEY_ID + APP_STORE_ISSUER_ID + key
  2. Fastlane pilot         — FREE (needs Apple Dev account, not paid service)
                              Uses same Apple account via open-source tooling
                              Env: FASTLANE_USER + FASTLANE_PASSWORD
  3. Firebase App Distribution — FREE (no Apple account needed)
                              Distributes to testers outside App Store
                              Env: FIREBASE_APP_ID_IOS + FIREBASE_TOKEN
  4. Airlock (Telegram)     — ALWAYS WORKS (zero config)
                              Sends IPA directly to operator via Telegram
                              Operator manually uploads to App Store Connect

Switch to paid: Set APP_STORE_API_KEY_ID + APP_STORE_ISSUER_ID + private key.
  The chain will automatically prefer it over the free options.

Force a specific provider: IOS_DELIVERY_PROVIDER=appstore|fastlane|firebase|airlock

Spec Authority: v5.6 §4.7.2, ADR-016
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from factory.core.state import PipelineState

logger = logging.getLogger("factory.delivery.ios_delivery_chain")


@dataclass
class iOSDeliveryResult:
    success: bool
    provider: str              # appstore | fastlane | firebase | airlock
    method: str                # api | cli | distribution | telegram
    manual_upload_required: bool = False
    testflight_url: Optional[str] = None
    firebase_url: Optional[str] = None
    airlock_delivered: bool = False
    error: str = ""
    details: dict = field(default_factory=dict)


async def deliver_ios(
    ipa_path: str,
    state: "PipelineState",
    bundle_id: str = "",
    release_notes: str = "New build",
    target: str = "testflight",    # testflight | appstore | distribution
) -> iOSDeliveryResult:
    """Deliver an iOS IPA through the provider cascade.

    Tries providers in priority order, returns first success.
    Airlock (Telegram delivery) is the guaranteed final fallback.
    """
    forced = os.getenv("IOS_DELIVERY_PROVIDER", "").lower()
    providers = _build_provider_list(forced)

    for provider in providers:
        logger.info(f"[ios-delivery] Trying provider: {provider}")
        try:
            result = await _try_provider(
                provider, ipa_path, state, bundle_id, release_notes, target,
            )
            if result.success:
                logger.info(f"[ios-delivery] Success via {provider}")
                return result
            logger.info(f"[ios-delivery] {provider} failed: {result.error[:100]}")
        except Exception as e:
            logger.warning(f"[ios-delivery] {provider} exception: {e}")
            continue

    # All providers failed — should never reach here since Airlock always works
    return iOSDeliveryResult(
        success=False,
        provider="none",
        method="none",
        error="All iOS delivery providers failed",
    )


def _build_provider_list(forced: str) -> list[str]:
    """Build ordered provider list based on configuration and forcing."""
    if forced and forced in ("appstore", "fastlane", "firebase", "airlock"):
        return [forced]

    providers: list[str] = []

    # 1. App Store Connect API (paid, requires Apple Dev account)
    has_appstore = bool(
        os.getenv("APP_STORE_API_KEY_ID")
        and os.getenv("APP_STORE_ISSUER_ID")
        and (os.getenv("APP_STORE_PRIVATE_KEY") or os.getenv("APP_STORE_KEY_PATH"))
    )
    if has_appstore:
        providers.append("appstore")

    # 2. Fastlane (free open-source, needs Apple account credentials)
    has_fastlane = bool(os.getenv("FASTLANE_USER") and os.getenv("FASTLANE_PASSWORD"))
    if has_fastlane:
        providers.append("fastlane")

    # 3. Firebase App Distribution (free, no Apple account)
    has_firebase = bool(
        os.getenv("FIREBASE_APP_ID_IOS")
        and (os.getenv("FIREBASE_TOKEN") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    )
    if has_firebase:
        providers.append("firebase")

    # 4. Airlock — always available
    providers.append("airlock")

    return providers


async def _try_provider(
    provider: str,
    ipa_path: str,
    state: "PipelineState",
    bundle_id: str,
    release_notes: str,
    target: str,
) -> iOSDeliveryResult:
    """Dispatch to a specific iOS delivery provider."""

    if provider == "appstore":
        from factory.appstore.apple_api import AppleAPIClient
        client = AppleAPIClient()
        if not await client.check_auth():
            return iOSDeliveryResult(
                success=False, provider="appstore", method="api",
                error="App Store Connect auth failed — check API key config",
            )
        # Upload via xcrun altool (installed with Xcode)
        upload = await _xcrun_upload(ipa_path)
        if upload["success"]:
            return iOSDeliveryResult(
                success=True,
                provider="appstore",
                method="api",
                testflight_url="https://appstoreconnect.apple.com/apps",
                details=upload,
            )
        return iOSDeliveryResult(
            success=False, provider="appstore", method="api",
            error=upload.get("error", "Upload failed"),
        )

    if provider == "fastlane":
        from factory.appstore.fastlane_runner import (
            upload_to_testflight, upload_to_appstore, check_installed,
        )
        if not await check_installed():
            return iOSDeliveryResult(
                success=False, provider="fastlane", method="cli",
                error="fastlane not installed (gem install fastlane)",
            )
        if target == "appstore":
            result = await upload_to_appstore(ipa_path)
        else:
            result = await upload_to_testflight(ipa_path, changelog=release_notes)

        return iOSDeliveryResult(
            success=result["success"],
            provider="fastlane",
            method="cli",
            error=result.get("error", ""),
            details=result,
        )

    if provider == "firebase":
        from factory.delivery.firebase_distribution import distribute_ios, check_installed
        if not await check_installed():
            return iOSDeliveryResult(
                success=False, provider="firebase", method="distribution",
                error="Firebase CLI not installed (npm install -g firebase-tools)",
            )
        result = await distribute_ios(ipa_path, release_notes=release_notes)
        return iOSDeliveryResult(
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
            state=state, platform="ios", binary_path=ipa_path,
            error="Automated delivery not available — manual upload required",
        )
        return iOSDeliveryResult(
            success=True,
            provider="airlock",
            method="telegram",
            manual_upload_required=True,
            airlock_delivered=True,
            details=airlock_result,
        )

    return iOSDeliveryResult(
        success=False, provider=provider, method="unknown",
        error=f"Unknown iOS delivery provider: {provider}",
    )


async def _xcrun_upload(ipa_path: str) -> dict:
    """Upload IPA using xcrun altool (free, installed with Xcode)."""
    import asyncio
    key_id    = os.getenv("APP_STORE_API_KEY_ID", "")
    issuer_id = os.getenv("APP_STORE_ISSUER_ID", "")
    key_path  = os.getenv("APP_STORE_KEY_PATH", "")

    if not all([key_id, issuer_id]):
        return {"success": False, "error": "APP_STORE_API_KEY_ID / APP_STORE_ISSUER_ID not set"}

    cmd = [
        "xcrun", "altool", "--upload-app",
        "-f", ipa_path, "-t", "ios",
        "--apiKey", key_id,
        "--apiIssuer", issuer_id,
    ]
    if key_path:
        cmd += ["--apiKey-path", key_path]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=900)
        output = stdout.decode("utf-8", errors="replace")
        success = proc.returncode == 0
        return {"success": success, "output": output[-800:], "error": "" if success else output[-400:]}
    except asyncio.TimeoutError:
        return {"success": False, "error": "xcrun altool timed out (15 min)"}
    except FileNotFoundError:
        return {"success": False, "error": "xcrun not found — requires macOS with Xcode"}
