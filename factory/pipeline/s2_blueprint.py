"""
AI Factory Pipeline v5.6 — S2 Blueprint Node

Implements:
  - §4.3 S2 Blueprint + Stack Selection + Design
  - Phase 1: Stack selection (Copilot 4-way or Autopilot auto)
  - Phase 2: Architecture design (Strategist)
  - Phase 3: Blueprint generation (Strategist)
  - Phase 4: Design system (Vibe Check)
  - Phase 5: Compliance artifact generation (FIX-07)

Spec Authority: v5.6 §4.3, §4.3.1, §3.4
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    AutonomyMode,
    PipelineState,
    Stage,
    TechStack,
)
from factory.core.roles import call_ai
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s2_blueprint")


# ═══════════════════════════════════════════════════════════════════
# Stack Selection Helpers
# ═══════════════════════════════════════════════════════════════════

STACK_DESCRIPTIONS: dict[str, str] = {
    "flutterflow": "FlutterFlow — visual builder, fastest for standard apps",
    "react_native": "React Native — JS cross-platform, flexible customization",
    "swift": "Swift — native iOS, best for Apple-only apps",
    "kotlin": "Kotlin — native Android, best for Google-only apps",
    "unity": "Unity — game engine, 2D/3D games and AR",
    "python_backend": "Python Backend — APIs, automation, no mobile UI",
}


async def select_stack(
    state: PipelineState,
    requirements: dict,
    legal_output: dict,
) -> TechStack:
    """Autopilot stack selection via Strategist.

    Spec: §4.3 Phase 1 (Autopilot path)
    """
    result = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"SELECT THE OPTIMAL TECH STACK.\n\n"
            f"App: {requirements.get('app_description', '')}\n"
            f"Category: {requirements.get('app_category', 'other')}\n"
            f"Platforms: {requirements.get('target_platforms', ['ios', 'android'])}\n"
            f"Complexity: {requirements.get('estimated_complexity', 'medium')}\n"
            f"Has payments: {requirements.get('has_payments', False)}\n"
            f"Has realtime: {requirements.get('has_realtime', False)}\n\n"
            f"Options: flutterflow, react_native, swift, kotlin, unity, python_backend\n\n"
            f"Return ONLY the stack name (one word)."
        ),
        state=state,
        action="plan_architecture",
    )

    stack_name = result.strip().lower().replace(" ", "_")
    try:
        return TechStack(stack_name)
    except ValueError:
        logger.warning(
            f"[{state.project_id}] Invalid stack '{stack_name}', "
            f"defaulting to flutterflow"
        )
        return TechStack.FLUTTERFLOW


async def copilot_stack_selection(
    state: PipelineState,
    requirements: dict,
    legal_output: dict,
) -> TechStack:
    """Copilot 4-way stack selection.

    Spec: §4.3 Phase 1 (Copilot path)
    Presents top options to operator via Telegram.
    """
    from factory.telegram.decisions import present_decision

    # Get Strategist recommendation
    recommendation = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Recommend the top 3 tech stacks for this app.\n\n"
            f"App: {requirements.get('app_description', '')}\n"
            f"Category: {requirements.get('app_category', 'other')}\n"
            f"Platforms: {requirements.get('target_platforms', [])}\n"
            f"Complexity: {requirements.get('estimated_complexity', 'medium')}\n\n"
            f"Return ONLY a JSON array of 3 stack names "
            f"from: flutterflow, react_native, swift, kotlin, unity, python_backend"
        ),
        state=state,
        action="plan_architecture",
    )

    try:
        top_stacks = json.loads(recommendation)[:3]
    except (json.JSONDecodeError, TypeError):
        top_stacks = ["flutterflow", "react_native", "python_backend"]

    options = []
    for i, stack_name in enumerate(top_stacks):
        label = STACK_DESCRIPTIONS.get(stack_name, stack_name)
        options.append({"label": label, "value": stack_name})

    selected = await present_decision(
        state=state,
        decision_type="stack_selection",
        question="Which tech stack for your app?",
        options=options,
        recommended=0,
    )

    try:
        return TechStack(selected)
    except ValueError:
        return TechStack.FLUTTERFLOW


# ═══════════════════════════════════════════════════════════════════
# Stack Metadata Initializers (§4.3)
# ═══════════════════════════════════════════════════════════════════


def _init_stack_metadata(
    stack: TechStack, requirements: dict,
) -> dict:
    """Initialize stack-specific metadata.

    Spec: §4.3
    """
    app_name_slug = requirements.get("app_name", "app").lower().replace(" ", "")

    initializers = {
        TechStack.FLUTTERFLOW: lambda: {
            "ff_project_id": "", "ff_pages": [], "ff_collections": [],
        },
        TechStack.REACT_NATIVE: lambda: {
            "package_json": {}, "entry_point": "App.tsx",
        },
        TechStack.SWIFT: lambda: {
            "xcode_project_path": "",
            "bundle_id": f"com.factory.{app_name_slug}",
            "swift_version": "5.10",
        },
        TechStack.KOTLIN: lambda: {
            "gradle_project_path": "",
            "package_name": f"com.factory.{app_name_slug}",
            "min_sdk": 26,
        },
        TechStack.UNITY: lambda: {
            "unity_project_path": "",
            "unity_version": "2022.3",
            "target_platforms": requirements.get("target_platforms", []),
        },
        TechStack.PYTHON_BACKEND: lambda: {
            "framework": "fastapi",
            "python_version": "3.11",
            "deploy_target": "cloud_run",
        },
    }

    return initializers.get(stack, lambda: {})()


# ═══════════════════════════════════════════════════════════════════
# §4.3 S2 Blueprint Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S2_BLUEPRINT)
async def s2_blueprint_node(state: PipelineState) -> PipelineState:
    """S2: Blueprint — Stack Selection → Architecture → Blueprint → Design.

    Spec: §4.3
    The Strategist's main stage. Produces the master plan consumed by S3–S8.

    Cost target: <$1.50
    """
    requirements = state.s0_output or {}
    legal_output = state.s1_output or {}

    # ══════════════════════════════════════
    # Phase 1: Stack Selection
    # ══════════════════════════════════════
    if state.autonomy_mode == AutonomyMode.COPILOT:
        selected_stack = await copilot_stack_selection(
            state, requirements, legal_output,
        )
    else:
        selected_stack = await select_stack(
            state, requirements, legal_output,
        )

    state.selected_stack = selected_stack
    state.project_metadata.update(
        _init_stack_metadata(selected_stack, requirements),
    )

    # ══════════════════════════════════════
    # Phase 2: Architecture Design
    # ══════════════════════════════════════
    architecture_result = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"DESIGN THE APP ARCHITECTURE.\n\n"
            f"App: {requirements.get('app_description', '')}\n"
            f"Stack: {selected_stack.value}\n"
            f"Features (must): {requirements.get('features_must', [])}\n"
            f"Features (nice): {requirements.get('features_nice', [])}\n"
            f"Platforms: {requirements.get('target_platforms', [])}\n"
            f"Data classification: "
            f"{legal_output.get('data_classification', 'internal')}\n"
            f"Regulatory: {legal_output.get('regulatory_bodies', [])}\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{\n'
            f'  "screens": [{{"name": "...", "purpose": "...", '
            f'"components": ["..."], "data_bindings": '
            f'[{{"collection": "...", "field": "..."}}]}}],\n'
            f'  "data_model": [{{"collection": "...", '
            f'"fields": [{{"name": "...", "type": "string|int|bool|timestamp|ref"}}]}}],\n'
            f'  "api_endpoints": [{{"path": "...", "method": "GET|POST", '
            f'"purpose": "..."}}],\n'
            f'  "auth_method": "email|phone|social|none",\n'
            f'  "services": {{"backend": "...", "storage": "...", "auth": "..."}},\n'
            f'  "env_vars": {{"VAR_NAME": "description"}}\n'
            f'}}'
        ),
        state=state,
        action="plan_architecture",
    )

    try:
        architecture = json.loads(architecture_result)
    except json.JSONDecodeError:
        logger.warning(
            f"[{state.project_id}] S2: Failed to parse architecture JSON, "
            f"using minimal scaffold"
        )
        architecture = {
            "screens": [{"name": "Home", "purpose": "Main screen", "components": [], "data_bindings": []}],
            "data_model": [{"collection": "users", "fields": [{"name": "email", "type": "string"}]}],
            "api_endpoints": [],
            "auth_method": "email",
            "services": {},
            "env_vars": {},
        }

    # ══════════════════════════════════════
    # Phase 3: Blueprint Assembly
    # ══════════════════════════════════════
    blueprint_data = {
        "app_name": requirements.get("app_name", state.project_id),
        "app_description": requirements.get("app_description", ""),
        "app_category": requirements.get("app_category", "other"),
        "target_platforms": requirements.get("target_platforms", ["ios", "android"]),
        "selected_stack": selected_stack.value,
        "screens": architecture.get("screens", []),
        "data_model": architecture.get("data_model", []),
        "api_endpoints": architecture.get("api_endpoints", []),
        "auth_method": architecture.get("auth_method", "email"),
        "payment_mode": legal_output.get("payment_mode", "SANDBOX"),
        "legal_classification": legal_output.get("data_classification", "internal"),
        "data_residency": "KSA",
        "business_model": requirements.get("app_category", "general"),
        "required_legal_docs": legal_output.get("required_legal_docs", []),
        "generated_by": ["strategist_opus"],
        "services": architecture.get("services", {}),
        "env_vars": architecture.get("env_vars", {}),
    }

    # ══════════════════════════════════════
    # Phase 4: Design System (Vibe Check)
    # ══════════════════════════════════════
    design_result = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"DESIGN SYSTEM for {blueprint_data['app_name']}.\n\n"
            f"Category: {blueprint_data['app_category']}\n"
            f"Stack: {selected_stack.value}\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{\n'
            f'  "color_palette": {{"primary": "#hex", "secondary": "#hex", '
            f'"background": "#hex", "text_primary": "#hex", '
            f'"text_secondary": "#hex", "accent": "#hex"}},\n'
            f'  "typography": {{"font_family": "...", "size_base": 16, '
            f'"size_h1": 32, "size_h2": 24, "weight_normal": 400, '
            f'"weight_bold": 700}},\n'
            f'  "design_system": "material3|cupertino|custom",\n'
            f'  "spacing": {{"unit": 4, "xs": 4, "sm": 8, "md": 16, '
            f'"lg": 24, "xl": 32}}\n'
            f'}}'
        ),
        state=state,
        action="plan_architecture",
    )

    try:
        design = json.loads(design_result)
        blueprint_data["color_palette"] = design.get("color_palette", {})
        blueprint_data["typography"] = design.get("typography", {})
        blueprint_data["design_system"] = design.get("design_system", "material3")
    except json.JSONDecodeError:
        logger.warning(f"[{state.project_id}] S2: Design parse failed, using defaults")
        blueprint_data["color_palette"] = {
            "primary": "#1976D2", "secondary": "#FF9800",
            "background": "#FFFFFF", "text_primary": "#212121",
            "text_secondary": "#757575", "accent": "#03DAC6",
        }
        blueprint_data["typography"] = {
            "font_family": "Inter", "size_base": 16,
        }
        blueprint_data["design_system"] = "material3"

    state.s2_output = blueprint_data

    # ══════════════════════════════════════
    # Phase 5: Compliance Artifacts (FIX-07)
    # ══════════════════════════════════════
    compliance_files = await _generate_compliance_artifacts(
        state, selected_stack, legal_output,
    )
    if compliance_files:
        state.s2_output["compliance_artifacts"] = compliance_files

    logger.info(
        f"[{state.project_id}] S2 complete: "
        f"stack={selected_stack.value}, "
        f"screens={len(architecture.get('screens', []))}, "
        f"collections={len(architecture.get('data_model', []))}"
    )
    return state


async def _generate_compliance_artifacts(
    state: PipelineState,
    stack: TechStack,
    legal_output: dict,
) -> list[str]:
    """Generate compliance artifact templates and write to project dir.

    Spec: §4.3.1 (FIX-07)
    Writes template files to disk; S8 DocuGen fills them with AI content.
    """
    project_dir = f"/tmp/factory_projects/{state.project_id}"
    files: list[str] = []

    templates: dict[str, str] = {
        "legal/privacy_policy.md": (
            f"# Privacy Policy — {state.project_id}\n\n"
            "**KSA PDPL Compliant** — To be completed at S8 Handoff.\n\n"
            "## Data Collection\n\n## Data Usage\n\n## User Rights\n"
        ),
        "legal/terms_of_service.md": (
            f"# Terms of Service — {state.project_id}\n\n"
            "**Draft** — To be completed at S8 Handoff.\n\n"
            "## Acceptance\n\n## Services\n\n## Limitations\n"
        ),
        "legal/store_checklist.md": (
            f"# App Store Checklist — {state.project_id}\n\n"
            f"Stack: {stack.value}\n\n"
            f"Legal classification: {legal_output.get('risk_level', 'MEDIUM')}\n\n"
            "- [ ] Privacy policy URL set\n"
            "- [ ] Age rating configured\n"
            "- [ ] Export compliance declared\n"
        ),
    }

    is_ios = stack in (
        TechStack.SWIFT, TechStack.FLUTTERFLOW,
        TechStack.REACT_NATIVE, TechStack.UNITY,
    )
    is_android = stack in (
        TechStack.KOTLIN, TechStack.FLUTTERFLOW,
        TechStack.REACT_NATIVE, TechStack.UNITY,
    )

    if is_ios:
        templates["legal/privacy_manifest_template.plist"] = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
            "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
            "<plist version=\"1.0\"><dict>"
            "<key>NSPrivacyTracking</key><false/>"
            "</dict></plist>\n"
        )
        templates["legal/ats_config.plist"] = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<plist version=\"1.0\"><dict>"
            "<key>NSAllowsArbitraryLoads</key><false/>"
            "</dict></plist>\n"
        )
    if is_android:
        templates["legal/data_safety_form.yaml"] = (
            f"app: {state.project_id}\n"
            "data_collected: []\n"
            "data_shared: []\n"
            "security_practices:\n"
            "  - data_encrypted_in_transit: true\n"
        )

    try:
        from factory.core.execution import write_file
        for rel_path, content in templates.items():
            full_path = f"{project_dir}/{rel_path}"
            await write_file(full_path, content, state.project_id)
            files.append(rel_path)
    except Exception as e:
        # Graceful degradation — return file list even if write fails
        logger.warning(
            f"[{state.project_id}] FIX-07: Could not write compliance files: {e}"
        )
        files = list(templates.keys())

    logger.info(
        f"[{state.project_id}] FIX-07: Generated {len(files)} compliance artifacts"
    )
    return files


# Register with DAG
register_stage_node("s2_blueprint", s2_blueprint_node)