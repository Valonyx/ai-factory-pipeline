"""
AI Factory Pipeline v5.6 — S6 Deploy Node

Implements:
  - §4.7 S6 Deploy (push to hosting, app stores, API endpoints)
  - §4.7.1 Android deployment (Google Play API, Airlock fallback)
  - §4.7.2 iOS deployment (Transporter CLI, Airlock fallback)
  - §4.7.3 Platform icon generation (v5.4.1 Patch 1)
  - §4.7.4 iOS App Store Submission Protocol (FIX-21)
  - API-first approach (ADR-016): no portal UI login

Spec Authority: v5.6 §4.7, §4.7.1–§4.7.4
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    NotificationType,
    PipelineState,
    Stage,
    TechStack,
)
from factory.core.roles import call_ai
from factory.core.execution import ExecutionModeManager
from factory.core.user_space import enforce_user_space
from factory.telegram.notifications import notify_operator, send_telegram_message
from factory.telegram.airlock import airlock_deliver
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s6_deploy")


# ═══════════════════════════════════════════════════════════════════
# iOS Submission Protocol (FIX-21)
# ═══════════════════════════════════════════════════════════════════

IOS_SUBMISSION_STEPS = [
    {
        "step": 1, "name": "archive",
        "command": (
            "xcodebuild archive -workspace App.xcworkspace "
            "-scheme App -archivePath build/App.xcarchive"
        ),
        "timeout": 600,
        "max_retries": 2, "backoff_base": 30,
    },
    {
        "step": 2, "name": "export",
        "command": (
            "xcodebuild -exportArchive "
            "-archivePath build/App.xcarchive "
            "-exportOptionsPlist ExportOptions.plist "
            "-exportPath build/export"
        ),
        "timeout": 300,
        "max_retries": 2, "backoff_base": 30,
    },
    {
        "step": 3, "name": "validate",
        "command": (
            "xcrun altool --validate-app "
            "-f build/export/App.ipa -t ios "
            "--apiKey $APP_STORE_API_KEY "
            "--apiIssuer $APP_STORE_ISSUER_ID"
        ),
        "timeout": 120,
        "max_retries": 3, "backoff_base": 60,
    },
    {
        "step": 4, "name": "upload",
        "command": (
            "xcrun altool --upload-app "
            "-f build/export/App.ipa -t ios "
            "--apiKey $APP_STORE_API_KEY "
            "--apiIssuer $APP_STORE_ISSUER_ID"
        ),
        "timeout": 900,
        "max_retries": 3, "backoff_base": 120,
    },
    {
        "step": 5, "name": "poll_processing",
        "command": (
            "xcrun altool --notarization-info $REQUEST_UUID "
            "--apiKey $APP_STORE_API_KEY "
            "--apiIssuer $APP_STORE_ISSUER_ID"
        ),
        "timeout": 3600,
        "max_retries": 60, "backoff_base": 0,
        "poll_interval": 60,
    },
]


# ═══════════════════════════════════════════════════════════════════
# §4.7 S6 Deploy Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S6_DEPLOY)
async def s6_deploy_node(state: PipelineState) -> PipelineState:
    """S6: Deploy — push artifacts to hosting, app stores, or API endpoints.

    Spec: §4.7
    API-first approach (ADR-016): no portal UI login.
    On failure: App Store Airlock (binary delivery via Telegram §7.6).

    Cost target: <$0.30
    """
    blueprint_data = state.s2_output or {}
    artifacts = (state.s4_output or {}).get("artifacts", {})
    stack_value = blueprint_data.get("selected_stack", "flutterflow")
    target_platforms = blueprint_data.get("target_platforms", ["ios", "android"])

    try:
        stack = TechStack(stack_value)
    except ValueError:
        stack = TechStack.FLUTTERFLOW

    exec_mgr = ExecutionModeManager(state)
    deploy_results: dict = {}

    # ══════════════════════════════════════════
    # Phase 1: Platform Icon Generation (v5.4.1 Patch 1)
    # ══════════════════════════════════════════
    brand_assets = state.project_metadata.get("brand_assets", [])
    logo_assets = [a for a in brand_assets if a.get("asset_type") == "logo"]

    if logo_assets:
        deploy_results["icons_generated"] = {
            "source": "brand_assets",
            "platforms": target_platforms,
        }
    else:
        await notify_operator(
            state,
            NotificationType.INFO,
            "📱 No logo found in brand assets. "
            "Using placeholder icon. Upload a logo via Telegram to replace it.",
        )
        deploy_results["icons_generated"] = {"placeholder": True}

    # ══════════════════════════════════════════
    # Phase 2: Web Deployment
    # ══════════════════════════════════════════
    if "web" in target_platforms:
        web_result = await _deploy_web(state, stack, exec_mgr)
        deploy_results["web"] = web_result

    # ══════════════════════════════════════════
    # Phase 3: Android Deployment
    # ══════════════════════════════════════════
    if "android" in target_platforms and stack != TechStack.SWIFT:
        android_result = await _deploy_android(state, stack, exec_mgr)
        deploy_results["android"] = android_result

    # ══════════════════════════════════════════
    # Phase 4: iOS Deployment
    # ══════════════════════════════════════════
    if "ios" in target_platforms and stack != TechStack.KOTLIN:
        ios_result = await _deploy_ios(state, stack, exec_mgr)
        deploy_results["ios"] = ios_result

    state.s6_output = {
        "deployments": deploy_results,
        "all_success": all(
            d.get("success", False)
            for k, d in deploy_results.items()
            if k not in ("icons_generated",)
        ),
    }

    logger.info(
        f"[{state.project_id}] S6 Deploy: "
        f"platforms={list(deploy_results.keys())}, "
        f"all_success={state.s6_output['all_success']}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# Web Deployment
# ═══════════════════════════════════════════════════════════════════


async def _deploy_web(
    state: PipelineState,
    stack: TechStack,
    exec_mgr: ExecutionModeManager,
) -> dict:
    """Deploy to web (Firebase Hosting or Cloud Run).

    Spec: §4.7
    """
    if stack == TechStack.PYTHON_BACKEND:
        app_name = (state.s0_output or {}).get("app_name", state.project_id)
        cmd = (
            f"gcloud run deploy "
            f"{app_name.lower().replace(' ', '-')} "
            f"--source . --region me-central1 --allow-unauthenticated"
        )
    else:
        cmd = "npx firebase deploy --only hosting --non-interactive"

    result = await exec_mgr.execute_task({
        "name": "deploy_web",
        "type": "backend_deploy",
        "command": enforce_user_space(cmd),
        "timeout": 300,
    }, requires_macincloud=False)

    success = result.get("exit_code", 1) == 0
    url = _extract_deploy_url(result.get("stdout", ""))

    return {
        "success": success,
        "url": url,
        "method": "api",
    }


def _extract_deploy_url(stdout: str) -> Optional[str]:
    """Extract deployment URL from command output."""
    for line in stdout.split("\n"):
        line = line.strip()
        if "https://" in line:
            # Find the URL
            start = line.index("https://")
            end = len(line)
            for char_idx in range(start, len(line)):
                if line[char_idx] in (" ", "\t", "\n", '"', "'"):
                    end = char_idx
                    break
            return line[start:end]
    return None


# ═══════════════════════════════════════════════════════════════════
# §4.7.1 Android Deployment
# ═══════════════════════════════════════════════════════════════════


async def _deploy_android(
    state: PipelineState,
    stack: TechStack,
    exec_mgr: ExecutionModeManager,
) -> dict:
    """Deploy Android via provider chain.

    Spec: §4.7.1
    Chain: Google Play API → Firebase App Distribution → Airlock (Telegram)
    Force via: ANDROID_DELIVERY_PROVIDER=playstore|firebase|airlock
    """
    blueprint_data = state.s2_output or {}
    artifacts = (state.s4_output or {}).get("artifacts", {})
    package_name = state.project_metadata.get(
        "package_name",
        blueprint_data.get("package_name", ""),
    )
    release_notes = blueprint_data.get("release_notes", f"Version update — {state.project_id}")

    # Find artifact path
    artifact_path = "app-release.aab"
    artifact_type = "aab"
    for platform_key in ("android", stack.value):
        art = artifacts.get(platform_key, {})
        if art.get("path"):
            artifact_path = art["path"]
            artifact_type = "apk" if artifact_path.endswith(".apk") else "aab"
            break

    try:
        from factory.delivery.android_delivery_chain import deliver_android
        result = await deliver_android(
            artifact_path=artifact_path,
            state=state,
            package_name=package_name,
            release_notes=release_notes,
            track="internal",
            artifact_type=artifact_type,
        )
        return {
            "success": result.success,
            "method": result.method,
            "provider": result.provider,
            "track": result.track,
            "manual_upload": result.manual_upload_required,
            "firebase_url": result.firebase_url,
            "airlock_delivered": result.airlock_delivered,
            "error": result.error,
        }
    except Exception as e:
        logger.error(f"[{state.project_id}] Android delivery chain error: {e}")
        # Hard fallback to Airlock
        airlock_result = await airlock_deliver(
            state=state,
            platform="android",
            binary_path=artifact_path,
            error=str(e),
        )
        return {
            "success": True,
            "method": "airlock_telegram",
            "manual_upload": True,
            "airlock": airlock_result,
        }


# ═══════════════════════════════════════════════════════════════════
# §4.7.2 iOS Deployment
# ═══════════════════════════════════════════════════════════════════


async def _deploy_ios(
    state: PipelineState,
    stack: TechStack,
    exec_mgr: ExecutionModeManager,
) -> dict:
    """Deploy iOS via provider chain.

    Spec: §4.7.2, §4.7.4 (FIX-21)
    Chain: App Store Connect API → Fastlane → Firebase App Distribution → Airlock
    Force via: IOS_DELIVERY_PROVIDER=appstore|fastlane|firebase|airlock
    """
    blueprint_data = state.s2_output or {}
    artifacts = (state.s4_output or {}).get("artifacts", {})
    bundle_id = state.project_metadata.get(
        "bundle_id",
        blueprint_data.get("bundle_id", ""),
    )
    release_notes = blueprint_data.get("release_notes", f"Version update — {state.project_id}")

    # Find IPA path
    ipa_path = "build/export/App.ipa"
    for platform_key in ("ios", stack.value):
        art = artifacts.get(platform_key, {})
        if art.get("path") and art["path"].endswith(".ipa"):
            ipa_path = art["path"]
            break

    try:
        from factory.delivery.ios_delivery_chain import deliver_ios
        result = await deliver_ios(
            ipa_path=ipa_path,
            state=state,
            bundle_id=bundle_id,
            release_notes=release_notes,
            target="testflight",
        )
        return {
            "success": result.success,
            "method": result.method,
            "provider": result.provider,
            "manual_upload": result.manual_upload_required,
            "testflight_url": result.testflight_url,
            "firebase_url": result.firebase_url,
            "airlock_delivered": result.airlock_delivered,
            "error": result.error,
        }
    except Exception as e:
        logger.error(f"[{state.project_id}] iOS delivery chain error: {e}")
        # Hard fallback to Airlock
        airlock_result = await airlock_deliver(
            state=state,
            platform="ios",
            binary_path=ipa_path,
            error=str(e),
        )
        return {
            "success": True,
            "method": "airlock_telegram",
            "manual_upload": True,
            "airlock": airlock_result,
        }


# Register with DAG (replaces stub)
register_stage_node("s6_deploy", s6_deploy_node)