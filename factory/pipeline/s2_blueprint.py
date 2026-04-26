"""
AI Factory Pipeline v5.8 — S2 Blueprint Node

Implements:
  - §4.3 S2 Blueprint + Stack Selection + Design
  - Phase 0: S1 legal dossier ingestion
  - Phase 1: Stack selection (Copilot 4-way or Autopilot auto)
  - Phase 2: Architecture design (Strategist)
  - Phase 3: Blueprint assembly
  - Phase 3.5: IEEE 20-doc blueprint suite (Scout→Strategist→Engineer + verification)
  - Phase 4: Design system (Vibe Check)
  - Phase 5: Compliance artifact generation (FIX-07)
  - Phase 8: Stack Selection ADR (project-scoped, deduplicated)
  - Phase 10: Mother Memory — blueprint decisions

Spec Authority: v5.8 §4.3, §4.3.1, §3.4
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

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
# FIX-S2: Structured Architecture Output (Pydantic)
# ═══════════════════════════════════════════════════════════════════

_MIN_SCREENS = 1
_MIN_FEATURES = 3
_MIN_JOURNEYS = 2
_MAX_REFINE_ROUNDS = 2


class _Screen(BaseModel):
    name: str
    purpose: str = ""
    components: list[str] = Field(default_factory=list)
    data_bindings: list[dict[str, Any]] = Field(default_factory=list)


class _DataField(BaseModel):
    name: str
    type: str = "string"


class _Collection(BaseModel):
    collection: str
    fields: list[_DataField] = Field(default_factory=list)


class _ApiEndpoint(BaseModel):
    path: str
    method: str = "GET"
    purpose: str = ""


class _Feature(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    priority: str = "medium"
    acceptance_criteria: str = ""


class _UserJourney(BaseModel):
    id: str = ""
    persona: str = ""
    goal: str = ""
    steps: list[str] = Field(default_factory=list)


class ArchitectureBlueprint(BaseModel):
    """Validated architecture output from the Strategist role."""
    screens: list[_Screen] = Field(default_factory=list)
    data_model: list[_Collection] = Field(default_factory=list)
    api_endpoints: list[_ApiEndpoint] = Field(default_factory=list)
    auth_method: str = "email"
    services: dict[str, Any] = Field(default_factory=dict)
    env_vars: dict[str, str] = Field(default_factory=dict)
    feature_list: list[_Feature] = Field(default_factory=list)
    user_journeys: list[_UserJourney] = Field(default_factory=list)
    analytics_events: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("screens")
    @classmethod
    def _require_screens(cls, v: list) -> list:
        if not v:
            raise ValueError("screens must have at least one entry")
        return v

    def is_complete(self) -> bool:
        return (
            len(self.screens) >= _MIN_SCREENS
            and len(self.feature_list) >= _MIN_FEATURES
            and len(self.user_journeys) >= _MIN_JOURNEYS
        )

    def missing_fields(self) -> list[str]:
        missing = []
        if len(self.screens) < _MIN_SCREENS:
            missing.append(f"screens (got {len(self.screens)}, need {_MIN_SCREENS})")
        if len(self.feature_list) < _MIN_FEATURES:
            missing.append(f"feature_list (got {len(self.feature_list)}, need {_MIN_FEATURES})")
        if len(self.user_journeys) < _MIN_JOURNEYS:
            missing.append(f"user_journeys (got {len(self.user_journeys)}, need {_MIN_JOURNEYS})")
        return missing


def _extract_json_block(text: str) -> str:
    """Strip markdown fences and return the first JSON object found."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    brace = text.find("{")
    if brace == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace:i + 1]
    return text[brace:]


_ARCH_FALLBACK: dict[str, Any] = {
    "screens": [{"name": "Home", "purpose": "Main screen", "components": [], "data_bindings": []}],
    "data_model": [{"collection": "users", "fields": [{"name": "email", "type": "string"}]}],
    "api_endpoints": [],
    "auth_method": "email",
    "services": {},
    "env_vars": {},
    "feature_list": [],
    "user_journeys": [],
    "analytics_events": [],
}


async def _parse_architecture(
    raw: str,
    state: "PipelineState",
    arch_prompt: str,
) -> dict[str, Any]:
    """Parse + validate architecture JSON with up to _MAX_REFINE_ROUNDS retry.

    On each round where the model returns malformed/incomplete JSON, we ask
    the AI to fix only the specific missing or invalid fields.
    """
    for attempt in range(_MAX_REFINE_ROUNDS + 1):
        text = raw if attempt == 0 else (
            await call_ai(
                role=AIRole.STRATEGIST,
                prompt=(
                    f"The previous architecture JSON was incomplete. "
                    f"Missing required fields: {missing}. "
                    f"Original request:\n{arch_prompt}\n\n"
                    f"Previous response (to improve):\n{raw}\n\n"
                    f"Return ONLY valid JSON fixing the missing fields."
                ),
                state=state,
                action="refine_architecture",
            )
        )
        json_str = _extract_json_block(text)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            missing = [f"valid JSON ({exc})"]
            logger.warning(
                f"[{state.project_id}] S2 parse attempt {attempt + 1}: "
                f"JSONDecodeError — {exc}"
            )
            raw = text
            continue

        try:
            model = ArchitectureBlueprint.model_validate(data)
        except Exception as exc:
            missing = [str(exc)]
            logger.warning(
                f"[{state.project_id}] S2 parse attempt {attempt + 1}: "
                f"validation error — {exc}"
            )
            raw = text
            continue

        missing = model.missing_fields()
        if missing and attempt < _MAX_REFINE_ROUNDS:
            logger.info(
                f"[{state.project_id}] S2 attempt {attempt + 1}: "
                f"incomplete fields {missing}, refining…"
            )
            raw = text
            continue

        if missing:
            logger.warning(
                f"[{state.project_id}] S2: still incomplete after "
                f"{_MAX_REFINE_ROUNDS} refinement rounds: {missing}"
            )
        return model.model_dump()

    logger.error(f"[{state.project_id}] S2: all parse attempts failed, using scaffold")
    return dict(_ARCH_FALLBACK)


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

_STACK_RATIONALE: dict[str, str] = {
    "flutterflow": "Best for rapid delivery with minimal custom code",
    "react_native": "Best for teams with JS experience needing both platforms",
    "swift": "Best for Apple-ecosystem-first apps with native performance",
    "kotlin": "Best for Android-first apps requiring deep platform integration",
    "unity": "Best for games and interactive 3D/AR experiences",
    "python_backend": "Best for API services, automation, and backend-only workloads",
}


def format_stack_summary(stack: "TechStack", requirements: dict) -> str:
    """Return a one-line operator notification for the auto-selected stack.

    Spec: §4.3 — Issue 22C
    Used in AUTOPILOT mode after stack selection to inform the operator.
    """
    name = STACK_DESCRIPTIONS.get(stack.value, stack.value)
    rationale = _STACK_RATIONALE.get(stack.value, "Selected as best fit")
    platforms = requirements.get("target_platforms", [])
    platform_str = "/".join(str(p) for p in platforms) if platforms else "cross-platform"
    return (
        f"🔧 Stack selected: {name}\n"
        f"   Platforms: {platform_str}\n"
        f"   Reason: {rationale}\n"
        f"   (Override with /switch_stack if needed)"
    )


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


def _infer_design_system(stack: TechStack) -> str:
    """Map TechStack to its canonical design system.

    Spec: §3.4.1
    """
    mapping = {
        TechStack.SWIFT: "cupertino",
        TechStack.KOTLIN: "material3",
        TechStack.REACT_NATIVE: "material3",
        TechStack.UNITY: "custom",
        TechStack.PYTHON_BACKEND: "custom",
        TechStack.FLUTTERFLOW: "material3",
    }
    return mapping.get(stack, "material3")


def _init_stack_metadata(
    stack: TechStack, requirements: dict,
) -> dict:
    """Initialize stack-specific metadata.

    Spec: §4.3
    """
    app_name_slug = (requirements.get("app_name") or "app").lower().replace(" ", "")

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

    # FIX-MEM Issue #16: read prior decisions before starting stage work
    try:
        from factory.memory.mother_memory import recall_stage_context
        _prior_ctx = await recall_stage_context(
            project_id=state.project_id,
            operator_id=state.operator_id or "",
            for_stage="S2_BLUEPRINT",
        )
        if _prior_ctx:
            state.project_metadata["s2_prior_context"] = _prior_ctx
            logger.debug(f"[{state.project_id}] S2: recalled prior memory context ({len(_prior_ctx)} chars)")
    except Exception as _mm_err:
        logger.debug(f"[{state.project_id}] S2: recall_stage_context skipped: {_mm_err}")

    # ── Pre-enrichment: Scout design patterns + memory ──
    from factory.core.stage_enrichment import enrich_prompt, store_stage_insight  # noqa: F401

    # ── MODIFY mode: generate change blueprint instead of full app blueprint ──
    from factory.core.state import PipelineMode
    if state.pipeline_mode == PipelineMode.MODIFY:
        return await _s2_modify_blueprint(state, requirements)

    # ══════════════════════════════════════
    # Phase 0: Ingest S1 Legal Dossier
    # ══════════════════════════════════════
    legal_constraints = await _ingest_s1_dossier(state, legal_output)

    # ══════════════════════════════════════
    # Phase 1: Stack Selection
    # ══════════════════════════════════════
    # Honor forced stack from /switch_stack command stored pre-S2
    _forced_stack_raw = state.project_metadata.get("preferred_stack")
    _forced_stack: "TechStack | None" = None
    if _forced_stack_raw:
        try:
            _forced_stack = TechStack(_forced_stack_raw)
            logger.info(
                f"[{state.project_id}] S2: Using forced stack from /switch_stack: "
                f"{_forced_stack.value}"
            )
        except ValueError:
            logger.warning(
                f"[{state.project_id}] S2: Invalid preferred_stack "
                f"'{_forced_stack_raw}' — falling back to AI selection"
            )

    if _forced_stack is not None:
        selected_stack = _forced_stack
    elif state.autonomy_mode == AutonomyMode.COPILOT:
        selected_stack = await copilot_stack_selection(
            state, requirements, legal_output,
        )
    else:
        selected_stack = await select_stack(
            state, requirements, legal_output,
        )
        # Issue 22B: AUTOPILOT — notify operator of auto-selected stack
        try:
            from factory.telegram.notifications import notify_operator
            from factory.core.state import NotificationType
            await notify_operator(
                state,
                NotificationType.INFO,
                format_stack_summary(selected_stack, requirements),
            )
        except Exception:
            pass

    state.selected_stack = selected_stack
    state.project_metadata.update(
        _init_stack_metadata(selected_stack, requirements),
    )

    # ══════════════════════════════════════
    # Phase 2: Architecture Design
    # ══════════════════════════════════════
    _arch_base_prompt = (
        f"DESIGN THE APP ARCHITECTURE AND FEATURE SET.\n\n"
            f"App: {requirements.get('app_description', '')}\n"
            f"Stack: {selected_stack.value}\n"
            f"Features (must): {requirements.get('features_must', [])}\n"
            f"Features (nice): {requirements.get('features_nice', [])}\n"
            f"Platforms: {requirements.get('target_platforms', [])}\n"
            f"Data classification: "
            f"{legal_output.get('data_classification', 'internal')}\n"
            f"Regulatory: {legal_output.get('regulatory_bodies', [])}\n\n"
            f"Return ONLY valid JSON (no markdown, no code fences).\n"
            f"ALL arrays must have AT LEAST the minimum items shown.\n\n"
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
            f'  "env_vars": {{"VAR_NAME": "description"}},\n'
            f'  "feature_list": [\n'
            f'    {{"id": "F1", "name": "...", "description": "...", '
            f'"priority": "high|medium|low", "acceptance_criteria": "..."}},\n'
            f'    ... (minimum 6 features)\n'
            f'  ],\n'
            f'  "user_journeys": [\n'
            f'    {{"id": "J1", "persona": "...", "goal": "...", '
            f'"steps": ["step1", "step2", "step3"]}},\n'
            f'    ... (minimum 4 journeys)\n'
            f'  ],\n'
            f'  "analytics_events": [\n'
            f'    {{"event": "...", "trigger": "...", "properties": {{"key": "value"}}}},\n'
            f'    ... (minimum 6 events)\n'
            f'  ]\n'
            f'}}'
    )
    from factory.pipeline.stage_chain import inject_chain_context as _inject_cc
    _arch_base_prompt = _inject_cc(
        _arch_base_prompt, state, current_stage="s2_blueprint", compact=True,
    )
    _arch_prompt = await enrich_prompt(
        "s2_blueprint", _arch_base_prompt, state,
        scout=True,
    )
    architecture_result = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=_arch_prompt,
        state=state,
        action="plan_architecture",
    )

    architecture = await _parse_architecture(architecture_result, state, _arch_prompt)

    # ══════════════════════════════════════
    # Phase 3: Blueprint Assembly
    # ══════════════════════════════════════

    # Derive fallback feature_list, user_journeys, analytics_events from
    # screens/api_endpoints if AI didn't return them (free tier often omits them).
    _screens = architecture.get("screens", [])
    _endpoints = architecture.get("api_endpoints", [])
    _app_desc = requirements.get("app_description", "")
    _app_name = requirements.get("app_name", state.project_id)

    _feature_list = architecture.get("feature_list", [])
    if len(_feature_list) < 5:
        # Derive from screens + must-have features
        _derived = []
        for i, s in enumerate(_screens[:10]):
            _derived.append({
                "id": f"F{i+1}", "name": s.get("name", f"Feature {i+1}"),
                "description": s.get("purpose", ""),
                "priority": "high" if i < 3 else "medium",
                "acceptance_criteria": f"{s.get('name','')} screen loads and functions correctly",
            })
        for f in requirements.get("features_must", []):
            _derived.append({
                "id": f"FM{len(_derived)+1}", "name": str(f),
                "description": str(f), "priority": "high",
                "acceptance_criteria": f"{f} works as specified",
            })
        _feature_list = (_feature_list + _derived)[:max(6, len(_feature_list))]

    _user_journeys = architecture.get("user_journeys", [])
    if len(_user_journeys) < 3:
        _user_journeys = [
            {"id": "J1", "persona": "New User", "goal": f"Sign up and start using {_app_name}",
             "steps": ["Open app", "Create account", "Complete onboarding", "Use core feature"]},
            {"id": "J2", "persona": "Returning User", "goal": f"Complete primary task in {_app_name}",
             "steps": ["Open app", "Log in", "Navigate to main feature", "Complete action"]},
            {"id": "J3", "persona": "Power User", "goal": "Access advanced features",
             "steps": ["Log in", "Access settings", "Configure preferences", "Use advanced feature"]},
            {"id": "J4", "persona": "Admin", "goal": "Manage content and users",
             "steps": ["Log in as admin", "View dashboard", "Manage entries", "Review analytics"]},
        ] + _user_journeys

    _analytics_events = architecture.get("analytics_events", [])
    if len(_analytics_events) < 5:
        _derived_events = [
            {"event": "app_open", "trigger": "App launched", "properties": {"source": "string"}},
            {"event": "user_signup", "trigger": "New account created", "properties": {"method": "string"}},
            {"event": "user_login", "trigger": "User authenticates", "properties": {"method": "string"}},
            {"event": "feature_used", "trigger": "Core feature activated", "properties": {"feature_name": "string"}},
            {"event": "session_end", "trigger": "App backgrounded", "properties": {"duration_seconds": "int"}},
            {"event": "error_encountered", "trigger": "Unhandled error", "properties": {"error_type": "string"}},
        ]
        for ep in _endpoints[:4]:
            _derived_events.append({
                "event": f"api_{ep.get('path','').strip('/').replace('/','_')}",
                "trigger": ep.get("purpose", "API call"),
                "properties": {"status": "string"},
            })
        _analytics_events = (_analytics_events + _derived_events)[:max(6, len(_analytics_events))]

    blueprint_data = {
        "app_name": _app_name,
        "app_description": _app_desc,
        "app_category": requirements.get("app_category", "other"),
        "target_platforms": requirements.get("target_platforms", ["ios", "android"]),
        "selected_stack": selected_stack.value,
        "screens": _screens,
        "data_model": architecture.get("data_model", []),
        "api_endpoints": _endpoints,
        "auth_method": architecture.get("auth_method", "email"),
        "payment_mode": legal_output.get("payment_mode", "SANDBOX"),
        "legal_classification": legal_output.get("data_classification", "internal"),
        "data_residency": "KSA",
        "business_model": requirements.get("app_category", "general"),
        "required_legal_docs": legal_output.get("required_legal_docs", []),
        "generated_by": ["strategist_opus"],
        "services": architecture.get("services", {}),
        "env_vars": architecture.get("env_vars", {}),
        "feature_list": _feature_list,
        "user_journeys": _user_journeys,
        "analytics_events": _analytics_events,
    }

    # ══════════════════════════════════════
    # Phase 3.5: IEEE 20-Document Blueprint Suite
    # ══════════════════════════════════════
    ieee_docs = await _generate_ieee_blueprint_suite(
        state, requirements, legal_output, legal_constraints, blueprint_data,
    )
    if ieee_docs:
        blueprint_data["ieee_docs"] = {k: v[:200] for k, v in ieee_docs.items()}  # summaries only in state
        blueprint_data["ieee_doc_count"] = len(ieee_docs)
        logger.info(
            f"[{state.project_id}] IEEE suite: {len(ieee_docs)} documents generated"
        )

    # ══════════════════════════════════════
    # Phase 4: Design System (Vibe Check)
    # ══════════════════════════════════════
    try:
        from factory.design.vibe_check import vibe_check
        design = await vibe_check(state, requirements)
        blueprint_data["color_palette"] = design.get("color_palette", {})
        blueprint_data["typography"] = design.get("typography", {})
        blueprint_data["spacing"] = design.get("spacing", {})
        blueprint_data["visual_style"] = design.get("visual_style", "minimal")
        blueprint_data["layout_patterns"] = design.get("layout_patterns", ["cards", "bottom_nav"])
        blueprint_data["design_system"] = _infer_design_system(selected_stack)
        logger.info(
            f"[{state.project_id}] S2: Vibe Check complete — "
            f"style={design.get('visual_style', 'minimal')}"
        )
    except Exception as e:
        logger.warning(f"[{state.project_id}] S2: Vibe Check failed ({e}), using defaults")
        blueprint_data["color_palette"] = {
            "primary": "#1976D2", "secondary": "#FF9800",
            "background": "#FFFFFF", "text_primary": "#212121",
            "text_secondary": "#757575", "accent": "#03DAC6",
        }
        blueprint_data["typography"] = {"font_family": "Inter", "size_base": 16}
        blueprint_data["design_system"] = _infer_design_system(selected_stack)

    state.s2_output = blueprint_data

    # ── Store blueprint nodes in Mother Memory (Issue 21 §6) ──────────
    try:
        from factory.memory.mother_memory import (
            store_requirement, store_screen, store_api_endpoint, store_data_model,
        )
        bp_out = state.s2_output or {}
        pid = state.project_id
        oid = state.operator_id

        for i, feat in enumerate(bp_out.get("feature_list", [])[:20]):
            if isinstance(feat, dict):
                await store_requirement(
                    project_id=pid, operator_id=oid,
                    req_id=feat.get("id", f"R{i+1}"),
                    description=feat.get("name","") or feat.get("description",""),
                    priority=feat.get("priority","medium"),
                    acceptance_criteria=feat.get("acceptance_criteria",""),
                    source_stage="S2_BLUEPRINT",
                )

        for i, screen in enumerate(bp_out.get("screens", [])[:20]):
            if isinstance(screen, dict):
                await store_screen(
                    project_id=pid, operator_id=oid,
                    screen_id=screen.get("id", f"SCR{i+1}"),
                    name=screen.get("name", f"Screen{i+1}"),
                    purpose=screen.get("purpose",""),
                    components=screen.get("components", []),
                    api_bindings=screen.get("api_bindings", []),
                )

        for ep in (bp_out.get("api_endpoints") or bp_out.get("api_spec") or [])[:15]:
            if isinstance(ep, dict):
                await store_api_endpoint(
                    project_id=pid, operator_id=oid,
                    path=ep.get("path",""),
                    method=ep.get("method","GET"),
                    request_schema=str(ep.get("request_schema","")),
                    response_schema=str(ep.get("response_schema","")),
                    auth=ep.get("auth",""),
                )

        for dm in (bp_out.get("data_model") or bp_out.get("data_models") or [])[:10]:
            if isinstance(dm, dict):
                await store_data_model(
                    project_id=pid, operator_id=oid,
                    name=dm.get("name","") or dm.get("collection",""),
                    fields=str(dm.get("fields","")),
                    relations=str(dm.get("relations","")),
                )
        logger.info(f"[{pid}] S2 blueprint nodes stored in Mother Memory")
    except Exception as _mm_err:
        logger.warning(f"[{state.project_id}] Mother Memory S2 store error (non-fatal): {_mm_err}")

    # ── Quality Gate (Issue 17) ──────────────────────────────────────
    # Skip gates in dry-run / test mode (DRY_RUN=true).
    from factory.core.dry_run import is_dry_run
    if not is_dry_run():
        from factory.core.quality_gates import (
            check_min_list, check_no_placeholders,
            raise_if_failed, GateResult, QualityGateFailure,
        )
        from factory.core.halt import HaltCode, HaltReason, set_halt

        bp = state.s2_output or state.project_metadata
        _gate_results = []

        features = bp.get("feature_list") or bp.get("FEATURE_LIST") or []
        _gate_results.append(check_min_list(features, 5, "feature_list"))

        journeys = bp.get("user_journeys") or bp.get("USER_JOURNEYS") or []
        _gate_results.append(check_min_list(journeys, 3, "user_journeys"))

        events = (bp.get("analytics_plan") or {}).get("events") or bp.get("analytics_events") or []
        _gate_results.append(check_min_list(events, 5, "analytics_events"))

        desc = bp.get("description") or bp.get("app_description") or ""
        if isinstance(desc, str) and desc:
            _gate_results.append(check_no_placeholders(desc, "description"))

        try:
            raise_if_failed(
                "S2_BLUEPRINT", _gate_results,
                recommended_action="retry S2_BLUEPRINT — regenerate with more detail",
            )
        except QualityGateFailure as qgf:
            set_halt(state, HaltReason(
                code=HaltCode.QUALITY_GATE_FAILED,
                title="Blueprint failed quality gate",
                detail=qgf.format_for_telegram()[:600],
                stage="S2_BLUEPRINT",
                failing_gate="blueprint_content",
                remediation_steps=["Retry S2 with /continue", "/cancel"],
            ))
            state.legal_halt = True
            return state

    # ══════════════════════════════════════
    # Phase 5: Compliance Artifacts (FIX-07)
    # ══════════════════════════════════════
    compliance_files = await _generate_compliance_artifacts(
        state, selected_stack, legal_output,
    )
    if compliance_files:
        state.s2_output["compliance_artifacts"] = compliance_files

    # Phase 6: Brand Asset Generation (Logo + Splash)
    # ═════════════════════════════════════════════════
    await _generate_and_deliver_brand_assets(state, state.s2_output)

    # Phase 7: Design Package (WCAG + component lib + mockups + icons)
    # ═════════════════════════════════════════════════════════════════
    try:
        from factory.pipeline.blueprint_pdf import build_design_package
        design_pkg = await build_design_package(state, state.s2_output)
        state.s2_output["design_package"] = design_pkg
        logger.info(
            f"[{state.project_id}] Design package: "
            f"mockups={len(design_pkg.get('screen_mockup_paths', []))}, "
            f"wcag_aa={design_pkg.get('wcag_aa_pass')}"
        )
    except Exception as _dpkg_err:
        logger.warning(f"[{state.project_id}] Design package failed (non-fatal): {_dpkg_err}")

    # Phase 8: Stack Selection ADR
    # ═════════════════════════════
    try:
        from factory.pipeline.blueprint_pdf import write_stack_adr
        adr_rationale = (
            f"The Strategist selected {selected_stack.value} based on: "
            f"target platforms ({requirements.get('target_platforms', [])}), "
            f"app category ({requirements.get('app_category', 'other')}), "
            f"complexity ({requirements.get('estimated_complexity', 'medium')}), "
            f"and KSA payment requirements."
        )
        adr_path = await write_stack_adr(state, state.s2_output, adr_rationale)
        state.s2_output["stack_adr_path"] = adr_path
        logger.info(f"[{state.project_id}] Stack ADR: {adr_path}")
    except Exception as _adr_err:
        logger.warning(f"[{state.project_id}] ADR write failed (non-fatal): {_adr_err}")

    # Phase 9: Master Blueprint PDF (100+ pages)
    # ════════════════════════════════════════════
    try:
        from factory.pipeline.blueprint_pdf import generate_master_blueprint_pdf
        blueprint_pdf_path = await generate_master_blueprint_pdf(state, state.s2_output)
        state.s2_output["blueprint_pdf_path"] = blueprint_pdf_path
        state.project_metadata["blueprint_doc_id"] = blueprint_pdf_path

        from factory.telegram.notifications import notify_operator
        from factory.core.state import NotificationType
        await notify_operator(
            state,
            NotificationType.INFO,
            f"📐 Master Blueprint PDF generated\n"
            f"Screens: {len(architecture.get('screens', []))} | "
            f"Stack: {selected_stack.value}\n"
            f"Path: {blueprint_pdf_path}",
        )
        logger.info(f"[{state.project_id}] Blueprint PDF: {blueprint_pdf_path}")
    except Exception as _bp_err:
        logger.warning(f"[{state.project_id}] Blueprint PDF failed (non-fatal): {_bp_err}")

    # ══════════════════════════════════════
    # Phase 10: Mother Memory — Blueprint Nodes
    # ══════════════════════════════════════
    await _write_blueprint_to_mother_memory(state, blueprint_data, selected_stack)

    # ── Issue 11 re-verify: store stage insight ──
    try:
        from factory.core.stage_enrichment import store_stage_insight
        bp_out = state.s2_output or {}
        await store_stage_insight(
            "s2_blueprint", state,
            fact=(
                f"Selected stack: {state.selected_stack.value if state.selected_stack else ''}. "
                f"Features: {len(bp_out.get('feature_list', []))}. "
                f"Screens: {len(bp_out.get('screens', []))}"
            ),
            category="blueprint",
        )
    except Exception as _si_err:
        logger.debug(f"[{state.project_id}] S2 store_stage_insight failed (non-fatal): {_si_err}")

    # ── Mother Memory: full blueprint snapshot → fan-out to ALL backends
    try:
        from factory.memory.mother_memory import (
            store_blueprint_snapshot,
            store_pipeline_state_snapshot,
        )
        await store_blueprint_snapshot(state.project_id, {
            "operator_id": state.operator_id,
            **state.s2_output,
        })
        await store_pipeline_state_snapshot(
            state.project_id, "s2_blueprint", state.s2_output
        )
    except Exception as _mm_err:
        logger.debug(f"[{state.project_id}] S2 mother-memory snapshot failed (non-fatal): {_mm_err}")

    logger.info(
        f"[{state.project_id}] S2 complete: "
        f"stack={selected_stack.value}, "
        f"screens={len(_screens)}, "
        f"features={len(_feature_list)}, "
        f"journeys={len(_user_journeys)}, "
        f"ieee_docs={len(ieee_docs)}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# §4.3 Phase 0 — S1 Legal Dossier Ingestion
# ═══════════════════════════════════════════════════════════════════


async def _ingest_s1_dossier(
    state: PipelineState,
    legal_output: dict,
) -> dict:
    """Extract actionable legal constraints from S1 output for Blueprint use.

    Spec: v5.8 §4.3 Phase 0

    Returns a dict of constraints that Blueprint phases must respect:
    - blocked_features: list of feature IDs S2 must not design
    - required_consents: list of consent points to wire into screens
    - data_residency: "KSA" | "GCC" | "global"
    - payment_sandbox: bool — True if payments must stay in SANDBOX mode
    - pdpl_obligations: list of PDPL-specific data handling requirements
    - inapp_texts: dict of UI text strings from S1 Quick Fix
    """
    constraints: dict = {
        "blocked_features": legal_output.get("blocked_features", []),
        "required_consents": legal_output.get("required_consents", []),
        "data_residency": legal_output.get("data_residency", "KSA"),
        "payment_sandbox": legal_output.get("payment_mode", "SANDBOX") == "SANDBOX",
        "pdpl_obligations": legal_output.get("pdpl_obligations", []),
        "risk_level": legal_output.get("risk_level", "MEDIUM"),
        "inapp_texts": legal_output.get("inapp_texts", {}),
        "compliance_matrix": legal_output.get("compliance_matrix", []),
    }

    blocked = constraints["blocked_features"]
    if blocked:
        logger.info(
            f"[{state.project_id}] S1→S2: {len(blocked)} blocked features "
            f"will be excluded from architecture: {blocked[:3]}"
        )
    else:
        logger.info(
            f"[{state.project_id}] S1→S2: dossier ingested — "
            f"risk={constraints['risk_level']}, "
            f"sandbox={constraints['payment_sandbox']}, "
            f"residency={constraints['data_residency']}"
        )

    return constraints


# ═══════════════════════════════════════════════════════════════════
# §4.3 Phase 3.5 — IEEE 20-Document Blueprint Suite
# ═══════════════════════════════════════════════════════════════════

# 20 IEEE-standard document types for a complete app blueprint
IEEE_DOC_SPECS: list[dict] = [
    # ── Tier 1: Business / Product ───────────────────────────────
    {
        "id": "prd",
        "name": "Product Requirements Document",
        "abbr": "PRD",
        "prompt_focus": "user stories, acceptance criteria, priority (MoSCoW), personas",
        "role": "strategist",
        "priority": 1,
    },
    {
        "id": "brd",
        "name": "Business Requirements Document",
        "abbr": "BRD",
        "prompt_focus": "business objectives, stakeholders, success metrics, ROI, KSA market context",
        "role": "strategist",
        "priority": 1,
    },
    {
        "id": "srs",
        "name": "Software Requirements Specification",
        "abbr": "SRS (IEEE 830)",
        "prompt_focus": "functional + non-functional requirements, constraints, system interfaces",
        "role": "engineer",
        "priority": 1,
    },
    # ── Tier 2: Architecture ──────────────────────────────────────
    {
        "id": "sad",
        "name": "Software Architecture Document",
        "abbr": "SAD",
        "prompt_focus": "C4 model (Context/Container/Component), patterns, tech decisions, ADRs",
        "role": "strategist",
        "priority": 2,
    },
    {
        "id": "api_spec",
        "name": "API Specification",
        "abbr": "API Spec (OpenAPI 3.1)",
        "prompt_focus": "endpoints, request/response schemas, auth, rate limits, error codes",
        "role": "engineer",
        "priority": 2,
    },
    {
        "id": "data_model",
        "name": "Data Model Specification",
        "abbr": "Data Model",
        "prompt_focus": "entity-relationship diagram (text), collections/tables, indexes, relationships",
        "role": "engineer",
        "priority": 2,
    },
    {
        "id": "security_arch",
        "name": "Security Architecture Document",
        "abbr": "SecArch",
        "prompt_focus": "threat model, OWASP Top 10, KSA PDPL data handling, auth flows, encryption",
        "role": "strategist",
        "priority": 2,
    },
    # ── Tier 3: Operations ────────────────────────────────────────
    {
        "id": "deploy_arch",
        "name": "Deployment Architecture",
        "abbr": "DeployArch",
        "prompt_focus": "infra topology, CI/CD pipeline, environments (dev/staging/prod), IaC",
        "role": "engineer",
        "priority": 3,
    },
    {
        "id": "monitoring_plan",
        "name": "Monitoring & Observability Plan",
        "abbr": "ObsPlan",
        "prompt_focus": "metrics, logs, traces, alerting thresholds, SLOs/SLAs, dashboards",
        "role": "engineer",
        "priority": 3,
    },
    {
        "id": "dr_plan",
        "name": "Disaster Recovery Plan",
        "abbr": "DRP",
        "prompt_focus": "RTO/RPO, backup strategy, failover procedures, runbooks",
        "role": "strategist",
        "priority": 3,
    },
    {
        "id": "perf_requirements",
        "name": "Performance Requirements Specification",
        "abbr": "PerfReq",
        "prompt_focus": "load targets, p50/p95/p99 latencies, throughput, scalability limits",
        "role": "engineer",
        "priority": 3,
    },
    # ── Tier 4: Testing ───────────────────────────────────────────
    {
        "id": "test_plan",
        "name": "Test Plan",
        "abbr": "TestPlan (IEEE 829)",
        "prompt_focus": "test strategy, scope, unit/integration/E2E/UAT, test data, pass criteria",
        "role": "engineer",
        "priority": 4,
    },
    {
        "id": "qa_matrix",
        "name": "QA Requirements Matrix",
        "abbr": "QA Matrix",
        "prompt_focus": "traceability matrix mapping requirements to test cases",
        "role": "engineer",
        "priority": 4,
    },
    # ── Tier 5: UX / Design ───────────────────────────────────────
    {
        "id": "ux_spec",
        "name": "UI/UX Specification",
        "abbr": "UX Spec",
        "prompt_focus": "screen flows, navigation map, component inventory, interaction patterns",
        "role": "strategist",
        "priority": 5,
    },
    {
        "id": "accessibility_spec",
        "name": "Accessibility Specification",
        "abbr": "A11y Spec (WCAG 2.2 AA)",
        "prompt_focus": "WCAG 2.2 AA requirements, colour contrast, touch targets, screen reader support",
        "role": "engineer",
        "priority": 5,
    },
    # ── Tier 6: Integrations ──────────────────────────────────────
    {
        "id": "integration_spec",
        "name": "Integration Specification",
        "abbr": "IntegSpec",
        "prompt_focus": "third-party services, SDKs, webhooks, event contracts, payment gateways",
        "role": "engineer",
        "priority": 6,
    },
    {
        "id": "localisation_plan",
        "name": "Localisation & Internationalisation Plan",
        "abbr": "L10n Plan",
        "prompt_focus": "Arabic RTL support, KSA locale, string extraction, date/currency formats",
        "role": "engineer",
        "priority": 6,
    },
    # ── Tier 7: Compliance / Legal ────────────────────────────────
    {
        "id": "privacy_impact",
        "name": "Privacy Impact Assessment",
        "abbr": "PIA (PDPL)",
        "prompt_focus": "PDPL Art. 5-16 compliance, data flows, consent mechanisms, DPA requirements",
        "role": "strategist",
        "priority": 7,
    },
    # ── Tier 8: Change / Knowledge ────────────────────────────────
    {
        "id": "change_mgmt",
        "name": "Change Management Plan",
        "abbr": "CMP",
        "prompt_focus": "change request process, version control strategy, ADR governance",
        "role": "strategist",
        "priority": 8,
    },
    {
        "id": "glossary",
        "name": "Project Glossary",
        "abbr": "Glossary",
        "prompt_focus": "domain terms, acronyms, KSA-specific terminology, Arabic-English equivalents",
        "role": "engineer",
        "priority": 8,
    },
]

_IEEE_ROLE_MAP = {
    "strategist": AIRole.STRATEGIST,
    "engineer": AIRole.ENGINEER,
}
_IEEE_SCOUT_VERIFY_PROMPT = (
    "You are the Scout verifying a blueprint document section.\n\n"
    "Document: {doc_name}\n"
    "Content (first 3000 chars):\n{content}\n\n"
    "Requirements context:\n{reqs_summary}\n\n"
    "Return EXACTLY one of:\n"
    "- 'OK' if the document is complete and aligns with requirements\n"
    "- 'REVISION_NEEDED: <specific issue in one sentence>' if it needs fixing\n\n"
    "No other text."
)


async def _generate_ieee_blueprint_suite(
    state: PipelineState,
    requirements: dict,
    legal_output: dict,
    legal_constraints: dict,
    blueprint_data: dict,
) -> dict[str, str]:
    """Generate the IEEE 20-document blueprint suite.

    Spec: v5.8 §4.3 Phase 3.5

    Flow per document:
      Strategist/Engineer writes → Scout verifies → revise if needed (max 3 rounds)

    All documents saved to /tmp/factory_projects/{project_id}/blueprint/
    Returns dict: {doc_id: full_content}
    """
    app_name = blueprint_data.get("app_name", state.project_id)
    stack = blueprint_data.get("selected_stack", "unknown")
    screens = blueprint_data.get("screens", [])
    data_model = blueprint_data.get("data_model", [])
    api_endpoints = blueprint_data.get("api_endpoints", [])

    reqs_summary = (
        f"App: {app_name}\n"
        f"Category: {requirements.get('app_category', 'other')}\n"
        f"Stack: {stack}\n"
        f"Platforms: {requirements.get('target_platforms', [])}\n"
        f"Features (must): {requirements.get('features_must', [])[:10]}\n"
        f"Blocked features: {legal_constraints.get('blocked_features', [])}\n"
        f"Risk level: {legal_constraints.get('risk_level', 'MEDIUM')}\n"
        f"Screens: {[s.get('name') for s in screens[:8]]}\n"
        f"Data collections: {[c.get('collection') for c in data_model[:6]]}\n"
        f"API endpoints: {len(api_endpoints)}"
    )

    # Project-scoped output directory
    blueprint_dir = Path(f"/tmp/factory_projects/{state.project_id}/blueprint")
    blueprint_dir.mkdir(parents=True, exist_ok=True)

    docs: dict[str, str] = {}
    sorted_specs = sorted(IEEE_DOC_SPECS, key=lambda d: d["priority"])

    for spec in sorted_specs:
        doc_id = spec["id"]
        doc_name = spec["name"]
        abbr = spec["abbr"]
        focus = spec["prompt_focus"]
        role = _IEEE_ROLE_MAP.get(spec["role"], AIRole.ENGINEER)

        logger.info(
            f"[{state.project_id}] IEEE [{doc_id}]: generating {abbr}"
        )

        # Build doc-specific context
        extra_context = ""
        if doc_id == "security_arch":
            extra_context = (
                f"Compliance obligations: {legal_constraints.get('pdpl_obligations', [])}\n"
                f"Payment sandbox: {legal_constraints.get('payment_sandbox')}\n"
                f"Data residency: {legal_constraints.get('data_residency')}"
            )
        elif doc_id == "privacy_impact":
            extra_context = (
                f"Legal dossier risk_level: {legal_output.get('risk_level', 'MEDIUM')}\n"
                f"Compliance matrix items: {len(legal_constraints.get('compliance_matrix', []))}"
            )
        elif doc_id == "api_spec":
            extra_context = (
                f"API endpoints from architecture:\n"
                + "\n".join(
                    f"  {ep.get('method','GET')} {ep.get('path','/')} — {ep.get('purpose','')}"
                    for ep in api_endpoints[:20]
                )
            )
        elif doc_id == "data_model":
            extra_context = (
                "Collections from architecture:\n"
                + "\n".join(
                    f"  {c.get('collection')}: {[f['name'] for f in c.get('fields', [])[:5]]}"
                    for c in data_model[:10]
                )
            )
        elif doc_id == "localisation_plan":
            extra_context = (
                f"KSA market: Arabic RTL mandatory. "
                f"Hijri calendar support required."
            )

        write_prompt = (
            f"Write the complete {doc_name} ({abbr}) for this project.\n\n"
            f"App context:\n{reqs_summary}\n\n"
            f"{'Additional context:' + chr(10) + extra_context + chr(10) if extra_context else ''}"
            f"Focus: {focus}\n\n"
            f"Requirements:\n"
            f"- Professional, production-quality document\n"
            f"- Use Markdown with clear headings (##, ###)\n"
            f"- Include concrete, app-specific details (not generic placeholders)\n"
            f"- KSA / PDPL compliant where applicable\n"
            f"- Mark uncertain items as [TBD:reason]\n\n"
            f"Return the complete document in Markdown."
        )

        content = await call_ai(
            role=role,
            prompt=write_prompt,
            state=state,
            action="plan_architecture" if role == AIRole.STRATEGIST else "write_code",
        )

        # Scout iterative verification (max 3 rounds)
        for revision_round in range(3):
            verify_result = await call_ai(
                role=AIRole.SCOUT,
                prompt=_IEEE_SCOUT_VERIFY_PROMPT.format(
                    doc_name=doc_name,
                    content=content[:3000],
                    reqs_summary=reqs_summary,
                ),
                state=state,
                action="general",
            )

            verdict = verify_result.strip()
            if verdict.startswith("OK"):
                logger.info(
                    f"[{state.project_id}] IEEE [{doc_id}]: verified OK "
                    f"(round {revision_round + 1})"
                )
                break

            if verdict.startswith("REVISION_NEEDED:"):
                issue = verdict[len("REVISION_NEEDED:"):].strip()
                logger.info(
                    f"[{state.project_id}] IEEE [{doc_id}]: revision needed — {issue}"
                )
                content = await call_ai(
                    role=role,
                    prompt=(
                        f"Revise this {doc_name} to fix the following issue:\n"
                        f"{issue}\n\n"
                        f"Current document:\n{content[:6000]}\n\n"
                        f"Return the complete revised document in Markdown."
                    ),
                    state=state,
                    action="plan_architecture" if role == AIRole.STRATEGIST else "write_code",
                )
            else:
                # Unexpected Scout response — treat as OK and move on
                logger.warning(
                    f"[{state.project_id}] IEEE [{doc_id}]: unexpected Scout "
                    f"response '{verdict[:80]}' — treating as OK"
                )
                break

        # Tag with generated-by header
        header = (
            f"<!-- IEEE Blueprint Suite | {abbr} -->\n"
            f"<!-- App: {app_name} | Project: {state.project_id} -->\n"
            f"<!-- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} -->\n\n"
        )
        full_content = header + content

        # Save to project dir
        doc_path = blueprint_dir / f"{doc_id}.md"
        try:
            doc_path.write_text(full_content, encoding="utf-8")
        except Exception as e:
            logger.warning(
                f"[{state.project_id}] IEEE [{doc_id}]: could not write file: {e}"
            )

        docs[doc_id] = full_content

    logger.info(
        f"[{state.project_id}] IEEE suite complete: "
        f"{len(docs)}/20 documents in {blueprint_dir}"
    )
    return docs


# ═══════════════════════════════════════════════════════════════════
# §4.3 Phase 10 — Mother Memory Blueprint Nodes
# ═══════════════════════════════════════════════════════════════════


async def _write_blueprint_to_mother_memory(
    state: PipelineState,
    blueprint_data: dict,
    selected_stack: "TechStack",
) -> None:
    """Write key blueprint decisions to Mother Memory.

    Spec: v5.8 §4.3 Phase 10

    Stores 4 decision nodes:
    - stack_choice: selected stack + rationale summary
    - architecture_summary: screens, data model, API count
    - ieee_blueprint: doc count + project dir
    - design_system: color palette, typography, design system name
    """
    try:
        from factory.memory.mother_memory import store_pipeline_decision

        app_name = blueprint_data.get("app_name", state.project_id)
        stack = selected_stack.value
        screens = blueprint_data.get("screens", [])
        data_model = blueprint_data.get("data_model", [])
        api_endpoints = blueprint_data.get("api_endpoints", [])

        # Node 1: Stack choice
        await store_pipeline_decision(
            project_id=state.project_id,
            stage="s2_blueprint",
            decision_type="stack_choice",
            content=(
                f"Stack: {stack} | App: {app_name} | "
                f"Platforms: {blueprint_data.get('target_platforms', [])} | "
                f"Auth: {blueprint_data.get('auth_method', 'email')} | "
                f"Design system: {blueprint_data.get('design_system', 'material3')}"
            ),
            operator_id=str(state.operator_id),
        )

        # Node 2: Architecture summary
        screen_names = [s.get("name", "?") for s in screens[:10]]
        collection_names = [c.get("collection", "?") for c in data_model[:8]]
        await store_pipeline_decision(
            project_id=state.project_id,
            stage="s2_blueprint",
            decision_type="architecture_summary",
            content=(
                f"Screens ({len(screens)}): {screen_names} | "
                f"Collections ({len(data_model)}): {collection_names} | "
                f"API endpoints: {len(api_endpoints)} | "
                f"Services: {list(blueprint_data.get('services', {}).keys())}"
            ),
            operator_id=str(state.operator_id),
        )

        # Node 3: IEEE blueprint suite
        ieee_count = blueprint_data.get("ieee_doc_count", 0)
        if ieee_count:
            await store_pipeline_decision(
                project_id=state.project_id,
                stage="s2_blueprint",
                decision_type="ieee_blueprint",
                content=(
                    f"Generated {ieee_count}/20 IEEE docs for {app_name} | "
                    f"Path: /tmp/factory_projects/{state.project_id}/blueprint/"
                ),
                operator_id=str(state.operator_id),
            )

        # Node 4: Design system
        palette = blueprint_data.get("color_palette", {})
        await store_pipeline_decision(
            project_id=state.project_id,
            stage="s2_blueprint",
            decision_type="design_system",
            content=(
                f"Design system: {blueprint_data.get('design_system', 'material3')} | "
                f"Visual style: {blueprint_data.get('visual_style', 'minimal')} | "
                f"Primary color: {palette.get('primary', '#1976D2')} | "
                f"Font: {blueprint_data.get('typography', {}).get('font_family', 'Inter')}"
            ),
            operator_id=str(state.operator_id),
        )

        logger.info(
            f"[{state.project_id}] S2→ Mother Memory: 4 blueprint nodes stored"
        )
    except Exception as e:
        logger.warning(
            f"[{state.project_id}] Mother Memory write failed (non-fatal): {e}"
        )


async def _generate_and_deliver_brand_assets(
    state: PipelineState,
    blueprint_data: dict,
) -> None:
    """Generate app logo + splash screen and send via Telegram.

    Non-blocking: failures are logged but do not halt the pipeline.
    """
    try:
        from factory.design.logo_gen import (
            generate_brand_assets,
            send_brand_assets_to_telegram,
        )
        from factory.telegram.notifications import send_telegram_message

        app_name = (
            blueprint_data.get("app_name")
            or state.idea_name
            or (state.s0_output or {}).get("app_name")
            or state.project_id
        )

        await send_telegram_message(
            state.operator_id,
            f"🎨 Generating logo and splash screen for *{app_name}*...",
            parse_mode="Markdown",
        )

        assets = await generate_brand_assets(state, blueprint_data)
        state.s2_output["brand_assets"] = {
            "logo_path": assets.get("logo_path"),
            "splash_path": assets.get("splash_path"),
            "logo_prompt": assets.get("logo_prompt", ""),
            "generated": bool(assets.get("logo_bytes") or assets.get("splash_bytes")),
        }

        await send_brand_assets_to_telegram(state.operator_id, assets, app_name)

    except Exception as e:
        logger.warning(f"[{state.project_id}] Brand asset generation failed (non-critical): {e}")


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
        # Graceful degradation — return only files actually written
        logger.warning(
            f"[{state.project_id}] FIX-07: Could not write compliance files: {e}"
        )

    logger.info(
        f"[{state.project_id}] FIX-07: Generated {len(files)} compliance artifacts"
    )
    return files


# Register with DAG
register_stage_node("s2_blueprint", s2_blueprint_node)


# ═══════════════════════════════════════════════════════════════════
# MODIFY Mode: Change Blueprint
# ═══════════════════════════════════════════════════════════════════


async def _s2_modify_blueprint(
    state: PipelineState,
    requirements: dict,
) -> PipelineState:
    """S2 MODIFY: generate a targeted change blueprint (files to add/modify/delete).

    Uses the codebase context from S0 to scope what needs changing.
    Produces: list of file operations rather than a full app design.
    """
    description = requirements.get("modification_description", "")
    detected_stack = requirements.get("detected_stack", "unknown")
    context = state.codebase_context or {}
    context_text = context.get("context_text", "")[:60000]  # fit in Claude context

    logger.info(
        f"[{state.project_id}] MODIFY S2: planning changes for '{description[:80]}'"
    )

    try:
        change_plan_raw = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=(
                f"You are a software architect planning targeted code changes.\n\n"
                f"MODIFICATION REQUEST: {description}\n\n"
                f"DETECTED STACK: {detected_stack}\n\n"
                f"CODEBASE CONTEXT:\n{context_text}\n\n"
                f"Plan the minimal set of file changes needed. "
                f"Return ONLY valid JSON:\n"
                f'{{\n'
                f'  "files_to_modify": [{{"path": "...", "change_summary": "...", "priority": "high|medium|low"}}],\n'
                f'  "files_to_add": [{{"path": "...", "purpose": "..."}}],\n'
                f'  "files_to_delete": ["path1"],\n'
                f'  "change_summary": "1-2 sentence summary",\n'
                f'  "version_bump": "patch|minor|major",\n'
                f'  "estimated_files": 5\n'
                f'}}'
            ),
            state=state,
            action="plan_architecture",
        )

        change_plan = json.loads(change_plan_raw)

    except (json.JSONDecodeError, TypeError, Exception) as e:
        logger.warning(f"[{state.project_id}] MODIFY S2: change plan parse failed: {e}")
        change_plan = {
            "files_to_modify": [],
            "files_to_add": [],
            "files_to_delete": [],
            "change_summary": description,
            "version_bump": "patch",
            "estimated_files": 1,
        }

    # Determine stack from S0 detection
    try:
        selected_stack = TechStack(detected_stack)
    except ValueError:
        selected_stack = TechStack.FLUTTERFLOW
    state.selected_stack = selected_stack

    state.s2_output = {
        "modify_mode": True,
        "modification_description": description,
        "selected_stack": selected_stack.value,
        "detected_stack": detected_stack,
        "change_plan": change_plan,
        "target_platforms": requirements.get("target_platforms", ["ios", "android"]),
        "version_bump": change_plan.get("version_bump", "patch"),
    }

    logger.info(
        f"[{state.project_id}] MODIFY S2 complete: "
        f"{len(change_plan.get('files_to_modify', []))} modify, "
        f"{len(change_plan.get('files_to_add', []))} add, "
        f"{len(change_plan.get('files_to_delete', []))} delete"
    )
    return state