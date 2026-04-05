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
    code_prompt = (
        f"Generate ALL code files for a {stack.value} project.\n\n"
        f"App: {app_name}\n"
        f"Screens: {json.dumps(screens[:10], indent=2)[:3000]}\n"
        f"Data model: {json.dumps(data_model, indent=2)[:2000]}\n"
        f"API endpoints: {json.dumps(api_endpoints, indent=2)[:1500]}\n"
        f"Auth: {auth_method}\n"
        f"Design: {json.dumps(blueprint_data.get('color_palette', {}))}\n\n"
        f"Return ONLY valid JSON: {{\"file_path\": \"file_content\", ...}}\n"
        f"Include all necessary files: entry point, screens, models, "
        f"config, package manifest."
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
        logger.warning(
            f"[{state.project_id}] S3: Failed to parse Engineer JSON, "
            f"creating minimal scaffold"
        )
        files = _create_minimal_scaffold(stack, app_name)

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
    L2: Engineer (Sonnet) — deeper analysis
    L3: Scout + Strategist — research + plan
    """
    # ── L1: Quick Fix attempt ──
    l1_result = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=(
            f"Fix this error in {file_path}:\n"
            f"Error: {error}\n\n"
            f"Current file content:\n{file_content[:4000]}\n\n"
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
        return {"resolved": True, "fixed_content": l1_result, "level": 1}

    # ── L2: Engineer analysis ──
    l2_result = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"The Quick Fix couldn't resolve this error. Analyze deeper.\n\n"
            f"File: {file_path}\n"
            f"Error: {error}\n"
            f"File content:\n{file_content[:3000]}\n\n"
            f"Other project files available: "
            f"{list(all_files.keys())[:20]}\n\n"
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
                # Apply secondary fixes
                for path, content in multi.get("secondary_fixes", {}).items():
                    if path in all_files:
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
        return {"resolved": True, "fixed_content": fixed_content, "level": 2}

    # ── L3: Unresolved — log for operator ──
    state.war_room_history.append({
        "level": 3,
        "error": error[:200],
        "file": file_path,
        "resolved": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    logger.error(
        f"[{state.project_id}] War Room L3 unresolved: "
        f"{file_path} — {error[:100]}"
    )
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
        k: v[:500] for k, v in files.items()
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
    except json.JSONDecodeError:
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
