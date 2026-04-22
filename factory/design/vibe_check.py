"""
AI Factory Pipeline v5.8 — Vibe Check (Autonomous Design Discovery)

Implements:
  - §3.4.1 Autonomous Vibe Check
  - Scout trend research + Design DNA extraction
  - Strategist KSA refinement (RTL + WCAG + cultural)
  - Grid Enforcer final validation
  - Design DNA persistence to Mother Memory

Spec Authority: v5.8 §3.4.1
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from factory.core.state import (
    AIRole,
    AutonomyMode,
    PipelineState,
)
from factory.core.mode_router import MasterMode
from factory.core.roles import call_ai
from factory.design.grid_enforcer import grid_enforcer_validate, create_default_design

logger = logging.getLogger("factory.design.vibe_check")


# ═══════════════════════════════════════════════════════════════════
# Design DNA JSON Schema (expected from Scout)
# ═══════════════════════════════════════════════════════════════════

DESIGN_DNA_SCHEMA = (
    '{"color_palette": {"primary":"#hex","secondary":"#hex","accent":"#hex",'
    '"background":"#hex","surface":"#hex","text_primary":"#hex",'
    '"text_secondary":"#hex","error":"#hex"},'
    '"typography": {"heading_font":"...","body_font":"...","size_base":16,"scale_ratio":1.25},'
    '"spacing": {"unit":4,"page_padding":16,"card_padding":12,"element_gap":8},'
    '"layout_patterns": ["cards","bottom_nav"],'
    '"visual_style": "minimal"}'
)


# ═══════════════════════════════════════════════════════════════════
# §3.4.1 Vibe Check
# ═══════════════════════════════════════════════════════════════════


async def vibe_check(
    state: PipelineState,
    requirements: dict,
) -> dict:
    """Autonomous Vibe Check — AI-driven design discovery.

    Spec: §3.4.1

    Flow:
      1. Scout finds trending apps in same category
      2. Scout extracts Design DNA (colors, fonts, spacing)
      3. Strategist refines for KSA audience + RTL + WCAG
      4. Grid Enforcer validates

    Args:
        state: Current pipeline state.
        requirements: Dict with app_category, app_description, etc.

    Returns:
        Validated design dict (Grid Enforcer output).
    """
    category = requirements.get("app_category", "general")
    description = requirements.get("app_description", "")

    logger.info(
        f"[{state.project_id}] Vibe Check: "
        f"category={category}"
    )

    # ── Step 1+2: Scout discovers trends and extracts DNA ──
    trend_research = await _scout_trend_research(state, category, description)
    design_dna = await _scout_extract_dna(state, trend_research)

    # Parse Scout's JSON response
    design = _parse_design_json(design_dna, category)

    # ── Step 3: Strategist refines for KSA ──
    refined = await _strategist_refine(state, design, description)

    # ── Step 4: Grid Enforcer validates ──
    validated = grid_enforcer_validate(refined)

    # ── Step 5: Vision verify rendered mockups (G5 closure) ──
    # Non-blocking: degraded result stored in metadata, never halts the stage.
    await _vision_verify_mockup(state, validated, description)

    logger.info(
        f"[{state.project_id}] Vibe Check complete: "
        f"style={validated.get('visual_style', 'unknown')}, "
        f"patterns={validated.get('layout_patterns', [])}"
    )
    return validated


# ═══════════════════════════════════════════════════════════════════
# Scout Steps
# ═══════════════════════════════════════════════════════════════════


async def _scout_trend_research(
    state: PipelineState, category: str, description: str,
) -> str:
    """Scout Step 1: Find trending apps in category.

    Spec: §3.4.1 Step 1
    """
    return await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"Find top 5 trending {category} apps in KSA and globally 2026.\n"
            f"For each: primary colors (hex), typography, layout patterns, "
            f"spacing, visual style.\n"
            f"Focus on apps similar to: {description}"
        ),
        state=state,
        action="general",
    )


async def _scout_extract_dna(state: PipelineState, trend_research: str) -> str:
    """Scout Step 2: Extract unified Design DNA from trends.

    Spec: §3.4.1 Step 2
    """
    return await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"From these trends:\n{trend_research[:5000]}\n\n"
            f"Extract unified Design DNA as JSON:\n{DESIGN_DNA_SCHEMA}"
        ),
        state=state,
        action="general",
    )


def _parse_design_json(raw: str, fallback_category: str = "general") -> dict:
    """Parse Design DNA JSON from Scout response.

    Falls back to category defaults if parsing fails.
    """
    # Try to extract JSON from response
    try:
        # Handle responses that contain JSON within text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback to defaults
    logger.warning(
        f"Vibe Check: Failed to parse Scout DNA, "
        f"using {fallback_category} defaults"
    )
    return create_default_design(fallback_category)


# ═══════════════════════════════════════════════════════════════════
# Strategist Refinement
# ═══════════════════════════════════════════════════════════════════


async def _strategist_refine(
    state: PipelineState, design: dict, description: str,
) -> dict:
    """Strategist Step 3: Refine design for KSA audience.

    Spec: §3.4.1 Step 3
    Ensures: RTL support, WCAG AA, 4px grid, KSA preferences.
    """
    refined_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=(
            f"Refine for KSA audience:\n{json.dumps(design, indent=2)}\n\n"
            f"App: {description}\n"
            f"Ensure: RTL support, WCAG AA contrast (4.5:1), 4px grid, "
            f"KSA cultural preferences.\nReturn refined JSON only."
        ),
        state=state,
        action="plan_architecture",
    )

    try:
        start = refined_raw.find("{")
        end = refined_raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(refined_raw[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategist parse failed — use unrefined (Grid Enforcer will fix)
    logger.warning("Vibe Check: Strategist parse failed, using Scout DNA")
    return design


# ═══════════════════════════════════════════════════════════════════
# Quick Vibe Check (Autopilot fast-track)
# ═══════════════════════════════════════════════════════════════════


async def quick_vibe_check(
    state: PipelineState,
    requirements: dict,
) -> dict:
    """Fast Vibe Check for Autopilot — Scout only, no Strategist.

    Skips the Strategist refinement step to save cost (~$0.30).
    Grid Enforcer still validates the output.
    """
    category = requirements.get("app_category", "general")
    description = requirements.get("app_description", "")

    trend_research = await _scout_trend_research(state, category, description)
    design_dna = await _scout_extract_dna(state, trend_research)
    design = _parse_design_json(design_dna, category)

    return grid_enforcer_validate(design)


# ═══════════════════════════════════════════════════════════════════
# §G5 — Vision Mockup Verification (v5.8.16)
# ═══════════════════════════════════════════════════════════════════

_MAX_SCREENSHOTS = 3  # cap to bound cost


async def _vision_verify_mockup(
    state: PipelineState,
    design: dict,
    description: str,
) -> None:
    """G5: Verify rendered mockup PNGs match the Design DNA via Claude Vision.

    Reads up to _MAX_SCREENSHOTS PNGs from
    artifacts/<project_id>/design/screenshots/ and asks Claude Vision
    whether each screen is consistent with the validated design.

    Result is stored in state.project_metadata["vision_analysis"]:
      - skipped:  True when BASIC mode or no screenshots present
      - degraded: True when key is missing (non-fatal)
      - analyses: list of per-screenshot analysis dicts on success

    This step is non-blocking: failure or absence of screenshots never
    prevents vibe_check from returning the validated design dict.

    Cost: claude-haiku-4-5-20251001 at ~$0.001–0.003/screenshot.
    """
    result_key = "vision_analysis"

    # ── Gate: BASIC mode → free-only, skip paid vision ──
    master_mode = getattr(state, "master_mode", MasterMode.BALANCED)
    if master_mode == MasterMode.BASIC:
        logger.info(f"[{state.project_id}] G5 vision: skipped (BASIC mode)")
        state.project_metadata[result_key] = {
            "skipped": True,
            "reason": "basic_mode",
        }
        return

    # ── Gate: locate screenshot directory ──
    screenshots_dir = Path("artifacts") / state.project_id / "design" / "screenshots"
    pngs = sorted(screenshots_dir.glob("*.png"))[:_MAX_SCREENSHOTS]
    if not pngs:
        logger.info(f"[{state.project_id}] G5 vision: skipped (no screenshots in {screenshots_dir})")
        state.project_metadata[result_key] = {
            "skipped": True,
            "reason": "no_screenshots",
        }
        return

    # ── Gate: API key ──
    from factory.integrations.claude_vision import call_claude_vision, is_available
    if not is_available():
        logger.warning(f"[{state.project_id}] G5 vision: ANTHROPIC_API_KEY missing — degraded")
        state.project_metadata[result_key] = {
            "degraded": True,
            "reason": "api_key_missing",
        }
        return

    # ── Analyse each screenshot ──
    dna_summary = json.dumps({
        "primary": design.get("color_palette", {}).get("primary", ""),
        "style":   design.get("visual_style", ""),
        "layout":  design.get("layout_patterns", []),
    })
    prompt_template = (
        "Design DNA: {dna}\n\n"
        "App description: {desc}\n\n"
        "Look at this UI mockup screenshot. Does it match the Design DNA? "
        "Reply with JSON: "
        '{{"match": true|false, "issues": ["..."], "score": 0-10, "summary": "..."}}'
    )

    analyses = []
    total_cost = 0.0
    for png_path in pngs:
        try:
            image_bytes = png_path.read_bytes()
            prompt = prompt_template.format(dna=dna_summary, desc=description[:300])
            text, cost = await call_claude_vision(image_bytes, prompt)
            total_cost += cost
            analyses.append({
                "screenshot": png_path.name,
                "analysis": text,
                "cost_usd": round(cost, 6),
                "source": "claude_vision",
            })
            logger.info(
                f"[{state.project_id}] G5 vision: {png_path.name} analysed "
                f"(${cost:.5f})"
            )
        except Exception as e:
            logger.warning(f"[{state.project_id}] G5 vision: {png_path.name} failed: {e}")
            analyses.append({
                "screenshot": png_path.name,
                "error": str(e),
                "source": "degraded",
            })

    # Track cost through QuotaTracker so /cost reports real spend
    if total_cost > 0:
        try:
            from factory.core.quota_tracker import get_quota_tracker
            qt = get_quota_tracker()
            await qt.record_usage(
                "claude_vision",
                tokens=0,
                calls=len(pngs),
                cost_usd=total_cost,
            )
        except Exception:
            pass  # quota tracking is advisory

    state.project_metadata[result_key] = {
        "analyses": analyses,
        "screenshots_checked": len(pngs),
        "total_cost_usd": round(total_cost, 6),
        "source": "claude_vision",
    }
    logger.info(
        f"[{state.project_id}] G5 vision complete: "
        f"{len(analyses)} screenshots, ${total_cost:.5f}"
    )