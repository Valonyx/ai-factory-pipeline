"""
AI Factory Pipeline v5.6 — S3 Code Generation Node

Implements:
  - §4.4 S3 CodeGen (full generation + retry fix mode)
  - Engineer generates all code files from Blueprint
  - Quick Fix validates generated code
  - §4.4.2 CI/CD configuration generation
  - War Room targeted fix on retry (§2.2.8)

Spec Authority: v5.6 §4.4, §4.4.2
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
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s3_codegen")


# ═══════════════════════════════════════════════════════════════════
# §4.4 S3 CodeGen Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S3_CODEGEN)
async def s3_codegen_node(state: PipelineState) -> PipelineState:
    """S3: CodeGen — generate all project files for the selected stack.

    Spec: §4.4
    First run: full generation from Blueprint.
    Retry (from S5 test failures): targeted fixes via War Room.

    Cost target: <$3.00
    """
    blueprint_data = state.s2_output or {}

    # ── MODIFY mode: generate targeted diffs instead of full files ──
    from factory.core.state import PipelineMode
    if state.pipeline_mode == PipelineMode.MODIFY:
        return await _s3_modify_codegen(state, blueprint_data)

    # Retry when: retry_count > 0 with prior failures, or previous_stage was S5_TEST
    s5_has_failures = bool(
        state.s5_output and not state.s5_output.get("passed", True)
        and state.s5_output.get("failures")
    )
    is_retry = (
        state.retry_count > 0 and s5_has_failures
    ) or state.previous_stage == Stage.S5_TEST

    if is_retry:
        state = await _codegen_retry_fix(state)
    else:
        state = await _codegen_full_generation(state, blueprint_data)

    return state


# ═══════════════════════════════════════════════════════════════════
# Full Generation Mode
# ═══════════════════════════════════════════════════════════════════


def _build_codegen_prompt(
    stack: TechStack,
    app_name: str,
    screens: list,
    data_model: list,
    api_endpoints: list,
    auth_method: str,
    blueprint_data: dict,
) -> str:
    """Build a stack-specific, detailed codegen prompt for the Engineer.

    Each stack gets targeted instructions for conventions, file structure,
    and must-have patterns — reducing hallucinations and improving output quality.
    """
    screens_json = json.dumps(screens[:10], indent=2)[:2500]
    model_json = json.dumps(data_model, indent=2)[:1800]
    api_json = json.dumps(api_endpoints, indent=2)[:1200]
    colors = json.dumps(blueprint_data.get("color_palette", {}))
    typography = blueprint_data.get("typography", {})
    features = blueprint_data.get("features_must", [])

    base = (
        f"App name: {app_name}\n"
        f"Screens: {screens_json}\n"
        f"Data model: {model_json}\n"
        f"API endpoints: {api_json}\n"
        f"Auth: {auth_method}\n"
        f"Colors: {colors}\n"
        f"Features: {features}\n\n"
        f"Return ONLY a raw JSON object. No markdown. No code fences. No explanation.\n"
        f"Each key is a relative file path. Each value is the complete raw file content.\n"
        f"Example format:\n"
        f'{{"lib/main.dart":"import \'package:flutter/material.dart\';\\nvoid main(){{runApp(MyApp());}}", '
        f'"pubspec.yaml":"name: myapp\\nversion: 1.0.0"}}\n'
        f"IMPORTANT: file content values must be raw code strings — NOT wrapped in ```fences```.\n"
        f"Include ALL necessary files (entry point, screens, models, config, manifest).\n"
    )

    if stack == TechStack.FLUTTERFLOW:
        return (
            f"Generate complete Flutter/FlutterFlow Dart files.\n\n"
            f"Conventions:\n"
            f"- Entry: lib/main.dart with MaterialApp\n"
            f"- Each screen: lib/screens/<name>_screen.dart as StatefulWidget\n"
            f"- Models: lib/models/<name>.dart with fromJson/toJson\n"
            f"- Services: lib/services/firestore_service.dart using cloud_firestore\n"
            f"- Theme: lib/theme.dart with ThemeData matching color palette\n"
            f"- pubspec.yaml: include flutter, firebase_core, cloud_firestore, firebase_auth\n"
            f"- Use const constructors where possible. Follow Material Design 3.\n\n"
            + base
        )

    elif stack == TechStack.REACT_NATIVE:
        bundle_id = blueprint_data.get("bundle_id", "com.factory.app")
        return (
            f"Generate complete React Native + Expo TypeScript project.\n\n"
            f"Conventions:\n"
            f"- App.tsx: NavigationContainer with Stack/Tab navigators\n"
            f"- src/screens/<Name>Screen.tsx per screen\n"
            f"- src/components/ for reusable UI\n"
            f"- src/services/firebase.ts for Firebase init\n"
            f"- src/store/ using Zustand for state management\n"
            f"- package.json: expo ~50, react-native ~0.74, @react-navigation/native\n"
            f"- tsconfig.json with strict mode\n"
            f"- app.json: bundleIdentifier={bundle_id}\n"
            f"- Use StyleSheet.create for all styles. Avoid inline styles.\n\n"
            + base
        )

    elif stack == TechStack.SWIFT:
        bundle_id = blueprint_data.get("bundle_id", "com.factory.app")
        return (
            f"Generate complete SwiftUI iOS project files.\n\n"
            f"Conventions:\n"
            f"- <AppName>App.swift: @main App entry with WindowGroup\n"
            f"- Views/<Name>View.swift per screen as SwiftUI View struct\n"
            f"- Models/<Name>.swift: Codable structs\n"
            f"- ViewModels/<Name>ViewModel.swift: @Observable class (Swift 5.9+)\n"
            f"- Services/FirebaseService.swift: FirebaseFirestore calls\n"
            f"- Services/AuthService.swift: FirebaseAuth calls\n"
            f"- Package.swift or Podfile: FirebaseFirestore, FirebaseAuth\n"
            f"- Info.plist: NSFaceIDUsageDescription, privacy keys\n"
            f"- Use async/await throughout. Target iOS 17+.\n"
            f"- Apply MVVM pattern strictly.\n\n"
            + base
        )

    elif stack == TechStack.KOTLIN:
        package = blueprint_data.get("package_name", "com.factory.app")
        return (
            f"Generate complete Android Kotlin project files.\n\n"
            f"Package: {package}\n"
            f"Conventions:\n"
            f"- app/src/main/java/{package.replace('.', '/')}/MainActivity.kt\n"
            f"- ui/<feature>/<Name>Fragment.kt and <Name>ViewModel.kt per screen\n"
            f"- data/models/<Name>.kt: data classes\n"
            f"- data/repository/<Name>Repository.kt: Firestore operations\n"
            f"- di/AppModule.kt: Hilt dependency injection\n"
            f"- app/build.gradle: compileSdk 34, Firebase BOM, Hilt, Navigation\n"
            f"- AndroidManifest.xml: INTERNET permission, activities\n"
            f"- res/values/colors.xml, strings.xml, themes.xml\n"
            f"- Use Jetpack Compose for UI. Coroutines + Flow for async.\n"
            f"- Apply MVVM + Repository pattern.\n\n"
            + base
        )

    elif stack == TechStack.UNITY:
        return (
            f"Generate complete Unity C# project files.\n\n"
            f"Conventions:\n"
            f"- Assets/Scripts/GameManager.cs: MonoBehaviour singleton\n"
            f"- Assets/Scripts/UI/<Name>UIController.cs per screen\n"
            f"- Assets/Scripts/Data/<Name>Data.cs: [Serializable] data classes\n"
            f"- Assets/Scripts/Services/FirebaseService.cs: Firebase Realtime DB\n"
            f"- Assets/Scripts/Services/AuthService.cs: Firebase Authentication\n"
            f"- ProjectSettings/ProjectVersion.txt\n"
            f"- Packages/manifest.json: com.unity.firebase.app, analytics\n"
            f"- Use UnityEngine.UIElements or TextMeshPro for UI.\n"
            f"- Implement singleton GameManager with DontDestroyOnLoad.\n"
            f"- All MonoBehaviours: null checks before API calls.\n\n"
            + base
        )

    elif stack == TechStack.PYTHON_BACKEND:
        return (
            f"Generate complete Python FastAPI backend project.\n\n"
            f"Conventions:\n"
            f"- main.py: FastAPI app, CORS, health endpoint\n"
            f"- routers/<name>.py: APIRouter per domain\n"
            f"- models/<name>.py: Pydantic v2 BaseModel\n"
            f"- services/<name>.py: business logic\n"
            f"- db/firebase.py: Firestore client init\n"
            f"- db/models.py: Firestore collection helpers\n"
            f"- requirements.txt: fastapi, uvicorn, firebase-admin, pydantic>=2\n"
            f"- Dockerfile: python:3.11-slim, non-root user, PORT env var\n"
            f"- .env.example: FIREBASE_CREDENTIALS, PROJECT_ID\n"
            f"- Use async def for all endpoints. Include OpenAPI docstrings.\n"
            f"- Auth: Firebase ID token verification middleware.\n\n"
            + base
        )

    # Fallback for unknown stacks
    return (
        f"Generate ALL code files for a {stack.value} project.\n\n"
        + base
    )


async def _codegen_full_generation(
    state: PipelineState, blueprint_data: dict,
) -> PipelineState:
    """Generate all project files from Blueprint.

    Spec: §4.4 (first run path)
    Step 1: Generate code files
    Step 2: Generate security rules (if auth)
    Step 3: Generate CI/CD configuration
    Step 4: Quick Fix validation pass
    """
    stack_value = blueprint_data.get("selected_stack", "flutterflow")
    try:
        stack = TechStack(stack_value)
    except ValueError:
        stack = TechStack.FLUTTERFLOW

    screens = blueprint_data.get("screens", [])
    data_model = blueprint_data.get("data_model", [])
    api_endpoints = blueprint_data.get("api_endpoints", [])
    auth_method = blueprint_data.get("auth_method", "email")
    app_name = blueprint_data.get("app_name", state.project_id)

    # ── Step 1: Generate code files ──
    from factory.core.stage_enrichment import enrich_prompt
    code_prompt = _build_codegen_prompt(
        stack=stack,
        app_name=app_name,
        screens=screens,
        data_model=data_model,
        api_endpoints=api_endpoints,
        auth_method=auth_method,
        blueprint_data=blueprint_data,
    )
    code_prompt = await enrich_prompt(
        "s3_codegen", code_prompt, state,
        scout=True,
    )

    result = await call_ai(
        role=AIRole.ENGINEER,
        prompt=code_prompt,
        state=state,
        action="write_code",
    )

    try:
        files = json.loads(result)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code fences (common with Gemini/free-tier)
        files = _extract_json_from_response(result)
        if not files:
            logger.warning(
                f"[{state.project_id}] S3: Failed to parse Engineer JSON, "
                f"creating minimal scaffold"
            )
            files = _create_minimal_scaffold(stack, app_name)
        else:
            logger.info(
                f"[{state.project_id}] S3: Extracted {len(files)} files from "
                f"markdown-wrapped AI response"
            )

    # ── Sanitize: strip markdown fences from file content values ──
    # Models sometimes wrap values in ```lang\n...\n``` inside the JSON
    files = _sanitize_file_contents(files)

    # ── Validate: if only 1 tiny file was generated it's a stub, not real code ──
    total_content_bytes = sum(len(v) for v in files.values() if isinstance(v, str))
    if total_content_bytes < 300 or (len(files) == 1 and "main.dart" in files and total_content_bytes < 500):
        logger.warning(
            f"[{state.project_id}] S3: Generated content too small "
            f"({total_content_bytes} bytes, {len(files)} files) — "
            f"regenerating with explicit file-by-file prompts"
        )
        files = await _generate_files_individually(state, stack, app_name, blueprint_data)

    # ── Step 2: Generate security rules (if auth) ──
    if auth_method and auth_method != "none":
        rules = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Generate Firestore security rules for this data model:\n"
                f"{json.dumps(data_model, indent=2)[:3000]}\n\n"
                f"Auth method: {auth_method}\n"
                f"Requirements: Users can only read/write their own data. "
                f"Public collections are read-only for non-auth users.\n"
                f"Return ONLY the firestore.rules file content."
            ),
            state=state,
            action="write_code",
        )
        files["firestore.rules"] = rules

    # ── Step 3: CI/CD configuration ──
    ci_files = await _generate_ci_config(state, stack, blueprint_data)
    files.update(ci_files)

    # ── Step 4: Quick Fix validation pass ──
    files = await _quick_fix_validation(state, files, stack)

    state.s3_output = {
        "generated_files": files,
        "file_count": len(files),
        "stack": stack.value,
        "generation_mode": "full",
    }

    logger.info(
        f"[{state.project_id}] S3 CodeGen complete: "
        f"{len(files)} files generated for {stack.value}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# Retry Fix Mode (from S5 test failures)
# ═══════════════════════════════════════════════════════════════════


async def _codegen_retry_fix(state: PipelineState) -> PipelineState:
    """Targeted fix mode when retrying from S5 test failures.

    Spec: §4.4 (retry path)
    Uses War Room escalation (L1→L2→L3) for each failure.
    """
    test_failures = (state.s5_output or {}).get("failures", [])
    existing_files = (state.s3_output or {}).get("generated_files", {})

    # Wire War Room hooks so L3 file rewrites persist into existing_files.
    # Save and restore prior hooks to avoid contaminating other callers.
    import factory.war_room.escalation as _esc
    _prev_runner   = _esc._test_runner
    _prev_writer   = _esc._file_writer
    _prev_executor = _esc._command_executor

    async def _file_writer(path: str, content: str) -> None:
        existing_files[path] = content

    async def _test_runner(context) -> bool:
        return True  # real test execution happens at S5

    async def _command_executor(command: str) -> dict:
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    from factory.war_room.escalation import set_fix_hooks
    set_fix_hooks(
        test_runner=_test_runner,
        file_writer=_file_writer,
        command_executor=_command_executor,
    )

    if not test_failures:
        logger.warning(f"[{state.project_id}] S3 retry but no failures to fix")
        return state

    fixed_count = 0
    unresolved = []

    for failure in test_failures:
        file_path = failure.get("file", "unknown")
        error = failure.get("error", "unknown error")
        severity = failure.get("severity", "normal")

        # War Room escalation
        fix_result = await _war_room_fix(
            state, file_path, error,
            existing_files.get(file_path, ""),
            existing_files,
        )

        if fix_result.get("resolved"):
            if fix_result.get("fixed_content"):
                existing_files[file_path] = fix_result["fixed_content"]
                fixed_count += 1
        else:
            unresolved.append({
                "file": file_path,
                "error": error,
                "severity": severity,
            })
            state.errors.append({
                "stage": "S3_CODEGEN",
                "type": "unresolved_war_room",
                "file": file_path,
                "error": error,
            })

    # Restore prior War Room hooks
    set_fix_hooks(
        test_runner=_prev_runner,
        file_writer=_prev_writer,
        command_executor=_prev_executor,
    )

    state.s3_output["generated_files"] = existing_files
    state.s3_output["generation_mode"] = "retry_fix"
    state.s3_output["fixes_applied"] = fixed_count
    state.s3_output["unresolved"] = unresolved

    logger.info(
        f"[{state.project_id}] S3 retry: {fixed_count} fixed, "
        f"{len(unresolved)} unresolved"
    )
    return state


async def _war_room_fix(
    state: PipelineState,
    file_path: str,
    error: str,
    file_content: str,
    all_files: Optional[dict] = None,
) -> dict:
    """War Room escalation for a single failure.

    Spec: §2.2.8
    L1: Quick Fix (Haiku) — direct fix attempt
    L2: Engineer (Sonnet) — deeper analysis with multi-file support
    L3: Delegates to war_room_escalate (Mother Memory + Telegram alert)

    Mother Memory: queries prior fixes before L1; stores pattern after success.
    """
    from factory.war_room.patterns import query_similar_errors, store_fix_pattern

    # ── Mother Memory: check prior fixes for this error ──
    prior_context = ""
    try:
        similar = await query_similar_errors(
            error, stack=getattr(state, "selected_stack", ""),
        )
        if similar:
            logger.info(
                f"[{state.project_id}] War Room: found {len(similar)} "
                f"prior fix(es) in Mother Memory"
            )
            prior_context = "\nPrior fixes for similar errors:\n" + "\n".join(
                f"- L{s.get('level', '?')}: {str(s.get('fix_applied', ''))[:200]}"
                for s in similar[:3]
            )
    except Exception:
        pass  # Mother Memory unavailable — continue without prior context

    # ── L1: Quick Fix attempt ──
    l1_result = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=(
            f"Fix this error in {file_path}:\n"
            f"Error: {error}\n\n"
            f"Current file content:\n{file_content[:4000]}\n"
            f"{prior_context}\n"
            f"Return the COMPLETE corrected file content. "
            f"If you cannot fix it, return exactly: CANNOT_FIX"
        ),
        state=state,
        action="write_code",
    )

    if l1_result and "CANNOT_FIX" not in l1_result:
        state.war_room_history.append({
            "level": 1,
            "error": error[:200],
            "file": file_path,
            "resolved": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        try:
            await store_fix_pattern(
                state, error_type="codegen",
                fix_description=l1_result[:500], success=True,
            )
        except Exception:
            pass
        return {"resolved": True, "fixed_content": l1_result, "level": 1}

    # ── L2: Engineer analysis with multi-file support ──
    l2_result = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"The Quick Fix couldn't resolve this error. Analyze deeper.\n\n"
            f"File: {file_path}\n"
            f"Error: {error}\n"
            f"File content:\n{file_content[:3000]}\n\n"
            f"Other project files available: "
            f"{list((all_files or {}).keys())[:20]}\n"
            f"{prior_context}\n"
            f"Return the COMPLETE corrected file content. "
            f"If the fix requires changes to other files, include them as "
            f"JSON: {{\"primary_fix\": \"content\", "
            f"\"secondary_fixes\": {{\"path\": \"content\"}}}}"
        ),
        state=state,
        action="write_code",
    )

    if l2_result and "CANNOT_FIX" not in l2_result:
        # Check if multi-file fix
        try:
            multi = json.loads(l2_result)
            if "primary_fix" in multi:
                for path, content in multi.get("secondary_fixes", {}).items():
                    if all_files and path in all_files:
                        all_files[path] = content
                fixed_content = multi["primary_fix"]
            else:
                fixed_content = l2_result
        except json.JSONDecodeError:
            fixed_content = l2_result

        state.war_room_history.append({
            "level": 2,
            "error": error[:200],
            "file": file_path,
            "resolved": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        try:
            await store_fix_pattern(
                state, error_type="codegen",
                fix_description=fixed_content[:500], success=True,
            )
        except Exception:
            pass
        return {"resolved": True, "fixed_content": fixed_content, "level": 2}

    # ── L3: Delegate to war_room_escalate for full handling ──
    # (Mother Memory pattern storage, Telegram operator alert, rewrite plan)
    from factory.war_room.war_room import war_room_escalate
    from factory.war_room.levels import WarRoomLevel
    try:
        result = await war_room_escalate(
            state,
            error=error,
            error_context={
                "type": "codegen",
                "file_path": file_path,
                "file_content": file_content,
                "files": all_files or {},
                "stage": "S3_CODEGEN",
            },
            current_level=WarRoomLevel.L3_WAR_ROOM,
        )
        state.war_room_history.append({
            "level": 3,
            "error": error[:200],
            "file": file_path,
            "resolved": result.get("resolved", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "resolved": result.get("resolved", False),
            "fixed_content": result.get("fix_applied", ""),
            "level": 3,
        }
    except Exception as e:
        logger.error(
            f"[{state.project_id}] War Room L3 unresolved: "
            f"{file_path} — {error[:100]} (escalation error: {e})"
        )
        state.war_room_history.append({
            "level": 3,
            "error": error[:200],
            "file": file_path,
            "resolved": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {"resolved": False, "level": 3}


# ═══════════════════════════════════════════════════════════════════
# §4.4 Quick Fix Validation Pass
# ═══════════════════════════════════════════════════════════════════


async def _quick_fix_validation(
    state: PipelineState,
    files: dict,
    stack: TechStack,
) -> dict:
    """Run Quick Fix validation on generated files.

    Spec: §4.4 Step 4
    Scans for obvious errors: syntax, missing imports, broken references.
    """
    # Prepare truncated file listing for validation
    file_summaries = {
        k: (v[:500] if isinstance(v, str) else str(v)[:500])
        for k, v in files.items()
    }

    validation_result = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=(
            f"Scan these {stack.value} files for obvious errors "
            f"(syntax, missing imports, broken references).\n\n"
            f"Files:\n{json.dumps(file_summaries, indent=2)[:6000]}\n\n"
            f"Return JSON: "
            f'[{{"file": "...", "error": "...", "fix": "..."}}]\n'
            f"Return empty list [] if no errors found."
        ),
        state=state,
        action="write_code",
    )

    try:
        errors = json.loads(validation_result)
        if not isinstance(errors, list):
            errors = []
        # Ensure each item is a dict (guard against bare string lists)
        errors = [e for e in errors if isinstance(e, dict)]
    except (json.JSONDecodeError, TypeError):
        errors = []

    for error_item in errors:
        file_path = error_item.get("file", "")
        if file_path in files:
            fixed = await call_ai(
                role=AIRole.QUICK_FIX,
                prompt=(
                    f"Fix this error in {file_path}:\n"
                    f"Error: {error_item.get('error', '')}\n"
                    f"Suggested fix: {error_item.get('fix', '')}\n\n"
                    f"Current content:\n{files[file_path][:4000]}\n\n"
                    f"Return the corrected file content ONLY."
                ),
                state=state,
                action="write_code",
            )
            if fixed:
                files[file_path] = fixed

    return files


# ═══════════════════════════════════════════════════════════════════
# §4.4.2 CI/CD Configuration Generation
# ═══════════════════════════════════════════════════════════════════


async def _generate_ci_config(
    state: PipelineState,
    stack: TechStack,
    blueprint_data: dict,
) -> dict[str, str]:
    """Generate CI/CD config files based on stack.

    Spec: §4.4.2
    """
    files: dict[str, str] = {}

    ci_prompts = {
        TechStack.FLUTTERFLOW: (
            "Generate GitHub Actions workflow for FlutterFlow project. "
            "Steps: checkout, flutter pub get, flutter build apk, "
            "flutter build ios --no-codesign. Return ONLY the YAML content."
        ),
        TechStack.REACT_NATIVE: (
            "Generate GitHub Actions for Expo React Native. "
            "Steps: checkout, npm ci, npx expo-doctor, "
            "eas build --platform all --non-interactive. Return ONLY YAML."
        ),
        TechStack.SWIFT: (
            "Generate GitHub Actions for Swift/Xcode project. "
            "Runs on macos-latest. Steps: checkout, xcodebuild -scheme App "
            "-destination 'generic/platform=iOS' build. Return ONLY YAML."
        ),
        TechStack.KOTLIN: (
            "Generate GitHub Actions for Android Kotlin project. "
            "Steps: checkout, setup-java@v4 (temurin 17), "
            "./gradlew assembleRelease. Return ONLY YAML."
        ),
        TechStack.PYTHON_BACKEND: (
            "Generate GitHub Actions for Python FastAPI deploy to Cloud Run. "
            "Steps: checkout, auth to GCP, docker build, push to Artifact "
            "Registry, gcloud run deploy. Return ONLY YAML."
        ),
    }

    prompt = ci_prompts.get(stack)
    if prompt:
        workflow_name = (
            ".github/workflows/deploy.yml"
            if stack == TechStack.PYTHON_BACKEND
            else ".github/workflows/build.yml"
        )
        ci_yaml = await call_ai(
            role=AIRole.ENGINEER,
            prompt=prompt,
            state=state,
            action="write_code",
        )
        files[workflow_name] = ci_yaml

    # Stack-specific extras
    if stack == TechStack.REACT_NATIVE:
        bundle_id = state.project_metadata.get("bundle_id", "com.factory.app")
        eas = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Generate eas.json for Expo project. Bundle ID: {bundle_id}. "
                f"Profiles: development, preview, production. Return ONLY JSON."
            ),
            state=state,
            action="write_code",
        )
        files["eas.json"] = eas

    elif stack == TechStack.PYTHON_BACKEND:
        dockerfile = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                "Generate Dockerfile for Python FastAPI. Python 3.11-slim, "
                "pip install -r requirements.txt, "
                "uvicorn main:app --port 8080. Return ONLY Dockerfile content."
            ),
            state=state,
            action="write_code",
        )
        files["Dockerfile"] = dockerfile

    return files


# ═══════════════════════════════════════════════════════════════════
# Minimal Scaffold Fallback
# ═══════════════════════════════════════════════════════════════════


def _sanitize_file_contents(files: dict) -> dict:
    """Strip markdown code fences from file content values.

    Models sometimes return:
      {"lib/main.dart": "```dart\\nimport ...\\n```"}
    This extracts just the code from inside the fence.
    """
    import re
    fence_re = re.compile(r"^```[\w]*\n?([\s\S]*?)```\s*$", re.MULTILINE)
    result = {}
    for path, content in files.items():
        if not isinstance(content, str):
            result[path] = content
            continue
        m = fence_re.match(content.strip())
        if m:
            result[path] = m.group(1).rstrip()
        else:
            result[path] = content
    return result


async def _generate_files_individually(
    state,
    stack: "TechStack",
    app_name: str,
    blueprint_data: dict,
) -> dict:
    """Generate each key file separately when bulk generation fails.

    This is more reliable for smaller/weaker models — one file per call,
    asking for raw code output only (no JSON wrapper, no markdown fences).
    """
    screens = blueprint_data.get("screens", [])
    data_model = blueprint_data.get("data_model", [])
    auth = blueprint_data.get("auth_method", "email")
    colors = blueprint_data.get("color_palette", {})
    primary = colors.get("primary", "#6366f1")

    files: dict = {}

    if stack == TechStack.FLUTTERFLOW:
        # main.dart
        main_result = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Write ONLY the complete content of lib/main.dart for a Flutter app called '{app_name}'.\n"
                f"Requirements:\n"
                f"- MaterialApp with title '{app_name}'\n"
                f"- Primary color: {primary}\n"
                f"- Home screen: {screens[0]['name'] if screens else 'HomeScreen'}Screen widget\n"
                f"- Firebase initialization (FirebaseApp)\n"
                f"- Import firebase_core, material\n"
                f"- Async main with WidgetsFlutterBinding.ensureInitialized()\n\n"
                f"Output: raw Dart code only. No markdown fences. No explanation."
            ),
            state=state,
            action="write_code",
        )
        files["lib/main.dart"] = _strip_fences(main_result)

        # pubspec.yaml
        pubspec_result = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Write ONLY the complete pubspec.yaml for a Flutter app called '{app_name}'.\n"
                f"Include: flutter sdk, firebase_core, cloud_firestore, firebase_auth, "
                f"provider or riverpod, cached_network_image, go_router.\n"
                f"Use latest stable versions (2024-2025).\n"
                f"Output: raw YAML only. No markdown fences. No explanation."
            ),
            state=state,
            action="write_code",
        )
        files["pubspec.yaml"] = _strip_fences(pubspec_result)

        # Home screen
        home_name = screens[0]["name"].replace(" ", "") if screens else "Home"
        home_result = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Write ONLY the complete lib/screens/{home_name.lower()}_screen.dart "
                f"for a Flutter app called '{app_name}'.\n"
                f"Purpose: {screens[0].get('purpose', 'Main screen') if screens else 'Main screen'}\n"
                f"Components: {screens[0].get('components', []) if screens else ['list', 'fab']}\n"
                f"Auth method: {auth}\n"
                f"Primary color: {primary}\n"
                f"Use StatefulWidget, Material Design 3, proper Dart null safety.\n"
                f"Output: raw Dart code only. No markdown fences. No explanation."
            ),
            state=state,
            action="write_code",
        )
        files[f"lib/screens/{home_name.lower()}_screen.dart"] = _strip_fences(home_result)

        # README
        files["README.md"] = (
            f"# {app_name}\n\n"
            f"Generated by AI Factory Pipeline.\n\n"
            f"## Setup\n```\nflutter pub get\nflutter run\n```\n\n"
            f"## Stack\nFlutter + Firebase\n"
        )

    elif stack == TechStack.REACT_NATIVE:
        app_result = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Write ONLY the complete App.tsx for a React Native + Expo app called '{app_name}'.\n"
                f"Include: NavigationContainer, Stack navigator, "
                f"{screens[0]['name'] if screens else 'Home'}Screen as first screen.\n"
                f"Primary color: {primary}\n"
                f"Output: raw TypeScript/TSX code only. No markdown fences. No explanation."
            ),
            state=state,
            action="write_code",
        )
        files["App.tsx"] = _strip_fences(app_result)
        files["package.json"] = (
            f'{{"name":"{app_name.lower().replace(" ","-")}","version":"1.0.0",'
            f'"main":"expo/AppEntry.js","scripts":{{"start":"expo start",'
            f'"android":"expo start --android","ios":"expo start --ios"}},'
            f'"dependencies":{{"expo":"~51.0.0","react":"18.2.0",'
            f'"react-native":"0.74.0","@react-navigation/native":"^6.0.0",'
            f'"firebase":"^10.0.0"}}}}\n'
        )

    else:
        # Other stacks: use the minimal scaffold but with real entry point logic
        files = _create_minimal_scaffold(stack, app_name)

    logger.info(
        f"[{state.project_id}] S3: File-by-file generation produced "
        f"{len(files)} files ({sum(len(v) for v in files.values() if isinstance(v,str))} bytes)"
    )
    return files


def _strip_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from a string."""
    import re
    if not text:
        return text
    m = re.match(r"^```[\w]*\n?([\s\S]*?)```\s*$", text.strip(), re.MULTILINE)
    return m.group(1).rstrip() if m else text.strip()


def _extract_json_from_response(text: str) -> dict:
    """Try to extract a JSON object from an AI response that may be wrapped in
    markdown code fences (```json ... ```) or contain preamble text.

    Returns a dict of {file_path: content} or empty dict on failure.
    """
    import re

    if not text:
        return {}

    # Try stripping markdown code fences
    patterns = [
        r"```json\s*([\s\S]*?)```",  # ```json ... ```
        r"```\s*([\s\S]*?)```",       # ``` ... ```
        r"\{[\s\S]*\}",               # bare JSON object anywhere
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1) if "(" in pattern and ")" in pattern else match.group(0)
            # For the bare-object pattern, group(0) is the whole match
            if pattern == r"\{[\s\S]*\}":
                candidate = match.group(0)
            try:
                parsed = json.loads(candidate.strip())
                if isinstance(parsed, dict) and parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

    return {}


def _create_minimal_scaffold(
    stack: TechStack, app_name: str,
) -> dict[str, str]:
    """Create minimal scaffold when AI generation fails."""
    scaffolds = {
        TechStack.FLUTTERFLOW: {
            "lib/main.dart": f'// {app_name} — FlutterFlow\nimport "package:flutter/material.dart";\nvoid main() => runApp(MaterialApp(home: Scaffold(body: Center(child: Text("{app_name}")))));\n',
            "pubspec.yaml": f"name: {app_name.lower().replace(' ', '_')}\ndescription: {app_name}\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n",
        },
        TechStack.REACT_NATIVE: {
            "App.tsx": f'// {app_name}\nimport React from "react";\nimport {{ Text, View }} from "react-native";\nexport default () => <View><Text>{app_name}</Text></View>;\n',
            "package.json": f'{{"name": "{app_name.lower().replace(" ", "-")}", "version": "1.0.0", "main": "App.tsx"}}\n',
        },
        TechStack.SWIFT: {
            "App.swift": f'// {app_name}\nimport SwiftUI\n@main\nstruct {app_name.replace(" ", "")}App: App {{\n    var body: some Scene {{\n        WindowGroup {{ Text("{app_name}") }}\n    }}\n}}\n',
        },
        TechStack.KOTLIN: {
            "app/src/main/java/com/factory/app/MainActivity.kt": f'package com.factory.app\nimport android.os.Bundle\nimport androidx.appcompat.app.AppCompatActivity\nclass MainActivity : AppCompatActivity() {{\n    override fun onCreate(savedInstanceState: Bundle?) {{\n        super.onCreate(savedInstanceState)\n    }}\n}}\n',
        },
        TechStack.PYTHON_BACKEND: {
            "main.py": f'# {app_name}\nfrom fastapi import FastAPI\napp = FastAPI(title="{app_name}")\n@app.get("/health")\nasync def health(): return {{"status": "ok"}}\n',
            "requirements.txt": "fastapi>=0.100.0\nuvicorn>=0.23.0\n",
        },
        TechStack.UNITY: {
            "Assets/Scripts/GameManager.cs": f'// {app_name}\nusing UnityEngine;\npublic class GameManager : MonoBehaviour {{\n    void Start() {{ Debug.Log("{app_name} started"); }}\n}}\n',
        },
    }
    return scaffolds.get(stack, {"README.md": f"# {app_name}\n"})


# Register with DAG (replaces stub)
register_stage_node("s3_codegen", s3_codegen_node)


# ═══════════════════════════════════════════════════════════════════
# MODIFY Mode: Diff-Based CodeGen
# ═══════════════════════════════════════════════════════════════════


async def _s3_modify_codegen(
    state: PipelineState,
    blueprint_data: dict,
) -> PipelineState:
    """S3 MODIFY: generate targeted file changes instead of full files.

    Steps:
      1. For each file in the change plan → generate modified version
      2. Generate new files from files_to_add list
      3. Build a ChangeSet (unified diffs) using DiffGenerator
      4. Store diffs in s3_output for operator review before applying
    """
    change_plan = blueprint_data.get("change_plan", {})
    description = blueprint_data.get("modification_description", "")
    context = state.codebase_context or {}
    context_text = context.get("context_text", "")[:40000]

    files_to_modify: list[dict] = change_plan.get("files_to_modify", [])
    files_to_add: list[dict] = change_plan.get("files_to_add", [])
    files_to_delete: list[str] = change_plan.get("files_to_delete", [])

    logger.info(
        f"[{state.project_id}] MODIFY S3: generating diffs for "
        f"{len(files_to_modify)} modify + {len(files_to_add)} add"
    )

    original_files: dict[str, str] = context.get("file_contents", {})
    generated_files: dict[str, str] = {}

    # ── Modify existing files ──
    for file_spec in files_to_modify[:20]:  # cap to keep costs controlled
        file_path = file_spec.get("path", "")
        change_summary = file_spec.get("change_summary", description)
        original_content = original_files.get(file_path, "")

        try:
            modified = await call_ai(
                role=AIRole.ENGINEER,
                prompt=(
                    f"Modify the following file to: {change_summary}\n\n"
                    f"Overall request: {description}\n\n"
                    f"FILE: {file_path}\n"
                    f"ORIGINAL CONTENT:\n{original_content[:8000]}\n\n"
                    f"CODEBASE CONTEXT (for references):\n{context_text[:4000]}\n\n"
                    f"Return ONLY the complete modified file content. "
                    f"Preserve style, indentation, and imports."
                ),
                state=state,
                action="codegen",
            )
            generated_files[file_path] = modified
        except Exception as e:
            logger.warning(f"[{state.project_id}] MODIFY S3: failed {file_path}: {e}")

    # ── Generate new files ──
    for file_spec in files_to_add[:10]:
        file_path = file_spec.get("path", "")
        purpose = file_spec.get("purpose", description)

        try:
            new_content = await call_ai(
                role=AIRole.ENGINEER,
                prompt=(
                    f"Create a new file: {file_path}\n"
                    f"Purpose: {purpose}\n"
                    f"Overall modification: {description}\n\n"
                    f"CODEBASE CONTEXT:\n{context_text[:6000]}\n\n"
                    f"Return ONLY the complete file content."
                ),
                state=state,
                action="codegen",
            )
            generated_files[file_path] = new_content
        except Exception as e:
            logger.warning(f"[{state.project_id}] MODIFY S3: failed new {file_path}: {e}")

    # ── Build ChangeSet with diffs ──
    try:
        from factory.pipeline.diff_generator import build_changeset
        changeset = build_changeset(
            original_files=original_files,
            generated_files=generated_files,
        )
        diff_summary = changeset.to_review_text()
        state.s3_output = {
            "modify_mode": True,
            "generated_files": generated_files,
            "deleted_files": files_to_delete,
            "diff_summary": diff_summary,
            "lines_added": changeset.lines_added,
            "lines_removed": changeset.lines_removed,
            "files_changed": len(generated_files),
            "changeset": {
                "modified": [f.path for f in changeset.modified_files],
                "new": [f.path for f in changeset.new_files],
                "deleted": [f.path for f in changeset.deleted_files],
            },
        }
    except Exception as e:
        logger.warning(f"[{state.project_id}] MODIFY S3: diff build failed: {e}")
        state.s3_output = {
            "modify_mode": True,
            "generated_files": generated_files,
            "deleted_files": files_to_delete,
            "files_changed": len(generated_files),
        }

    logger.info(
        f"[{state.project_id}] MODIFY S3 complete: "
        f"{len(generated_files)} files generated"
    )
    return state


def _parse_files_response(text: str) -> dict[str, str]:
    """Parse AI-generated files response into a filename→content dict.

    Spec: §4.4 — CodeGen output parsing
    Handles: markdown fenced blocks with filename headers, plain JSON.
    """
    import re
    files: dict[str, str] = {}
    # Pattern: ## filename.ext or **filename.ext** followed by ```lang ... ```
    pattern = re.compile(
        r"(?:##\s*|[*]{2})([^\n*`]+?)(?:[*]{2})?\s*\n```[^\n]*\n(.*?)```",
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        filename = match.group(1).strip()
        content = match.group(2)
        if filename and content:
            files[filename] = content

    # Fallback: try to extract JSON from plain ``` blocks or raw JSON
    if not files:
        # Try JSON inside a code fence (```json ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:\w*)\n(.*?)```", text, re.DOTALL)
        if fence_match:
            try:
                files = json.loads(fence_match.group(1).strip())
                return files
            except (json.JSONDecodeError, TypeError):
                pass
        # Try raw JSON
        try:
            files = json.loads(text.strip())
            if isinstance(files, dict):
                return files
        except (json.JSONDecodeError, TypeError):
            pass

    return files
