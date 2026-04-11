"""
AI Factory Pipeline v5.6 — S0 Intake Node

Implements:
  - §4.1 S0 Intake (requirement extraction)
  - Quick Fix (Haiku) extracts structured requirements from free-text
  - Scout optionally performs market scan (if budget allows)
  - Copilot confirmation gate

Spec Authority: v5.6 §4.1
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from factory.core.state import (
    AIRole,
    AutonomyMode,
    PipelineMode,
    PipelineState,
    Stage,
)
from factory.core.roles import call_ai
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s0_intake")


# ═══════════════════════════════════════════════════════════════════
# §4.1 S0 Intake Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S0_INTAKE)
async def s0_intake_node(state: PipelineState) -> PipelineState:
    """S0: Intake — extract structured requirements from operator input.

    Spec: §4.1
    Step 1: Quick Fix extracts structured requirements (JSON)
    Step 2: Scout market scan (optional, if budget allows)
    Step 3: Copilot confirmation (if Copilot mode)

    Cost target: <$0.15
    """
    # ── MODIFY mode: clone repo + analyze codebase instead of normal intake ──
    if state.pipeline_mode == PipelineMode.MODIFY:
        return await _s0_modify_intake(state)

    raw_input = state.project_metadata.get("raw_input", "")
    attachments = state.project_metadata.get("attachments", [])

    # ── Step 1: Quick Fix extracts requirements ──
    extraction_prompt = (
        f"Extract structured requirements from this app description.\n\n"
        f"User input: {raw_input}\n"
    )
    if attachments:
        extraction_prompt += (
            f"Attachments: {len(attachments)} files provided "
            f"({', '.join(a.get('type', 'unknown') for a in attachments)})\n"
        )

    extraction_prompt += (
        f"\nReturn ONLY valid JSON:\n"
        f'{{\n'
        f'  "app_name": "short name",\n'
        f'  "app_description": "1-2 sentence summary",\n'
        f'  "app_category": "e-commerce|social|fitness|fintech|education|'
        f'delivery|marketplace|utility|game|healthcare|other",\n'
        f'  "features_must": ["list of required features"],\n'
        f'  "features_nice": ["list of nice-to-have features"],\n'
        f'  "target_platforms": ["ios", "android", "web"],\n'
        f'  "has_payments": true/false,\n'
        f'  "has_user_accounts": true/false,\n'
        f'  "has_location": true/false,\n'
        f'  "has_notifications": true/false,\n'
        f'  "has_realtime": true/false,\n'
        f'  "estimated_complexity": "simple|medium|complex"\n'
        f'}}'
    )

    result = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=extraction_prompt,
        state=state,
        action="general",
    )

    try:
        requirements = json.loads(result)
    except (json.JSONDecodeError, TypeError, Exception):
        # Fallback: create minimal requirements from raw input
        logger.warning(
            f"[{state.project_id}] S0: Failed to parse Quick Fix JSON, "
            f"using fallback extraction"
        )
        # Try to extract a short name: use the first word cluster before any colon/comma
        import re as _re
        _first_words = _re.sub(r"[^a-zA-Z0-9 ]", " ", raw_input).split()
        _fallback_name = " ".join(_first_words[:3]).title() or "Untitled"
        requirements = {
            "app_name": _fallback_name,
            "app_description": raw_input[:500],
            "app_category": "other",
            "features_must": [],
            "features_nice": [],
            "target_platforms": ["ios", "android"],
            "has_payments": False,
            "has_user_accounts": True,
            "has_location": False,
            "has_notifications": False,
            "has_realtime": False,
            "estimated_complexity": "medium",
        }

    # ── Step 2: Scout market scan (optional) ──
    # check_circuit_breaker moved to factory.monitoring.circuit_breaker (Part 9)
    # Inline budget guard (check_circuit_breaker wired in Part 9)
    current_spend = state.total_cost_usd
    per_project_cap = 25.00
    can_research = current_spend < per_project_cap
    if can_research:
        try:
            market_intel = await call_ai(
                role=AIRole.SCOUT,
                prompt=(
                    f"Quick scan: What are the top 3 competing apps for "
                    f"'{requirements.get('app_description', raw_input[:200])}' "
                    f"in Saudi Arabia? Key features they offer?"
                ),
                state=state,
                action="general",
            )
            requirements["market_intel"] = market_intel
        except Exception as e:
            logger.warning(f"[{state.project_id}] S0: Scout scan failed: {e}")
            requirements["market_intel"] = "Scout unavailable"

    # ── Step 3: Copilot confirmation ──
    if state.autonomy_mode == AutonomyMode.COPILOT:
        from factory.telegram.decisions import present_decision

        selection = await present_decision(
            state=state,
            decision_type="s0_scope_confirmation",
            question=(
                f"I understood your app as: "
                f"{requirements.get('app_description', raw_input[:200])}"
            ),
            options=[
                {"label": "Correct, proceed", "value": "proceed"},
                {"label": "Simplify to MVP", "value": "simplify"},
                {"label": "Add more features", "value": "expand"},
            ],
            recommended=0,
        )

        if selection == "simplify":
            requirements["features_must"] = requirements.get(
                "features_must", [],
            )[:3]
            requirements["features_nice"] = []
            requirements["estimated_complexity"] = "simple"
        elif selection == "expand":
            requirements["operator_additions"] = "Operator requested expansion"

    state.s0_output = requirements
    # Propagate app name so workspace directory uses it (not UUID)
    if requirements.get("app_name"):
        state.idea_name = requirements["app_name"]

    logger.info(
        f"[{state.project_id}] S0 complete: "
        f"{requirements.get('app_name', 'unnamed')} "
        f"({requirements.get('estimated_complexity', '?')})"
    )
    return state


# Register with DAG
register_stage_node("s0_intake", s0_intake_node)


# ═══════════════════════════════════════════════════════════════════
# MODIFY Mode: Repo Intake
# ═══════════════════════════════════════════════════════════════════


async def _s0_modify_intake(state: PipelineState) -> PipelineState:
    """S0 MODIFY: clone and analyze existing repo instead of building from scratch.

    Steps:
      1. Clone repo via git (shallow clone)
      2. Detect stack from manifest files
      3. Extract codebase context for Claude
      4. Store in state.codebase_context for S2/S3 consumption
    """
    repo_url = state.source_repo_url or state.project_metadata.get("repo_url", "")
    description = (
        state.modification_description
        or state.project_metadata.get("raw_input", "")
    )

    if not repo_url:
        logger.error(f"[{state.project_id}] MODIFY S0: no repo URL provided")
        state.s0_output = {
            "error": "No repo URL provided for MODIFY mode",
            "modify_mode": True,
        }
        return state

    logger.info(f"[{state.project_id}] MODIFY S0: cloning {repo_url}")

    try:
        from factory.pipeline.codebase_ingestor import CodebaseIngestor

        ingestor = CodebaseIngestor()
        analysis = await ingestor.analyze(repo_url=repo_url)

        state.codebase_context = analysis
        state.source_repo_path = str(analysis.get("repo_path", ""))
        state.project_metadata["detected_stack"] = analysis.get("stack", "unknown")

        state.s0_output = {
            "modify_mode": True,
            "repo_url": repo_url,
            "modification_description": description,
            "detected_stack": analysis.get("stack", "unknown"),
            "detected_architecture": analysis.get("architecture", "unknown"),
            "file_count": analysis.get("file_count", 0),
            "dependencies": analysis.get("dependencies", {}),
            "context_chars": len(analysis.get("context_text", "")),
            "app_name": analysis.get("app_name", "Existing App"),
            "app_description": description,
            "target_platforms": analysis.get("platforms", ["ios", "android"]),
            "estimated_complexity": "medium",
        }

        logger.info(
            f"[{state.project_id}] MODIFY S0 complete: "
            f"stack={analysis.get('stack')}, "
            f"files={analysis.get('file_count', 0)}"
        )

    except Exception as e:
        logger.error(f"[{state.project_id}] MODIFY S0 failed: {e}")
        # Fallback: proceed with description only (no repo context)
        state.s0_output = {
            "modify_mode": True,
            "repo_url": repo_url,
            "modification_description": description,
            "error": str(e),
            "app_description": description,
            "target_platforms": ["ios", "android"],
        }

    return state

def _fallback_requirements(raw_text: str) -> dict:
    """Parse requirements with a minimal fallback when AI parsing fails.

    Spec: §4.0 S0 Intake — graceful degradation
    """
    return {
        "app_name": raw_text.strip() or "Unnamed App",
        "app_description": raw_text[:500],
        "app_category": "other",
        "target_platforms": ["ios", "android"],
        "tech_stack": "react_native",
        "features_must": [],
        "features_nice": [],
        "has_payments": False,
        "has_user_accounts": True,
        "estimated_complexity": "medium",
        "region": "ksa",
        "parsed_by": "fallback",
    }
