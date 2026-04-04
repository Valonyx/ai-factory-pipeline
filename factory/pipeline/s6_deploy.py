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
    """Deploy Android via Google Play API (service account, no UI).

    Spec: §4.7.1
    Fallback: Airlock binary delivery via Telegram.
    """
    package_name = state.project_metadata.get("package_name", "")

    # Step 1: Sign the AAB
    sign_result = await exec_mgr.execute_task({
        "name": "sign_android",
        "type": "build",
        "command": enforce_user_space(
            "jarsigner -verbose -sigalg SHA256withRSA -digestalg SHA-256 "
            "-keystore release.keystore app-release-unsigned.apk alias_name"
        ),
    }, requires_macincloud=False)

    # Step 2: Upload via Google Play API
    upload_result = await exec_mgr.execute_task({
        "name": "upload_play_store",
        "type": "backend_deploy",
        "command": enforce_user_space(
            f"npx google-play-cli upload "
            f"--package-name {package_name} "
            f"--track internal --aab app-release.aab"
        ),
    }, requires_macincloud=False)

    if upload_result.get("exit_code", 1) != 0:
        # Airlock fallback: deliver binary via Telegram
        logger.warning(
            f"[{state.project_id}] Google Play upload failed, activating Airlock"
        )
        airlock_result = await airlock_deliver(
            state=state,
            platform="android",
            binary_path="app-release.aab",
            error=upload_result.get("stderr", "")[:500],
        )
        return {
            "success": True,
            "method": "airlock_telegram",
            "manual_upload": True,
            "airlock": airlock_result,
        }

    return {"success": True, "method": "api", "track": "internal"}


# ═══════════════════════════════════════════════════════════════════
# §4.7.2 iOS Deployment
# ═══════════════════════════════════════════════════════════════════


async def _deploy_ios(
    state: PipelineState,
    stack: TechStack,
    exec_mgr: ExecutionModeManager,
) -> dict:
    """Deploy iOS via Transporter CLI (no App Store Connect UI).

    Spec: §4.7.2, §4.7.4 (FIX-21)
    Uses 5-step submission protocol with retry logic.
    Fallback: Airlock binary delivery via Telegram.
    """
    errors: list[str] = []

    # Execute iOS submission steps (FIX-21 protocol)
    for step in IOS_SUBMISSION_STEPS:
        import asyncio

        for attempt in range(step["max_retries"]):
            result = await exec_mgr.execute_task({
                "name": f"ios_{step['name']}",
                "type": "ios_build",
                "command": enforce_user_space(step["command"]),
                "timeout": step["timeout"],
            }, requires_macincloud=True)

            if result.get("exit_code", 1) == 0:
                break

            # Retry with backoff
            if attempt < step["max_retries"] - 1:
                backoff = step["backoff_base"] * (attempt + 1)
                logger.info(
                    f"[{state.project_id}] iOS {step['name']} retry "
                    f"{attempt + 1}/{step['max_retries']}, backoff {backoff}s"
                )
                await asyncio.sleep(min(backoff, 5))  # Cap for dry-run
        else:
            # All retries exhausted
            error_msg = (
                f"iOS {step['name']} failed after "
                f"{step['max_retries']} retries: "
                f"{result.get('stderr', '')[:300]}"
            )
            errors.append(error_msg)

            # For non-polling steps, halt and use Airlock
            if step["name"] != "poll_processing":
                logger.warning(
                    f"[{state.project_id}] iOS deploy failed at "
                    f"{step['name']}, activating Airlock"
                )
                airlock_result = await airlock_deliver(
                    state=state,
                    platform="ios",
                    binary_path="build/export/App.ipa",
                    error=error_msg,
                )
                return {
                    "success": True,
                    "method": "airlock_telegram",
                    "manual_upload": True,
                    "failed_step": step["name"],
                    "airlock": airlock_result,
                }

    return {
        "success": True,
        "method": "api",
        "status": "processing",
        "steps_completed": len(IOS_SUBMISSION_STEPS),
    }


# Register with DAG (replaces stub)
register_stage_node("s6_deploy", s6_deploy_node)