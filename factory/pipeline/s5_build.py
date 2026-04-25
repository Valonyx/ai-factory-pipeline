"""
AI Factory Pipeline v5.8 — S5 Build Node

Implements:
  - §4.5 S5 Build (compile using Cloud/Local/Hybrid mode)
  - §4.5.1 CLI build path (React Native, Swift, Kotlin, Python)
  - §4.5.2 GUI automation build path (FlutterFlow, Unity) — stub
  - Phase 1: Write files to workspace
  - Phase 2: Install dependencies
  - Phase 3: Build (stack-specific)
  - Phase 4: Collect artifacts

Spec Authority: v5.8 §4.5, §4.5.1, §4.5.2
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    PipelineState,
    Stage,
    TechStack,
)
from factory.core.roles import call_ai
from factory.core.execution import ExecutionModeManager, _get_project_workspace
from factory.core.user_space import enforce_user_space
from factory.pipeline.graph import pipeline_node, register_stage_node
from factory.pipeline.stage_chain import inject_chain_context as _inject_cc

logger = logging.getLogger("factory.pipeline.s5_build")


# ═══════════════════════════════════════════════════════════════════
# Stack Build Configuration
# ═══════════════════════════════════════════════════════════════════

DEPENDENCY_COMMANDS: dict[TechStack, list[str]] = {
    TechStack.FLUTTERFLOW:    ["flutter pub get"],
    TechStack.REACT_NATIVE:   ["npm ci", "npx expo install"],
    TechStack.SWIFT:          ["swift package resolve"],
    TechStack.KOTLIN:         ["./gradlew dependencies"],
    TechStack.UNITY:          [],  # Unity resolves packages internally
    TechStack.PYTHON_BACKEND: ["pip install --user -r requirements.txt"],
}

CLI_BUILD_COMMANDS: dict[TechStack, dict[str, str]] = {
    TechStack.REACT_NATIVE: {
        "android": "npx eas build --platform android --profile preview --non-interactive",
        "ios": "npx eas build --platform ios --profile preview --non-interactive",
        "web": "npx expo export --platform web",
    },
    TechStack.SWIFT: {
        "ios": (
            "xcodebuild -scheme App "
            "-destination 'generic/platform=iOS' "
            "-archivePath build/App.xcarchive archive"
        ),
    },
    TechStack.KOTLIN: {
        "android": "./gradlew assembleRelease",
    },
    TechStack.PYTHON_BACKEND: {
        "web": "docker build -t app . && echo 'Docker build success'",
    },
}

# Which stacks require Mac and/or GUI automation
STACK_BUILD_REQUIREMENTS: dict[TechStack, dict[str, bool]] = {
    TechStack.FLUTTERFLOW:    {"requires_mac": True, "requires_gui": True},
    TechStack.REACT_NATIVE:   {"requires_mac": False, "requires_gui": False},
    TechStack.SWIFT:          {"requires_mac": True, "requires_gui": False},
    TechStack.KOTLIN:         {"requires_mac": False, "requires_gui": False},
    TechStack.UNITY:          {"requires_mac": True, "requires_gui": True},
    TechStack.PYTHON_BACKEND: {"requires_mac": False, "requires_gui": False},
}


# ═══════════════════════════════════════════════════════════════════
# §4.5 S5 Build Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S5_BUILD)
async def s5_build_node(state: PipelineState) -> PipelineState:
    """S4: Build — compile the project using Cloud/Local/Hybrid mode.

    Spec: §4.5
    Phase 1: Write files to workspace
    Phase 2: Install dependencies
    Phase 3: Build (CLI or GUI-automated)
    Phase 4: Collect artifacts

    Cost target: <$0.50
    """
    import os as _os
    _is_ci = (
        _os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
        or _os.getenv("PIPELINE_ENV", "").lower() == "ci"
        or _os.getenv("AI_PROVIDER", "").lower() == "mock"
    )

    blueprint_data = state.s2_output or {}
    files = (state.s4_output or {}).get("generated_files", {})
    stack_value = blueprint_data.get("selected_stack", "flutterflow")

    try:
        stack = TechStack(stack_value)
    except ValueError:
        stack = TechStack.FLUTTERFLOW

    target_platforms = blueprint_data.get("target_platforms", ["ios", "android"])

    reqs = STACK_BUILD_REQUIREMENTS.get(stack, {})
    requires_mac = reqs.get("requires_mac", False)
    requires_gui = reqs.get("requires_gui", False)

    exec_mgr = ExecutionModeManager(state)
    build_start = datetime.now(timezone.utc)

    # ══════════════════════════════════════════
    # Phase 1: Write files to workspace (always runs — even in DRY_RUN)
    # ══════════════════════════════════════════
    write_errors = []
    for file_path, content in files.items():
        result = await exec_mgr.execute_task({
            "name": f"write_{file_path}",
            "type": "file_write",
            "command": f"mkdir -p $(dirname {file_path}) && cat > {file_path}",
            "content": content,
        }, requires_macincloud=False)
        if result.get("exit_code", 0) != 0:
            write_errors.append(file_path)

    if write_errors:
        logger.warning(
            f"[{state.project_id}] S4: Failed to write {len(write_errors)} files"
        )

    # ══════════════════════════════════════════
    # Phase 2+3: Dependency install + Build
    # Skip in DRY_RUN / CI — no real toolchain available.
    # ══════════════════════════════════════════
    if _is_ci:
        logger.info(f"[{state.project_id}] S5: DRY_RUN — skipping build, source_only pass")
        build_result: dict = {"success": True, "source_only": True, "artifacts": {}, "errors": []}
        dep_errors: list = []
    else:
        # Phase 2: Install dependencies
        dep_errors = []
        for cmd in DEPENDENCY_COMMANDS.get(stack, []):
            result = await exec_mgr.execute_task({
                "name": f"deps_{stack.value}",
                "type": "dependency_install",
                "command": enforce_user_space(cmd),
            }, requires_macincloud=requires_mac)

            if result.get("exit_code", 0) != 0:
                dep_errors.append({
                    "command": cmd,
                    "error": result.get("stderr", "")[:500],
                })

        # Phase 3: Build
        if requires_gui:
            build_result = await _build_gui(state, stack, exec_mgr)
        else:
            build_result = await _build_cli(
                state, stack, target_platforms, exec_mgr, requires_mac,
            )

    # ══════════════════════════════════════════
    # Phase 4: Collect artifacts
    # ══════════════════════════════════════════
    build_duration = (
        datetime.now(timezone.utc) - build_start
    ).total_seconds()

    source_only = build_result.get("source_only", False)
    state.s5_output = {
        "build_success": build_result.get("success", False),
        "source_only": source_only,
        "artifacts": build_result.get("artifacts", {}),
        "execution_mode": state.execution_mode.value,
        "build_duration_seconds": round(build_duration, 1),
        "errors": build_result.get("errors", []),
        "dependency_errors": dep_errors,
        "files_written": len(files) - len(write_errors),
        "workspace_path": _get_project_workspace(
            state.project_id,
            app_name=(state.s0_output or {}).get("app_name") or state.idea_name,
        ),
    }

    # ── Issue 11 re-verify: store stage insight ──
    try:
        from factory.core.stage_enrichment import store_stage_insight
        await store_stage_insight(
            "s5_build", state,
            fact=(
                f"Build: {state.s5_output.get('build_status', 'source_only' if state.s5_output.get('source_only') else 'attempted')}. "
                f"Platforms: {state.s5_output.get('build_platforms', [])}"
            ),
            category="build",
        )
    except Exception as _si_err:
        import logging as _l
        _l.getLogger("factory.pipeline.s5_build").debug(
            f"[{state.project_id}] S5 store_stage_insight failed (non-fatal): {_si_err}"
        )

    # Mother Memory: full S5 output snapshot → fan-out to ALL backends
    try:
        from factory.memory.mother_memory import store_pipeline_state_snapshot
        await store_pipeline_state_snapshot(
            state.project_id, "s5_build", state.s5_output
        )
    except Exception:
        pass

    # War Room for build failures (skip for source_only — no binary to fix)
    if not build_result.get("success") and build_result.get("errors") and not source_only:
        for error in build_result["errors"][:3]:
            wr_result = await _attempt_build_fix(state, error, exec_mgr)
            if wr_result.get("resolved"):
                state.s5_output["build_success"] = True
                break

    # Notify operator of workspace location so they can see generated files
    workspace = state.s5_output["workspace_path"]
    files_written = state.s5_output["files_written"]
    if source_only:
        from factory.telegram.notifications import send_telegram_message
        await send_telegram_message(
            state.operator_id,
            f"📂 *Source code ready* — {files_written} file(s) written to:\n"
            f"`{workspace}`\n\n"
            f"Build environment ({stack.value}) not available locally.\n"
            f"Source code will be zipped and sent to you in the next step.\n"
            f"Set `MACINCLOUD_API_KEY` to enable automated builds.",
        )
    elif files_written > 0:
        from factory.telegram.notifications import send_telegram_message
        await send_telegram_message(
            state.operator_id,
            f"📂 *Project files*: {files_written} file(s) at `{workspace}`",
        )

    logger.info(
        f"[{state.project_id}] S5 Build: "
        f"success={state.s5_output['build_success']}, source_only={source_only}, "
        f"duration={build_duration:.1f}s, "
        f"artifacts={len(state.s5_output.get('artifacts', {}))}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# §4.5.1 CLI Build Path
# ═══════════════════════════════════════════════════════════════════


async def _build_cli(
    state: PipelineState,
    stack: TechStack,
    target_platforms: list[str],
    exec_mgr: ExecutionModeManager,
    requires_mac: bool,
) -> dict:
    """CLI-based build for React Native, Swift, Kotlin, Python.

    Spec: §4.5.1
    """
    commands = CLI_BUILD_COMMANDS.get(stack, {})
    artifacts: dict = {}
    errors: list[str] = []

    for platform, cmd in commands.items():
        # Only build for targeted platforms (or web)
        if platform not in target_platforms and platform != "web":
            continue

        is_ios_build = platform == "ios"
        result = await exec_mgr.execute_task({
            "name": f"build_{platform}",
            "type": "ios_build" if is_ios_build else "build",
            "command": enforce_user_space(cmd),
            "timeout": 1200,  # 20 min max
        }, requires_macincloud=requires_mac and is_ios_build)

        if result.get("exit_code", 0) == 0:
            artifacts[platform] = {
                "status": "success",
                "output": result.get("stdout", "")[-500:],
            }
        else:
            errors.append(
                f"{platform}: {result.get('stderr', '')[-1000:]}"
            )

    return {
        "success": len(errors) == 0,
        "artifacts": artifacts,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════════
# §4.5.2 GUI Automation Build Path
# ═══════════════════════════════════════════════════════════════════


async def _build_gui(
    state: PipelineState,
    stack: TechStack,
    exec_mgr: ExecutionModeManager,
) -> dict:
    """GUI-automated build for FlutterFlow and Unity.

    Spec: §4.5.2
    Uses 5-layer GUI automation stack (OmniParser + UI-TARS).
    Provider cascade: MacinCloud SSH → local pyautogui → GitHub Actions.
    """
    blueprint_data = state.s2_output or {}
    target_platforms = blueprint_data.get("target_platforms", ["ios", "android"])
    version = blueprint_data.get("version", "1.0.0")

    # Try build_with_chain first (GitHub Actions / Codemagic for CI)
    try:
        from factory.infra.build_chain import build_with_chain
        result = await build_with_chain(
            stack=stack.value,
            platforms=target_platforms,
            version=version,
            project_id=state.project_id,
            state=state,
            requires_mac=True,
        )
        if result.success:
            logger.info(
                f"[{state.project_id}] S4 GUI build via {result.provider}: success"
            )
            return {
                "success": True,
                "artifacts": result.artifacts,
                "errors": [],
                "provider": result.provider,
            }
        # CI build failed — try local UI automation
        logger.warning(
            f"[{state.project_id}] CI build failed ({result.error}), "
            f"trying local UI automation"
        )
    except Exception as e:
        logger.warning(f"[{state.project_id}] build_with_chain error: {e}")

    # Local UI-TARS automation (MacinCloud or local pyautogui)
    try:
        from factory.automation.ui_tars import UITARSAutomation
        from factory.infra.macincloud_client import MacinCloudClient

        mac_client = None
        try:
            import os
            if os.getenv("MACINCLOUD_API_KEY"):
                mac_client = MacinCloudClient()
                if not await mac_client.connect():
                    mac_client = None
        except Exception:
            mac_client = None

        automation = UITARSAutomation(macincloud=mac_client)
        intent = f"Build {stack.value} app for {', '.join(target_platforms)}"
        auto_result = await automation.execute_with_retry(
            intent=intent,
            state=state,
            max_retries=2,
        )

        if mac_client:
            await mac_client.disconnect()

        return {
            "success": auto_result.success,
            "artifacts": {
                stack.value: {
                    "status": "success" if auto_result.success else "failed",
                    "provider": auto_result.provider,
                    "steps": f"{auto_result.steps_executed}/{auto_result.steps_total}",
                }
            },
            "errors": [auto_result.error] if auto_result.error else [],
            "provider": auto_result.provider,
        }

    except Exception as e:
        logger.error(f"[{state.project_id}] UI automation failed: {e}")
        # Final fallback: no binary produced — source code is ready but not built
        return {
            "success": False,
            "source_only": True,   # Tells S6 to deliver source zip, not binary
            "artifacts": {
                stack.value: {
                    "status": "pending_manual_build",
                    "note": (
                        f"GUI build requires {stack.value} environment. "
                        f"Set MACINCLOUD_API_KEY or push to GitHub to trigger CI."
                    ),
                }
            },
            "errors": [
                f"{stack.value} build skipped — no build environment available. "
                f"Source code written to workspace. Set MACINCLOUD_API_KEY to enable."
            ],
        }


async def _attempt_build_fix(
    state: PipelineState,
    error: str,
    exec_mgr: ExecutionModeManager,
) -> dict:
    """Attempt War Room L1 fix for build errors.

    Spec: §4.5 Phase 4 error recovery
    """
    _fix_base = (
        f"Build error:\n{error[:2000]}\n\n"
        f"Suggest a fix command or file change. "
        f"Return JSON: {{\"fix_type\": \"command|file\", "
        f"\"fix\": \"...\", \"resolved\": true/false}}"
    )
    fix = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=_inject_cc(_fix_base, state, current_stage="s5_build", compact=True),
        state=state,
        action="general",
    )

    try:
        result = json.loads(fix)
        if result.get("resolved") and result.get("fix_type") == "command":
            await exec_mgr.execute_task({
                "name": "build_fix",
                "type": "build",
                "command": enforce_user_space(result["fix"]),
            }, requires_macincloud=False)
        return result
    except (json.JSONDecodeError, Exception):
        return {"resolved": False}


# Register with DAG (replaces stub)
register_stage_node("s5_build", s5_build_node)

def _get_target_stores(stack: TechStack, platforms: list[str] = None) -> list[str]:
    """Return the app stores targeted for a given stack and platforms.

    Spec: §4.5 Build output routing
    """
    # Default platforms based on stack
    if platforms is None:
        if stack == TechStack.SWIFT:
            platforms = ["ios"]
        elif stack == TechStack.KOTLIN:
            platforms = ["android"]
        elif stack == TechStack.PYTHON_BACKEND:
            platforms = ["web"]
        elif stack == TechStack.FLUTTERFLOW:
            platforms = ["ios", "android"]
        elif stack == TechStack.REACT_NATIVE:
            platforms = ["ios", "android"]
        else:
            platforms = []

    stores = []
    if "ios" in platforms or stack == TechStack.SWIFT:
        stores.append("App Store")
    if "android" in platforms or stack == TechStack.KOTLIN:
        stores.append("Google Play")
    if stack == TechStack.PYTHON_BACKEND or "web" in platforms:
        stores.append("Cloud Run")
    # FlutterFlow always targets both
    if stack == TechStack.FLUTTERFLOW:
        if "App Store" not in stores:
            stores.append("App Store")
        if "Google Play" not in stores:
            stores.append("Google Play")
    return list(dict.fromkeys(stores))  # deduplicate preserving order
