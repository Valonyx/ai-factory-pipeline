"""
AI Factory Pipeline v5.8 — S3 Design Node

Implements:
  - §4.3 S3 Design (new stage, split from S2 in v5.8)
  - 3 sub-modes: Autopilot / One-by-One / User Control
  - Free image-gen and UI/UX providers via Mode Router
  - Scout research: target customer aesthetics, competitor design, 2026 trends
  - Design system: colors, typography, spacing, component library
  - Screen mockups for every screen in S2 blueprint
  - Platform-specific assets: app icons, splash screens, onboarding illustrations
  - Mother Memory: (:Project)-[:HAS_DESIGN]->(:DesignSystem)
  - User preference learning: (:User)-[:PREFERS]->(:DesignTrait)

Spec Authority: v5.8 §4.3 (Phase 5)

NOTE: Full real implementation is Phase 5 of v5.8 rewire.
      This stub routes through to S4 CodeGen while Phase 5 is built.
      It captures design sub-mode selection and passes design context forward.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from factory.core.state import (
    AIRole,
    PipelineState,
    Stage,
)
from factory.core.roles import call_ai
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s3_design")


# ═══════════════════════════════════════════════════════════════════
# Design Sub-Mode
# ═══════════════════════════════════════════════════════════════════

DESIGN_SUBMODE_AUTOPILOT   = "autopilot"
DESIGN_SUBMODE_ONE_BY_ONE  = "one_by_one"
DESIGN_SUBMODE_USER_CONTROL = "user_control"


@pipeline_node(Stage.S3_DESIGN)
async def s3_design_node(state: PipelineState) -> PipelineState:
    """S3: Design — generate UI/UX design system and screen assets.

    Spec: §4.3 (v5.8 Phase 5)
    Sub-modes:
      A. Autopilot — generate all, operator approves at end
      B. One-by-One — generate each element, operator approves each
      C. User Control — operator specifies each element

    Phase 5 full implementation: design system, component library,
    screen mockups, platform assets, Mother Memory persistence.

    This stub captures sub-mode and produces a minimal design context
    so the pipeline can proceed to S4 CodeGen. Full real implementation
    arrives in Phase 5 of the v5.8 rewire.
    """
    blueprint_data = state.s2_output or {}
    app_name = blueprint_data.get("app_name") or state.idea_name or "App"

    logger.info(f"[{state.project_id}] S3 Design starting for '{app_name}'")

    # Use existing design system from S2 if available (backwards compat)
    existing_design = blueprint_data.get("design_system") or {}
    color_palette   = blueprint_data.get("color_palette") or {}
    screens         = blueprint_data.get("screens") or []

    # ── Determine design sub-mode ──
    design_submode = state.project_metadata.get("design_submode", DESIGN_SUBMODE_AUTOPILOT)

    # ── Generate minimal design context via Strategist ──
    # (Phase 5 will replace this with full research + multi-round generation)
    design_prompt = (
        f"Generate a concise design system specification for '{app_name}'.\n"
        f"Return JSON with:\n"
        f"  color_palette: {{primary, secondary, background, surface, error, on_primary, on_secondary}}\n"
        f"  typography: {{heading_font, body_font, scale_factor}}\n"
        f"  spacing: {{base_unit, border_radius}}\n"
        f"  design_language: (e.g. 'Material 3', 'Cupertino', 'Custom')\n"
        f"  key_screens: list of screen names from blueprint\n\n"
        f"Existing blueprint screens: {[s.get('name', '') for s in screens[:10]]}\n"
        f"Existing color hints: {color_palette}\n"
        f"Design sub-mode: {design_submode}\n\n"
        f"Return only the JSON object."
    )

    try:
        design_result = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=design_prompt,
            state=state,
            action="design_system",
        )
        import json
        # Try to parse; fallback to existing or empty
        try:
            design_system = json.loads(design_result)
        except (json.JSONDecodeError, TypeError):
            import re
            m = re.search(r'\{.*\}', design_result, re.DOTALL)
            design_system = json.loads(m.group()) if m else existing_design
    except Exception as e:
        logger.warning(f"[{state.project_id}] Design AI call failed (non-fatal): {e}")
        design_system = existing_design

    # ── Ensure design_system is a dict (guard against AI returning a string) ──
    if not isinstance(design_system, dict):
        design_system = existing_design if isinstance(existing_design, dict) else {}

    # ── Merge with existing design data from S2 ──
    if not design_system.get("color_palette") and color_palette:
        design_system["color_palette"] = color_palette
    if not design_system.get("screens"):
        design_system["screens"] = screens

    # ── Logo path passthrough ──
    logo_path = (
        state.project_metadata.get("logo_path")
        or (state.s0_output or {}).get("logo_path")
        or blueprint_data.get("logo_path")
    )

    state.s3_output = {
        "design_system": design_system,
        "design_submode": design_submode,
        "logo_path": logo_path,
        "color_palette": design_system.get("color_palette") or color_palette,
        "screens": screens,
        "app_name": app_name,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "phase": "stub_v5.8_phase5_pending",
        # Phase 5 will add: approved_assets, design_tokens, mockup_paths,
        # icon_set_paths, splash_paths, mother_memory_node_id
    }

    logger.info(
        f"[{state.project_id}] S3 Design complete (stub): "
        f"submode={design_submode}, "
        f"design_language={design_system.get('design_language', 'unknown')}"
    )

    return state


# Register with DAG
register_stage_node("s3_design", s3_design_node)
