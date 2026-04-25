"""
AI Factory Pipeline v5.8 — S3 Design Node (Full Real Implementation)

Implements:
  - §4.3 S3 Design (Phase 5 of v5.8 rewire)
  - Project-type detection: Standard App, Mobile/PC/Console Game, AR/VR,
    Medical, Educational, E-commerce, Dashboard, Creative Tool
  - 3 sub-modes: Autopilot / One-by-One / User Control
  - Standard App: Vibe Check → design system → screen mockups → platform assets
  - Game Projects: GDD, Art Bible, Sprite Manifest, Level Design, HUD Spec,
    Audio Design, VFX/Particle Spec, Platform Certification Requirements
  - Specialist: AR/VR spatial design, Medical clinical workflow, Educational
    taxonomy, E-commerce catalog design, Dashboard data viz, Creative Tool canvas
  - Scout design research per project type
  - Mother Memory: (:Project)-[:HAS_DESIGN]->(:DesignSystem)

Spec Authority: v5.8 §4.3 (Phase 5)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from factory.core.state import (
    AIRole,
    AutonomyMode,
    PipelineState,
    Stage,
)
from factory.core.roles import call_ai
from factory.pipeline.graph import pipeline_node, register_stage_node
from factory.pipeline.stage_chain import inject_chain_context as _inject_cc

logger = logging.getLogger("factory.pipeline.s3_design")


# ═══════════════════════════════════════════════════════════════════
# Project Design Type — Detection & Routing
# ═══════════════════════════════════════════════════════════════════

class ProjectDesignType(str, Enum):
    STANDARD_APP    = "standard_app"
    MOBILE_GAME     = "mobile_game"
    PC_GAME         = "pc_game"
    CONSOLE_GAME    = "console_game"
    AR_VR           = "ar_vr"
    MEDICAL         = "medical"
    EDUCATIONAL     = "educational"
    ECOMMERCE       = "ecommerce"
    DASHBOARD       = "dashboard"
    CREATIVE_TOOL   = "creative_tool"


# Keyword → project type mapping (checked in order; first match wins)
_TYPE_KEYWORDS: list[tuple[ProjectDesignType, list[str]]] = [
    (ProjectDesignType.CONSOLE_GAME, [
        "console", "playstation", "xbox", "nintendo", "switch", "ps5", "ps4",
        "game console", "tvos game", "controller", "gamepad",
    ]),
    (ProjectDesignType.PC_GAME, [
        "pc game", "steam", "windows game", "linux game", "macos game",
        "unity pc", "unreal", "godot", "indie game", "desktop game",
    ]),
    (ProjectDesignType.MOBILE_GAME, [
        "mobile game", "game", "puzzle", "arcade", "rpg", "strategy game",
        "casual game", "clicker", "runner", "shooter", "platformer", "card game",
        "board game", "match-3", "tower defense", "idle game", "hyper-casual",
    ]),
    (ProjectDesignType.AR_VR, [
        "ar", "vr", "augmented reality", "virtual reality", "mixed reality",
        "spatial", "xr", "arkit", "arcore", "oculus", "quest", "visionos",
        "apple vision", "holographic", "metaverse",
    ]),
    (ProjectDesignType.MEDICAL, [
        "medical", "health", "clinic", "hospital", "patient", "ehr", "emr",
        "telemedicine", "pharmacy", "drug", "diagnosis", "healthcare", "nurse",
        "doctor", "fda", "hipaa", "dicom",
    ]),
    (ProjectDesignType.EDUCATIONAL, [
        "education", "learning", "school", "student", "teacher", "course",
        "e-learning", "edtech", "quiz", "lesson", "curriculum", "lms",
        "tutoring", "flashcard",
    ]),
    (ProjectDesignType.ECOMMERCE, [
        "shop", "store", "ecommerce", "e-commerce", "marketplace", "product",
        "cart", "checkout", "order", "merchant", "retail", "inventory",
    ]),
    (ProjectDesignType.DASHBOARD, [
        "dashboard", "analytics", "bi", "business intelligence", "data viz",
        "chart", "graph", "kpi", "reporting", "monitoring", "metrics",
    ]),
    (ProjectDesignType.CREATIVE_TOOL, [
        "photo editor", "video editor", "drawing", "painting", "design tool",
        "canvas", "vector", "illustration", "daw", "music production",
        "recording", "creative", "art tool", "figma", "sketch",
    ]),
]


def _detect_project_type(
    requirements: dict,
    blueprint_data: dict,
) -> ProjectDesignType:
    """Detect the project design type from requirements and blueprint.

    Checks: app_category, app_description, features_must, selected_stack.
    Returns the most specific matching ProjectDesignType.
    Uses whole-word boundary matching to avoid false positives
    (e.g. "product" must not match "productivity").
    """
    # Build a combined haystack for keyword search
    category    = (requirements.get("app_category") or "").lower()
    description = (requirements.get("app_description") or "").lower()
    features    = " ".join(str(f) for f in requirements.get("features_must", [])).lower()
    stack       = (blueprint_data.get("selected_stack") or "").lower()
    haystack    = f"{category} {description} {features} {stack}"

    def _word_match(keyword: str, text: str) -> bool:
        """True if keyword appears as a whole word/phrase in text."""
        # Escape for regex, then add word boundaries
        escaped = re.escape(keyword)
        return bool(re.search(rf"\b{escaped}\b", text))

    for ptype, keywords in _TYPE_KEYWORDS:
        for kw in keywords:
            if _word_match(kw, haystack):
                logger.info(
                    f"Detected project type: {ptype.value} (matched '{kw}')"
                )
                return ptype

    # Unity stack without game keywords → still likely a game
    if "unity" in stack:
        return ProjectDesignType.MOBILE_GAME

    return ProjectDesignType.STANDARD_APP


# Design sub-mode constants
DESIGN_SUBMODE_AUTOPILOT    = "autopilot"
DESIGN_SUBMODE_ONE_BY_ONE   = "one_by_one"
DESIGN_SUBMODE_USER_CONTROL = "user_control"


# ═══════════════════════════════════════════════════════════════════
# S3 Design Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S3_DESIGN)
async def s3_design_node(state: PipelineState) -> PipelineState:
    """S3: Design — full real implementation.

    Spec: §4.3 (v5.8 Phase 5)

    Flow:
      1. Detect project type (game / AR-VR / medical / educational / standard…)
      2. Vibe Check — Scout trend research → design DNA
      3. Route to specialist asset generator for this project type
      4. Sub-mode approval loop (Autopilot / One-by-One / User Control)
      5. Screen mockups (all types)
      6. Platform-specific asset specs
      7. Mother Memory persistence
    """
    blueprint_data = state.s2_output or {}
    requirements   = state.s0_output or {}
    app_name       = blueprint_data.get("app_name") or state.idea_name or state.project_id
    screens        = blueprint_data.get("screens") or []

    design_submode = state.project_metadata.get("design_submode", DESIGN_SUBMODE_AUTOPILOT)
    target_platforms = requirements.get("target_platforms", ["ios", "android"])

    logger.info(
        f"[{state.project_id}] S3 Design: app='{app_name}', "
        f"submode={design_submode}"
    )

    # ── 1. Project type detection ──
    project_type = _detect_project_type(requirements, blueprint_data)
    logger.info(f"[{state.project_id}] Project design type: {project_type.value}")

    # ── 2. Vibe Check — design DNA for all types ──
    vibe = await _run_vibe_check(state, requirements, blueprint_data, project_type)

    # ── 3. Specialist asset generation ──
    specialist_output: dict = {}
    if project_type in (
        ProjectDesignType.MOBILE_GAME,
        ProjectDesignType.PC_GAME,
        ProjectDesignType.CONSOLE_GAME,
    ):
        specialist_output = await _generate_game_assets(
            state, requirements, blueprint_data, vibe, project_type,
            design_submode,
        )
    elif project_type == ProjectDesignType.AR_VR:
        specialist_output = await _generate_ar_vr_assets(
            state, requirements, blueprint_data, vibe, design_submode,
        )
    elif project_type == ProjectDesignType.MEDICAL:
        specialist_output = await _generate_medical_assets(
            state, requirements, blueprint_data, vibe, design_submode,
        )
    elif project_type == ProjectDesignType.EDUCATIONAL:
        specialist_output = await _generate_educational_assets(
            state, requirements, blueprint_data, vibe, design_submode,
        )
    elif project_type == ProjectDesignType.ECOMMERCE:
        specialist_output = await _generate_ecommerce_assets(
            state, requirements, blueprint_data, vibe, design_submode,
        )
    elif project_type == ProjectDesignType.DASHBOARD:
        specialist_output = await _generate_dashboard_assets(
            state, requirements, blueprint_data, vibe, design_submode,
        )
    elif project_type == ProjectDesignType.CREATIVE_TOOL:
        specialist_output = await _generate_creative_tool_assets(
            state, requirements, blueprint_data, vibe, design_submode,
        )
    else:
        specialist_output = await _generate_standard_design(
            state, requirements, blueprint_data, vibe, design_submode,
        )

    # ── 4. Screen mockups (all types) ──
    mockup_paths = await _generate_screen_mockups(
        state, screens, blueprint_data, vibe, project_type,
    )

    # ── 5. Platform asset specs ──
    platform_assets = await _generate_platform_assets(
        state, requirements, blueprint_data, app_name, project_type,
    )

    # ── 6. Logo passthrough ──
    logo_path = (
        state.project_metadata.get("logo_path")
        or (state.s0_output or {}).get("logo_path")
        or blueprint_data.get("logo_path")
    )

    # ── Assemble output ──
    state.s3_output = {
        "project_type": project_type.value,
        "design_submode": design_submode,
        "app_name": app_name,
        "vibe": vibe,
        "design_system": vibe,
        "color_palette": vibe.get("color_palette", {}),
        "typography": vibe.get("typography", {}),
        "spacing": vibe.get("spacing", {}),
        "visual_style": vibe.get("visual_style", "minimal"),
        "screens": screens,
        "mockup_paths": mockup_paths,
        "platform_assets": platform_assets,
        "logo_path": logo_path,
        "specialist": specialist_output,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── 7. Mother Memory ──
    await _write_design_to_mother_memory(state, project_type, state.s3_output)

    # ── Issue 11 re-verify: store stage insight ──
    try:
        from factory.core.stage_enrichment import store_stage_insight
        await store_stage_insight(
            "s3_design", state,
            fact=(
                f"Design type: {state.s3_output.get('design_type', state.s3_output.get('project_type', ''))}. "
                f"Assets: {len(state.s3_output.get('design_assets', state.s3_output.get('platform_assets', [])))}"
            ),
            category="design",
        )
    except Exception as _si_err:
        logger.debug(f"[{state.project_id}] S3 store_stage_insight failed (non-fatal): {_si_err}")

    # Mother Memory: full S3 output snapshot → fan-out to ALL backends
    try:
        from factory.memory.mother_memory import store_pipeline_state_snapshot
        await store_pipeline_state_snapshot(
            state.project_id, "s3_design", state.s3_output
        )
    except Exception:
        pass

    # ── Operator summary notification ──
    try:
        from factory.telegram.notifications import notify_operator
        from factory.core.state import NotificationType

        doc_count = len([k for k in specialist_output if k.endswith("_doc") or k.endswith("_spec") or k.endswith("_manifest") or k.endswith("_bible") or k.endswith("_plan")])
        await notify_operator(
            state,
            NotificationType.INFO,
            f"🎨 S3 Design complete\n"
            f"Type: {project_type.value} | Sub-mode: {design_submode}\n"
            f"Mockups: {len(mockup_paths)} screens\n"
            f"Specialist docs: {doc_count}\n"
            f"Visual style: {vibe.get('visual_style', 'minimal')}",
        )
    except Exception as e:
        logger.warning(f"[{state.project_id}] S3 notify failed (non-fatal): {e}")

    logger.info(
        f"[{state.project_id}] S3 Design complete: "
        f"type={project_type.value}, "
        f"mockups={len(mockup_paths)}, "
        f"specialist_keys={list(specialist_output.keys())[:6]}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# Vibe Check — Design DNA (all project types)
# ═══════════════════════════════════════════════════════════════════


async def _run_vibe_check(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    project_type: ProjectDesignType,
) -> dict:
    """Run Vibe Check adapted for the detected project type.

    Falls back to existing design data from S2 if the vibe check fails.
    """
    try:
        from factory.design.vibe_check import vibe_check
        return await vibe_check(state, requirements)
    except Exception as e:
        logger.warning(f"[{state.project_id}] Vibe Check failed: {e} — using S2 design")
        return {
            "color_palette": blueprint_data.get("color_palette", {
                "primary": "#1976D2", "secondary": "#FF9800",
                "background": "#FFFFFF", "surface": "#F5F5F5",
                "text_primary": "#212121", "text_secondary": "#757575",
                "accent": "#03DAC6", "error": "#B00020",
            }),
            "typography": blueprint_data.get("typography", {
                "heading_font": "Inter", "body_font": "Inter", "size_base": 16,
            }),
            "spacing": {"unit": 4, "page_padding": 16, "card_padding": 12},
            "visual_style": blueprint_data.get("visual_style", "minimal"),
            "layout_patterns": blueprint_data.get("layout_patterns", ["cards", "bottom_nav"]),
            "design_system": blueprint_data.get("design_system", "material3"),
        }


# ═══════════════════════════════════════════════════════════════════
# Sub-Mode Approval Helper
# ═══════════════════════════════════════════════════════════════════


async def _submode_approval(
    state: PipelineState,
    asset_name: str,
    content: str,
    design_submode: str,
) -> str:
    """Apply sub-mode approval gate to a generated design asset.

    Autopilot: return content as-is.
    One-by-One: COPILOT operator sees a preview + 3-option menu.
    User Control: COPILOT operator provides their own content (or skips).
    """
    if design_submode == DESIGN_SUBMODE_AUTOPILOT:
        return content

    try:
        from factory.telegram.decisions import present_decision, wait_for_operator_reply
        from factory.telegram.notifications import send_telegram_message

        if design_submode == DESIGN_SUBMODE_ONE_BY_ONE:
            # Show 600-char preview
            preview = content[:600] + ("…" if len(content) > 600 else "")
            choice = await present_decision(
                state=state,
                decision_type="design_approval",
                question=(
                    f"*{asset_name}* — review generated design:\n\n"
                    f"```\n{preview}\n```\n\n"
                    f"Approve or request revision?"
                ),
                options=[
                    {"label": "Approve — use this", "value": "approve"},
                    {"label": "Revise — regenerate", "value": "revise"},
                    {"label": "Skip — leave blank", "value": "skip"},
                ],
                recommended=0,
            )
            if choice == "revise":
                await send_telegram_message(
                    state.operator_id,
                    f"Describe your revision for *{asset_name}*:",
                    parse_mode="Markdown",
                )
                feedback = await wait_for_operator_reply(state, timeout_seconds=900)
                # Regenerate with operator feedback
                revised = await call_ai(
                    role=AIRole.ENGINEER,
                    prompt=(
                        f"Revise this design document ({asset_name}) based on feedback:\n\n"
                        f"Feedback: {feedback}\n\n"
                        f"Original:\n{content[:4000]}\n\n"
                        f"Return the complete revised document in Markdown."
                    ),
                    state=state,
                    action="write_code",
                )
                return revised
            elif choice == "skip":
                return f"<!-- {asset_name}: skipped by operator -->"
            return content  # approved

        elif design_submode == DESIGN_SUBMODE_USER_CONTROL:
            choice = await present_decision(
                state=state,
                decision_type="design_upload",
                question=f"*{asset_name}* — provide your own spec or use AI-generated?",
                options=[
                    {"label": "Use AI-generated", "value": "ai"},
                    {"label": "Type my own spec", "value": "type"},
                    {"label": "Skip this asset", "value": "skip"},
                ],
                recommended=0,
            )
            if choice == "type":
                await send_telegram_message(
                    state.operator_id,
                    f"Type your spec for *{asset_name}* (send when done):",
                    parse_mode="Markdown",
                )
                user_content = await wait_for_operator_reply(state, timeout_seconds=1800)
                return user_content
            elif choice == "skip":
                return f"<!-- {asset_name}: skipped by operator -->"
            return content

    except Exception as e:
        logger.warning(
            f"[{state.project_id}] Sub-mode approval for {asset_name} failed: {e} — using AI output"
        )

    return content


# ═══════════════════════════════════════════════════════════════════
# Standard App Design Pipeline
# ═══════════════════════════════════════════════════════════════════


async def _generate_standard_design(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    design_submode: str,
) -> dict:
    """Generate standard app design package.

    Produces: component library spec, design tokens, onboarding illustration brief.
    """
    app_name = blueprint_data.get("app_name", state.project_id)
    screens  = blueprint_data.get("screens", [])

    # Component library spec
    _comp_base = (
        f"Write a Component Library Specification for '{app_name}'.\n\n"
        f"Design system: {vibe.get('design_system', 'material3')}\n"
        f"Visual style: {vibe.get('visual_style', 'minimal')}\n"
        f"Color palette: {json.dumps(vibe.get('color_palette', {}))}\n"
        f"Screens: {[s.get('name') for s in screens[:12]]}\n\n"
        f"List all reusable UI components with: name, purpose, variants, "
        f"state (default/hover/pressed/disabled), props. "
        f"Cover: buttons, inputs, cards, navigation, modals, loaders. "
        f"Return Markdown."
    )
    comp_lib_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=_inject_cc(_comp_base, state, current_stage="s3_design", compact=True),
        state=state,
        action="plan_architecture",
    )
    comp_lib = await _submode_approval(state, "Component Library", comp_lib_raw, design_submode)

    # Design tokens
    tokens_raw = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Generate design tokens for '{app_name}' as JSON.\n"
            f"Include: color tokens, typography tokens, spacing tokens, "
            f"border-radius tokens, shadow tokens, animation duration tokens.\n"
            f"Base values:\n{json.dumps(vibe, indent=2)[:2000]}\n\n"
            f"Return a flat JSON object: {{\"token-name\": \"value\"}}\n"
            f"Use kebab-case. Example: {{\"color-primary\": \"#1976D2\"}}"
        ),
        state=state,
        action="write_code",
    )
    tokens = await _submode_approval(state, "Design Tokens", tokens_raw, design_submode)

    return {
        "component_library_doc": comp_lib,
        "design_tokens": tokens,
    }


# ═══════════════════════════════════════════════════════════════════
# Game Asset Suite — Mobile / PC / Console
# ═══════════════════════════════════════════════════════════════════

_GAME_PLATFORM_NOTES: dict[ProjectDesignType, str] = {
    ProjectDesignType.MOBILE_GAME: (
        "Mobile platforms (iOS/Android). Touch controls. Portrait/landscape. "
        "Performance budget: 60fps on mid-tier devices (2GB RAM). "
        "IAP integration points. Rewarded ad placement zones. "
        "Offline capability. Small download size (<100MB preferred)."
    ),
    ProjectDesignType.PC_GAME: (
        "PC platforms (Windows/macOS/Linux). Keyboard + mouse primary. "
        "Optional controller support. Resolution support: 1080p, 1440p, 4K. "
        "Steam integration (achievements, cloud saves, leaderboards). "
        "Scalable graphics settings (low/medium/high/ultra). "
        "Windowed, borderless, fullscreen modes."
    ),
    ProjectDesignType.CONSOLE_GAME: (
        "Console platforms. Controller-first design. HDR10/Dolby Vision support. "
        "Platform certification: Xbox TRC, PlayStation TCR, Nintendo LotCheck. "
        "Accessibility requirements: Xbox Accessibility Guidelines, "
        "PlayStation Accessibility Features. 4K/60fps or 1080p/120fps targets. "
        "No cursor UI — all navigation must work with D-pad + buttons."
    ),
}


async def _generate_game_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    game_type: ProjectDesignType,
    design_submode: str,
) -> dict:
    """Generate the full game asset design suite.

    Documents:
      1. GDD (Game Design Document)
      2. Art Bible
      3. Sprite & Asset Manifest
      4. Level Design Document
      5. HUD & UI Design Spec
      6. Audio Design Spec
      7. VFX & Particle Effects Spec
      8. Platform Certification Requirements
    """
    app_name    = blueprint_data.get("app_name", state.project_id)
    description = requirements.get("app_description", "")
    category    = requirements.get("app_category", "game")
    features    = requirements.get("features_must", [])
    platform_note = _GAME_PLATFORM_NOTES.get(game_type, "")
    stack       = blueprint_data.get("selected_stack", "unity")

    base_ctx = (
        f"Game: {app_name}\n"
        f"Description: {description}\n"
        f"Category/Genre: {category}\n"
        f"Core features: {features[:8]}\n"
        f"Stack: {stack}\n"
        f"Platform notes: {platform_note}\n"
        f"Visual style: {vibe.get('visual_style', 'colorful')}\n"
        f"Color palette: {json.dumps(vibe.get('color_palette', {}))}\n"
    )

    output: dict = {}

    # ── 1. GDD ──────────────────────────────────────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating GDD")
    _gdd_base = (
        f"Write a complete Game Design Document (GDD) for this game.\n\n"
        f"{base_ctx}\n"
        f"Sections required:\n"
        f"## Game Overview — genre, target audience (age/region), platform, ESRB/PEGI rating\n"
        f"## Core Gameplay Loop — the 30-second, 5-minute, and 30-minute loops\n"
        f"## Mechanics — movement, actions, interactions, physics, rules\n"
        f"## Win/Fail Conditions — objectives, failure states, checkpoints\n"
        f"## Progression System — levels, XP, unlocks, difficulty curve\n"
        f"## Economy — in-game currency, IAP items, premium vs free content\n"
        f"## Controls & Input — {platform_note[:100]}\n"
        f"## KSA Market Fit — cultural considerations, Arabic localisation, GCAM rating\n\n"
        f"Return professional Markdown."
    )
    gdd_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=_inject_cc(_gdd_base, state, current_stage="s3_design", compact=True),
        state=state,
        action="plan_architecture",
    )
    output["gdd"] = await _submode_approval(state, "Game Design Document", gdd_raw, design_submode)

    # ── 2. Art Bible ─────────────────────────────────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating Art Bible")
    art_bible_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write an Art Bible for this game.\n\n"
            f"{base_ctx}\n"
            f"Sections required:\n"
            f"## Visual Style — pixel art / vector / 3D / hand-drawn / stylised 3D\n"
            f"## Color Palette — base palette (8-16 colors) + UI palette, with hex codes\n"
            f"## Character Design Guidelines — proportions, silhouette clarity, style references\n"
            f"## Environment & Tile Design — tileset philosophy, parallax layers, biome list\n"
            f"## UI/HUD Style — font choices, icon style, button design, color usage rules\n"
            f"## Animation Guidelines — frame rates, easing curves, squash & stretch\n"
            f"## Do's and Don'ts — specific style rules to maintain consistency\n"
            f"## Reference Board — 5 reference games/artworks with style analysis\n\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["art_bible"] = await _submode_approval(state, "Art Bible", art_bible_raw, design_submode)

    # ── 3. Sprite & Asset Manifest ───────────────────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating Sprite Manifest")
    sprite_raw = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Write a complete Sprite & Asset Manifest for this game.\n\n"
            f"{base_ctx}\n"
            f"For each asset category, list every asset needed with:\n"
            f"  - Asset name, file format, resolution/size, frame count (if animated),\n"
            f"    animation states, notes\n\n"
            f"Categories to cover:\n"
            f"## Player Character Sprites — idle, walk, run, jump, fall, attack, hurt, death\n"
            f"## Enemy/NPC Sprites — all required enemies with same states as player\n"
            f"## Environment Tiles — ground, wall, ceiling, platforms, hazards, decorations\n"
            f"## Collectibles & Power-ups — coins, gems, health pickups, special items\n"
            f"## UI Elements — buttons, health bar, stamina bar, score display, icons\n"
            f"## Background Layers — parallax backgrounds (far/mid/near)\n"
            f"## VFX Sprites — explosions, sparkles, dust puffs, water splash\n"
            f"## Menu & Cutscene Art — main menu bg, loading screen, cutscene frames\n"
            f"## Audio Placeholders — list SFX and music files needed (name + description)\n\n"
            f"Include recommended resolutions for {game_type.value}.\n"
            f"Return structured Markdown with tables."
        ),
        state=state,
        action="write_code",
    )
    output["sprite_manifest"] = await _submode_approval(
        state, "Sprite & Asset Manifest", sprite_raw, design_submode,
    )

    # ── 4. Level Design Document ──────────────────────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating Level Design Doc")
    level_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write a Level Design Document for this game.\n\n"
            f"{base_ctx}\n"
            f"Sections required:\n"
            f"## Level Structure — total level count, world/act organisation\n"
            f"## Difficulty Curve — progression from tutorial to challenge to boss\n"
            f"## Level Template — standard layout blueprint (spawn, obstacles, secrets, exit)\n"
            f"## Tutorial Design — first-5-minutes onboarding, mechanic introduction order\n"
            f"## Boss Encounters — boss count, mechanics, difficulty scaling\n"
            f"## Checkpoint & Save Points — placement philosophy\n"
            f"## Secrets & Collectibles — secret room design, collectible placement density\n"
            f"## Environmental Storytelling — how levels convey narrative without cutscenes\n"
            f"## Biomes/Themes — list of distinct visual themes per world/act\n\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["level_design_doc"] = await _submode_approval(
        state, "Level Design Document", level_raw, design_submode,
    )

    # ── 5. HUD & UI Design Spec ──────────────────────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating HUD Spec")
    hud_raw = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Write a detailed HUD & UI Design Spec for this game.\n\n"
            f"{base_ctx}\n"
            f"Platform constraints: {platform_note}\n\n"
            f"Sections required:\n"
            f"## In-Game HUD Layout — health bar, stamina, ammo, score, timer, minimap position\n"
            f"## HUD Element Specifications — size, position (% of screen), always-visible vs contextual\n"
            f"## Main Menu — layout, background, button hierarchy, animated elements\n"
            f"## Pause Menu — overlay design, options available\n"
            f"## Settings Screen — audio, graphics (if PC/console), controls, language\n"
            f"## Game Over / Victory Screens — layout, stats display, CTA buttons\n"
            f"## IAP / Shop UI — item display, pricing, purchase flow (for mobile)\n"
            f"## Onboarding / Tutorial UI — tooltip design, highlight overlays, skip option\n"
            f"## Loading Screen — progress indicator, tips, branding\n"
            f"## Accessibility — colorblind mode, text size options, high-contrast HUD\n\n"
            f"Return professional Markdown with ASCII layout sketches where helpful."
        ),
        state=state,
        action="write_code",
    )
    output["hud_spec"] = await _submode_approval(
        state, "HUD & UI Design Spec", hud_raw, design_submode,
    )

    # ── 6. Audio Design Spec ─────────────────────────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating Audio Spec")
    audio_raw = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Write a complete Audio Design Specification for this game.\n\n"
            f"{base_ctx}\n"
            f"Sections required:\n"
            f"## Music Tracks — list every music cue with: name, mood, tempo (BPM), "
            f"  loop type (seamless/stinger), trigger condition, duration estimate\n"
            f"  Required cues: Main Menu, Gameplay (by biome/act), Boss Fight, "
            f"  Victory, Game Over, Credits\n"
            f"## SFX Library — complete list of sound effects with: name, category, "
            f"  trigger event, variations needed, priority (critical/high/low)\n"
            f"  Categories: Player actions, Enemy actions, Environment, UI, Collectibles, Combat\n"
            f"## Voice-Over — narration script stubs, character VO requirements, "
            f"  Arabic + English line count estimate\n"
            f"## Audio Bus Structure — master, music, SFX, voice buses with target levels (dB)\n"
            f"## Adaptive Audio — how music transitions with gameplay state changes\n"
            f"## Platform Audio Notes — {platform_note[:120]}\n"
            f"## File Format & Compression — OGG/WAV/MP3 per platform, bitrate targets\n\n"
            f"Return professional Markdown with tables."
        ),
        state=state,
        action="write_code",
    )
    output["audio_spec"] = await _submode_approval(
        state, "Audio Design Spec", audio_raw, design_submode,
    )

    # ── 7. VFX & Particle Effects Spec ──────────────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating VFX Spec")
    vfx_raw = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Write a VFX & Particle Effects Specification for this game.\n\n"
            f"{base_ctx}\n"
            f"Sections required:\n"
            f"## Particle Systems — for each effect: name, trigger, emitter type, "
            f"  particle count, lifetime, color gradient, size curve, emission rate\n"
            f"  Required: jump dust, landing impact, attack slash, hit impact, "
            f"  explosion, coin pickup, death, healing, level-up flash, UI hover\n"
            f"## Screen Effects — screen shake (events + intensity + duration), "
            f"  chromatic aberration (trigger conditions), vignette (health warning)\n"
            f"## Post-Processing Stack — bloom, color grading (per biome LUT), "
            f"  motion blur (on/off option), depth of field (cutscenes)\n"
            f"## Juice & Game Feel — hit freeze frames (duration), hitstop, "
            f"  enemy death physics, ragdoll notes\n"
            f"## Performance Budget — max active particle systems, draw call budget\n\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="write_code",
    )
    output["vfx_spec"] = await _submode_approval(
        state, "VFX & Particle Effects Spec", vfx_raw, design_submode,
    )

    # ── 8. Platform Certification Requirements ───────────────────────
    logger.info(f"[{state.project_id}] Game assets: generating Platform Cert Requirements")
    cert_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write Platform Certification Requirements for this game.\n\n"
            f"{base_ctx}\n"
            f"Game type: {game_type.value}\n"
            f"Platform details: {platform_note}\n\n"
            f"Sections required:\n"
            f"## Rating Requirements — GCAM (KSA), ESRB (US), PEGI (EU), IARC (global) "
            f"  — content rating categories, required disclosures, IAP labelling\n"
            f"## Technical Requirements — frame rate targets, load time limits, "
            f"  crash rate thresholds, memory limits per platform\n"
            f"## Accessibility Compliance — mandatory a11y features per platform\n"
            f"## Store Submission Checklist — screenshots, trailer, metadata, "
            f"  age gate implementation, content descriptors\n"
            f"## Legal & Privacy — COPPA compliance (if under-13 audience), "
            f"  PDPL (KSA), GDPR (EU), CCPA (US), privacy nutrition label\n"
            f"{'## Console-Specific Certification — TRC/TCR/LotCheck key requirements' if game_type == ProjectDesignType.CONSOLE_GAME else ''}\n"
            f"{'## Steam Requirements — Steamworks SDK integration, achievements, cloud saves' if game_type == ProjectDesignType.PC_GAME else ''}\n"
            f"{'## Mobile Store Rules — IAP guidelines, rewarded ads policy, anti-cheat' if game_type == ProjectDesignType.MOBILE_GAME else ''}\n\n"
            f"Return professional Markdown checklist."
        ),
        state=state,
        action="plan_architecture",
    )
    output["platform_cert_requirements"] = await _submode_approval(
        state, "Platform Certification Requirements", cert_raw, design_submode,
    )

    # Save all game docs to project dir
    _save_design_docs(state.project_id, "game", output)

    logger.info(
        f"[{state.project_id}] Game asset suite complete: "
        f"{len(output)} documents"
    )
    return output


# ═══════════════════════════════════════════════════════════════════
# Specialist Generators — AR/VR, Medical, Educational, E-commerce,
#                        Dashboard, Creative Tool
# ═══════════════════════════════════════════════════════════════════


async def _generate_ar_vr_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    design_submode: str,
) -> dict:
    """AR/VR: spatial design spec, comfort guidelines, interaction paradigms."""
    app_name = blueprint_data.get("app_name", state.project_id)
    description = requirements.get("app_description", "")
    stack = blueprint_data.get("selected_stack", "unity")

    output: dict = {}

    spatial_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write a Spatial Design Specification for AR/VR app '{app_name}'.\n\n"
            f"Description: {description}\nStack: {stack}\n\n"
            f"## Interaction Paradigm — 3DoF vs 6DoF, gaze/hand/controller input\n"
            f"## Comfort Guidelines — PPD targets, frame rate floor (72/90/120Hz), "
            f"  locomotion method (teleport/smooth), FOV limits, IPD range\n"
            f"## Spatial UI — world-space vs head-locked panels, "
            f"  minimum text size at 1m, depth placement zones\n"
            f"## Scene Scale — real-world scale vs stylised, gravity direction\n"
            f"## Hand Tracking / Controller Mapping — gesture library, haptic feedback points\n"
            f"## Accessibility — seated mode, reduced motion mode, single-hand mode\n"
            f"## Platform Requirements — visionOS/ARKit/ARCore/OpenXR specific notes\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["spatial_design_spec"] = await _submode_approval(
        state, "Spatial Design Spec", spatial_raw, design_submode,
    )

    asset_raw = await call_ai(
        role=AIRole.ENGINEER,
        prompt=(
            f"Write an AR/VR Asset Manifest for '{app_name}'.\n\n"
            f"3D assets: models (format, poly budget), textures (resolution, PBR maps), "
            f"shaders, particle systems, audio spatialisation requirements.\n"
            f"Include performance budget per render pass.\n"
            f"Return Markdown tables."
        ),
        state=state,
        action="write_code",
    )
    output["ar_vr_asset_manifest"] = await _submode_approval(
        state, "AR/VR Asset Manifest", asset_raw, design_submode,
    )

    _save_design_docs(state.project_id, "ar_vr", output)
    return output


async def _generate_medical_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    design_submode: str,
) -> dict:
    """Medical: clinical workflow, safety-critical UX, accessibility."""
    app_name = blueprint_data.get("app_name", state.project_id)
    screens  = blueprint_data.get("screens", [])

    output: dict = {}

    workflow_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write a Clinical Workflow & Safety-Critical UX Spec for '{app_name}'.\n\n"
            f"Screens: {[s.get('name') for s in screens[:10]]}\n\n"
            f"## Clinical Workflow Diagrams — patient journey, provider journey, "
            f"  handoff points, emergency escalation paths\n"
            f"## Error Prevention Design — confirmation dialogs for irreversible actions, "
            f"  drug/dosage input validation, double-confirmation for critical writes\n"
            f"## Accessibility (Medical Grade) — WCAG 2.2 AA minimum, "
            f"  large touch targets (min 44×44pt), high-contrast mode, audio cues\n"
            f"## Data Entry UX — structured input (dropdowns over free text), "
            f"  autocomplete for medical codes, barcode/QR scanning\n"
            f"## Privacy & Data Handling — de-identification UX, "
            f"  session timeout warnings, biometric lock\n"
            f"## Regulatory Notes — SFDA (KSA), CE marking, FDA 510k UX considerations\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["clinical_workflow_spec"] = await _submode_approval(
        state, "Clinical Workflow Spec", workflow_raw, design_submode,
    )

    _save_design_docs(state.project_id, "medical", output)
    return output


async def _generate_educational_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    design_submode: str,
) -> dict:
    """Educational: learning taxonomy, gamification, curriculum alignment."""
    app_name = blueprint_data.get("app_name", state.project_id)
    features = requirements.get("features_must", [])

    output: dict = {}

    pedagogy_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write a Pedagogical Design & Gamification Spec for '{app_name}'.\n\n"
            f"Features: {features[:8]}\n\n"
            f"## Learning Taxonomy — Bloom's taxonomy alignment per module\n"
            f"## Content Structure — lesson → module → course hierarchy\n"
            f"## Assessment Design — quiz types, adaptive difficulty, spaced repetition\n"
            f"## Gamification Elements — XP, badges, streaks, leaderboards, "
            f"  progress bars, rewards design\n"
            f"## Engagement Loop — daily challenge, notification strategy, retention hooks\n"
            f"## Accessibility — reading level calibration, dyslexia-friendly fonts, "
            f"  audio narration, colour-blind safe palettes\n"
            f"## KSA Curriculum Alignment — MOE standards, Arabic content requirements\n"
            f"## Mascot & Character Design Brief — if applicable\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["pedagogy_design_spec"] = await _submode_approval(
        state, "Pedagogy & Gamification Spec", pedagogy_raw, design_submode,
    )

    _save_design_docs(state.project_id, "educational", output)
    return output


async def _generate_ecommerce_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    design_submode: str,
) -> dict:
    """E-commerce: catalog design, product photography spec, checkout UX."""
    app_name = blueprint_data.get("app_name", state.project_id)

    output: dict = {}

    catalog_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write an E-commerce Design Specification for '{app_name}'.\n\n"
            f"## Product Catalog Design — grid vs list toggle, card layout spec, "
            f"  filter/sort UI, infinite scroll vs pagination\n"
            f"## Product Photography Spec — image count per SKU, aspect ratio, "
            f"  background style, 360-view requirements, zoom behaviour\n"
            f"## Checkout Flow UX — step count, guest checkout, address validation, "
            f"  KSA payment methods (MADA, Apple Pay, STC Pay, Tamara), "
            f"  order confirmation design\n"
            f"## Search & Discovery — autocomplete design, zero-results page, "
            f"  recommendation widget, recently viewed\n"
            f"## Trust Signals — review display, seller rating, return policy badges, "
            f"  secure payment icons\n"
            f"## Arabic RTL E-commerce — RTL cart, right-to-left checkout flow\n"
            f"## Empty States — empty cart, no search results, wishlist empty\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["ecommerce_design_spec"] = await _submode_approval(
        state, "E-commerce Design Spec", catalog_raw, design_submode,
    )

    _save_design_docs(state.project_id, "ecommerce", output)
    return output


async def _generate_dashboard_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    design_submode: str,
) -> dict:
    """Dashboard/BI: chart type guide, density modes, color-blind accessibility."""
    app_name = blueprint_data.get("app_name", state.project_id)

    output: dict = {}

    viz_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write a Data Visualisation Design Specification for '{app_name}'.\n\n"
            f"## Chart Type Selection Guide — when to use bar/line/pie/scatter/heatmap/funnel\n"
            f"## Color System for Data — categorical palette (8 colors), "
            f"  sequential palette, diverging palette, all colorblind-safe\n"
            f"## Density Modes — compact / comfortable / spacious toggle\n"
            f"## Real-time Data UX — update animation, loading skeleton, "
            f"  stale data indicator, refresh controls\n"
            f"## Responsive Layout — mobile dashboard vs desktop (widget reflow)\n"
            f"## Drill-down & Filters — filter panel design, date range picker, "
            f"  breadcrumb navigation for drill-down\n"
            f"## Export & Share — chart export (PNG/SVG/PDF), table CSV, shareable links\n"
            f"## Arabic Dashboard — RTL table headers, right-aligned numbers, "
            f"  Hijri date axis option\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["data_viz_design_spec"] = await _submode_approval(
        state, "Data Viz Design Spec", viz_raw, design_submode,
    )

    _save_design_docs(state.project_id, "dashboard", output)
    return output


async def _generate_creative_tool_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    vibe: dict,
    design_submode: str,
) -> dict:
    """Creative Tool: canvas spec, tool palette, dark mode, performance."""
    app_name = blueprint_data.get("app_name", state.project_id)
    description = requirements.get("app_description", "")

    output: dict = {}

    canvas_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Write a Creative Tool Design Specification for '{app_name}'.\n\n"
            f"Tool type: {description}\n\n"
            f"## Canvas Architecture — infinite canvas, fixed canvas, zoom limits, "
            f"  pan behaviour, grid/ruler/guide system\n"
            f"## Tool Palette Design — tool grouping, keyboard shortcuts, "
            f"  context toolbar (shows options for active tool)\n"
            f"## Dark Mode — dark canvas with neutral mid-grey chrome "
            f"  (industry standard: #1E1E1E, #2D2D2D, #3C3C3C)\n"
            f"## Performance UX — progress indicators for renders, "
            f"  background save indicator, undo history limit display\n"
            f"## Layer / Object Panel — hierarchy view, visibility, lock, blend modes\n"
            f"## Asset Library — brush library, symbol library, recent colours\n"
            f"## Export Workflow — format selection, quality settings, "
            f"  batch export, share sheet\n"
            f"## Accessibility — keyboard-only operation, screen reader support "
            f"  for tool state announcement\n"
            f"Return professional Markdown."
        ),
        state=state,
        action="plan_architecture",
    )
    output["creative_tool_design_spec"] = await _submode_approval(
        state, "Creative Tool Design Spec", canvas_raw, design_submode,
    )

    _save_design_docs(state.project_id, "creative_tool", output)
    return output


# ═══════════════════════════════════════════════════════════════════
# Screen Mockups (all project types)
# ═══════════════════════════════════════════════════════════════════


async def _generate_screen_mockups(
    state: PipelineState,
    screens: list,
    blueprint_data: dict,
    vibe: dict,
    project_type: ProjectDesignType,
) -> list[str]:
    """Generate ASCII/Markdown wireframe mockups for each screen.

    Returns list of file paths written to project dir.
    """
    if not screens:
        logger.info(f"[{state.project_id}] No screens to mockup")
        return []

    mockup_dir = Path(f"/tmp/factory_projects/{state.project_id}/mockups")
    mockup_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    # Batch mockup generation (max 12 screens to control cost)
    for screen in screens[:12]:
        screen_name = screen.get("name", "Screen")
        purpose     = screen.get("purpose", "")
        components  = screen.get("components", [])
        bindings    = screen.get("data_bindings", [])

        mockup_raw = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Draw an ASCII wireframe mockup for '{screen_name}' screen.\n\n"
                f"Purpose: {purpose}\n"
                f"Components: {components}\n"
                f"Data bindings: {[b.get('collection') for b in bindings[:5]]}\n"
                f"Visual style: {vibe.get('visual_style', 'minimal')}\n"
                f"Design system: {vibe.get('design_system', 'material3')}\n"
                f"Project type: {project_type.value}\n\n"
                f"Use ASCII art to show the layout. Include:\n"
                f"  - Header/navigation bar\n"
                f"  - Main content area with realistic placeholder content\n"
                f"  - Key interactive elements (buttons, inputs, cards)\n"
                f"  - Bottom navigation/tab bar (if applicable)\n"
                f"  - Use [  ] for buttons, [____] for text inputs, "
                f"  [img] for images, ░░░ for loading/skeleton\n\n"
                f"After the wireframe, add a brief annotation (2-3 bullets) "
                f"about key UX decisions."
            ),
            state=state,
            action="write_code",
        )

        # Save mockup file
        filename = screen_name.lower().replace(" ", "_").replace("/", "_")
        mockup_path = mockup_dir / f"{filename}.md"
        try:
            header = (
                f"# Screen Mockup: {screen_name}\n"
                f"<!-- App: {blueprint_data.get('app_name', 'App')} | "
                f"Project: {state.project_id} -->\n\n"
            )
            mockup_path.write_text(header + mockup_raw, encoding="utf-8")
            paths.append(str(mockup_path))
        except Exception as e:
            logger.warning(f"[{state.project_id}] Mockup write failed for {screen_name}: {e}")

    logger.info(f"[{state.project_id}] Generated {len(paths)} screen mockups")
    return paths


# ═══════════════════════════════════════════════════════════════════
# Platform Asset Specs
# ═══════════════════════════════════════════════════════════════════

# Required icon sizes per platform
_ICON_SIZES: dict[str, list[int]] = {
    "ios":         [20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 1024],
    "android":     [36, 48, 72, 96, 144, 192, 512],
    "web":         [16, 32, 48, 64, 128, 192, 256, 512],
    "macos":       [16, 32, 64, 128, 256, 512, 1024],
    "windows":     [16, 32, 48, 64, 128, 256],
    "tvos":        [400, 1280],
    "watchos":     [48, 55, 58, 80, 87, 88, 172, 196, 216],
    "android_tv":  [320, 512],
}

# Store screenshot specs per platform
_SCREENSHOT_SPECS: dict[str, dict] = {
    "ios": {
        "sizes": ["6.7\" (1290×2796)", "6.5\" (1242×2688)", "5.5\" (1242×2208)", "iPad Pro (2048×2732)"],
        "count": "10 max per size",
    },
    "android": {
        "sizes": ["1080×1920 (phone)", "1200×1920 (tablet)"],
        "count": "8 max",
    },
    "web": {
        "sizes": ["1280×800 (desktop)", "768×1024 (tablet)", "390×844 (mobile)"],
        "count": "5 recommended",
    },
}


async def _generate_platform_assets(
    state: PipelineState,
    requirements: dict,
    blueprint_data: dict,
    app_name: str,
    project_type: ProjectDesignType,
) -> dict:
    """Generate platform-specific asset specifications.

    Returns a spec dict covering icon sets, splash screens, store screenshots.
    """
    target_platforms = requirements.get("target_platforms", ["ios", "android"])

    platform_spec: dict = {}

    for platform in target_platforms:
        icon_sizes = _ICON_SIZES.get(platform, [])
        screenshot_spec = _SCREENSHOT_SPECS.get(platform, {})

        platform_spec[platform] = {
            "app_icon_sizes": [f"{s}×{s}px" for s in icon_sizes],
            "splash_screen": _splash_spec(platform),
            "store_screenshots": screenshot_spec,
        }

    # Game-specific: add platform feature art sizes
    if project_type in (
        ProjectDesignType.MOBILE_GAME,
        ProjectDesignType.PC_GAME,
        ProjectDesignType.CONSOLE_GAME,
    ):
        platform_spec["_game_store_art"] = {
            "feature_graphic": "1024×500px (Google Play)",
            "app_preview_video": "15–30 seconds, 1080p",
            "steam_capsule": "460×215px (main), 231×87px (small)",
            "console_box_art": "2000×2000px (cover), banner variants",
        }

    logger.info(
        f"[{state.project_id}] Platform asset specs: {list(platform_spec.keys())}"
    )
    return platform_spec


def _splash_spec(platform: str) -> dict:
    specs = {
        "ios":        {"size": "1290×2796px (6.7\")", "format": "PNG", "notes": "No text — use LaunchScreen.storyboard"},
        "android":    {"size": "1080×1920px", "format": "PNG/9-patch", "notes": "Use Android 12 Splash Screen API"},
        "web":        {"size": "1920×1080px", "format": "SVG/PNG", "notes": "Preloader overlay, 500ms max display"},
        "macos":      {"size": "512×512px icon", "format": "PNG", "notes": "No separate splash on macOS"},
        "windows":    {"size": "620×300px", "format": "PNG", "notes": "UWP splash screen"},
        "tvos":       {"size": "1920×1080px", "format": "PNG", "notes": "Top shelf image required"},
        "android_tv": {"size": "1280×720px", "format": "PNG", "notes": "Banner image for launcher"},
        "watchos":    {"size": "No splash on watchOS", "format": "N/A", "notes": ""},
    }
    return specs.get(platform, {"size": "1080×1920px", "format": "PNG", "notes": ""})


# ═══════════════════════════════════════════════════════════════════
# Mother Memory — Design Nodes
# ═══════════════════════════════════════════════════════════════════


async def _write_design_to_mother_memory(
    state: PipelineState,
    project_type: ProjectDesignType,
    design_output: dict,
) -> None:
    """Write design decisions to Mother Memory.

    Stores 3 nodes: design_type, design_system, specialist_assets.
    """
    try:
        from factory.memory.mother_memory import store_pipeline_decision

        vibe = design_output.get("vibe", {})
        palette = vibe.get("color_palette", {})

        await store_pipeline_decision(
            project_id=state.project_id,
            stage="s3_design",
            decision_type="design_type",
            content=(
                f"Project type: {project_type.value} | "
                f"Sub-mode: {design_output.get('design_submode', 'autopilot')} | "
                f"Visual style: {vibe.get('visual_style', 'minimal')} | "
                f"Design system: {vibe.get('design_system', 'material3')}"
            ),
            operator_id=str(state.operator_id),
        )

        await store_pipeline_decision(
            project_id=state.project_id,
            stage="s3_design",
            decision_type="design_system",
            content=(
                f"Primary: {palette.get('primary', '#1976D2')} | "
                f"Secondary: {palette.get('secondary', '#FF9800')} | "
                f"Font: {vibe.get('typography', {}).get('heading_font', 'Inter')} | "
                f"Layout: {vibe.get('layout_patterns', [])} | "
                f"Mockups: {len(design_output.get('mockup_paths', []))} screens"
            ),
            operator_id=str(state.operator_id),
        )

        specialist = design_output.get("specialist", {})
        if specialist:
            doc_keys = list(specialist.keys())
            await store_pipeline_decision(
                project_id=state.project_id,
                stage="s3_design",
                decision_type="specialist_assets",
                content=(
                    f"Type: {project_type.value} | "
                    f"Docs generated: {doc_keys}"
                ),
                operator_id=str(state.operator_id),
            )

        logger.info(
            f"[{state.project_id}] S3 → Mother Memory: design nodes stored"
        )
    except Exception as e:
        logger.warning(
            f"[{state.project_id}] S3 Mother Memory write failed (non-fatal): {e}"
        )


# ═══════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════


def _save_design_docs(project_id: str, category: str, docs: dict) -> None:
    """Save generated design documents to project dir."""
    design_dir = Path(f"/tmp/factory_projects/{project_id}/design/{category}")
    design_dir.mkdir(parents=True, exist_ok=True)
    for key, content in docs.items():
        try:
            (design_dir / f"{key}.md").write_text(str(content), encoding="utf-8")
        except Exception as e:
            logger.warning(
                f"[{project_id}] Could not save design doc {key}: {e}"
            )


# Register with DAG
register_stage_node("s3_design", s3_design_node)
