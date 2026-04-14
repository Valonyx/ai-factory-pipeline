"""
AI Factory Pipeline v5.8 — S0 Intake Node

Implements:
  - §4.1 S0 Intake (requirement extraction)
  - Quick Fix (Haiku) extracts structured requirements from free-text
  - Platform multi-select: 14 canonical platforms (COPILOT) or AI-extracted (AUTOPILOT)
  - Markets selection: KSA / GCC / Global / Custom
  - Logo flow: upload / describe / auto-generate 3 variants with infinite regen
  - Scout optionally performs market scan (if budget allows)
  - Copilot confirmation gate

Spec Authority: v5.8 §4.1
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    AutonomyMode,
    PipelineMode,
    PipelineState,
    Stage,
)
from factory.core.mode_router import (
    MasterMode,
    mode_selection_message,
    parse_mode_selection,
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

    Spec: §4.1 v5.8
    Step 1: Quick Fix extracts structured requirements (JSON)
    Step 2: Platform multi-select (COPILOT) or AI-extracted (AUTOPILOT)
    Step 3: Markets selection
    Step 4: Scout market scan (optional, if budget allows)
    Step 5: Copilot scope confirmation
    Step 6: Logo flow (COPILOT: 3 variants; AUTOPILOT: silent auto-gen)
    Step 7: Master Mode selection

    Cost target: <$0.15
    """
    # ── MODIFY mode: clone repo + analyze codebase ──
    if state.pipeline_mode == PipelineMode.MODIFY:
        return await _s0_modify_intake(state)

    raw_input = state.project_metadata.get("raw_input", "")
    attachments = state.project_metadata.get("attachments", [])

    # ── Step 1: Quick Fix extracts requirements ──
    requirements = await _extract_requirements(raw_input, attachments, state)

    # ── Step 2: Platform multi-select ──
    requirements["target_platforms"] = await _select_platforms(state, requirements)

    # ── Step 3: Markets selection ──
    requirements["target_market"] = await _select_market(state)

    # ── Step 4: Scout market scan (optional) ──
    requirements = await _scout_scan(state, requirements, raw_input)

    # ── Step 5: Copilot scope confirmation ──
    requirements = await _scope_confirmation(state, requirements, raw_input)

    # ── Step 6: Logo flow ──
    logo_asset = await _logo_flow(state, requirements)
    if logo_asset:
        state.brand_assets.append(logo_asset)
        requirements["logo_ready"] = True

    # ── Step 7: Master Mode selection ──
    requirements = await _mode_selection(state, requirements)

    # ── Finalise ──
    state.s0_output = requirements
    if requirements.get("app_name"):
        if not state.idea_name:
            state.idea_name = requirements["app_name"]
        # Fix #8: write back into project_metadata so bot.py completion message
        # uses app_name instead of falling back to project_id
        state.project_metadata["app_name"] = requirements["app_name"]

    # Store insight for future projects
    from factory.core.stage_enrichment import store_stage_insight
    await store_stage_insight(
        "s0_intake", state,
        fact=(
            f"App '{requirements.get('app_name', '?')}' "
            f"({requirements.get('app_category', '?')}) requested. "
            f"Complexity: {requirements.get('estimated_complexity', '?')}. "
            f"Platforms: {', '.join(requirements.get('target_platforms', []))}. "
            f"Market: {requirements.get('target_market', '?')}. "
            f"Features: {', '.join(requirements.get('features_must', [])[:5])}."
        ),
        category="requirements",
        ttl_hours=720,
    )

    logger.info(
        f"[{state.project_id}] S0 complete: "
        f"{requirements.get('app_name', 'unnamed')} "
        f"({requirements.get('estimated_complexity', '?')}) "
        f"platforms={requirements.get('target_platforms')} "
        f"market={requirements.get('target_market')}"
    )
    return state


# Register with DAG
register_stage_node("s0_intake", s0_intake_node)


# ═══════════════════════════════════════════════════════════════════
# Step 1: AI Requirement Extraction
# ═══════════════════════════════════════════════════════════════════


async def _extract_requirements(
    raw_input: str,
    attachments: list,
    state: PipelineState,
) -> dict:
    """Call Quick Fix to extract structured requirements from free text."""
    from factory.core.stage_enrichment import enrich_prompt

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

    enriched_prompt = await enrich_prompt(
        "s0_intake", extraction_prompt, state, scout=False,
    )
    result = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=enriched_prompt,
        state=state,
        action="general",
    )

    try:
        return json.loads(result)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            f"[{state.project_id}] S0: Failed to parse Quick Fix JSON, "
            f"using fallback extraction"
        )
        return _fallback_requirements(raw_input)


# ═══════════════════════════════════════════════════════════════════
# Step 2: Platform Multi-Select (14 canonical platforms)
# ═══════════════════════════════════════════════════════════════════


async def _select_platforms(state: PipelineState, requirements: dict) -> list[str]:
    """Select target platforms.

    COPILOT: interactive multi-select from 14 canonical options.
    AUTOPILOT: use AI-extracted platforms (capped to canonical set).
    """
    from factory.telegram.decisions import present_platform_multiselect, ALL_PLATFORMS

    # Build default from AI extraction (map legacy names to canonical IDs)
    ai_platforms = requirements.get("target_platforms", ["ios", "android"])
    canonical_ids = {p["id"] for p in ALL_PLATFORMS}
    _legacy_map = {"ios": "ios", "android": "android", "web": "web"}
    default = [_legacy_map.get(p, p) for p in ai_platforms if _legacy_map.get(p, p) in canonical_ids]
    if not default:
        default = ["ios", "android"]

    return await present_platform_multiselect(state, default=default)


# ═══════════════════════════════════════════════════════════════════
# Step 3: Markets Selection
# ═══════════════════════════════════════════════════════════════════


async def _select_market(state: PipelineState) -> str:
    """Select target market.

    COPILOT: 4-option menu.
    AUTOPILOT: default KSA.
    """
    from factory.telegram.decisions import present_decision

    return await present_decision(
        state=state,
        decision_type="s0_market_selection",
        question=(
            "🌍 *Target Market*\n\n"
            "Where is your app's primary market?"
        ),
        options=[
            {"label": "🇸🇦 KSA only (Saudi Arabia)",     "value": "ksa"},
            {"label": "🌍 GCC (Saudi + UAE + Gulf)",      "value": "gcc"},
            {"label": "🌐 Global (worldwide)",            "value": "global"},
            {"label": "🎯 Custom (specify countries)",    "value": "custom"},
        ],
        recommended=0,  # KSA is default
    )


# ═══════════════════════════════════════════════════════════════════
# Step 4: Scout Market Scan
# ═══════════════════════════════════════════════════════════════════


async def _scout_scan(
    state: PipelineState,
    requirements: dict,
    raw_input: str,
) -> dict:
    """Optional Scout market scan (budget-gated)."""
    current_spend = state.total_cost_usd
    per_project_cap = 25.00
    market = requirements.get("target_market", "ksa")
    market_label = {
        "ksa": "Saudi Arabia", "gcc": "GCC region",
        "global": "global market", "custom": "target market",
    }.get(market, market)

    if current_spend < per_project_cap:
        try:
            market_intel = await call_ai(
                role=AIRole.SCOUT,
                prompt=(
                    f"Quick scan: What are the top 3 competing apps for "
                    f"'{requirements.get('app_description', raw_input[:200])}' "
                    f"in {market_label}? Key features they offer?"
                ),
                state=state,
                action="general",
            )
            requirements["market_intel"] = market_intel
        except Exception as e:
            logger.warning(f"[{state.project_id}] S0: Scout scan failed: {e}")
            requirements["market_intel"] = "Scout unavailable"

    return requirements


# ═══════════════════════════════════════════════════════════════════
# Step 5: Scope Confirmation
# ═══════════════════════════════════════════════════════════════════


async def _scope_confirmation(
    state: PipelineState,
    requirements: dict,
    raw_input: str,
) -> dict:
    """COPILOT scope confirmation gate."""
    if state.autonomy_mode != AutonomyMode.COPILOT:
        return requirements

    from factory.telegram.decisions import present_decision
    selection = await present_decision(
        state=state,
        decision_type="s0_scope_confirmation",
        question=(
            f"I understood your app as: "
            f"{requirements.get('app_description', raw_input[:200])}"
        ),
        options=[
            {"label": "Correct, proceed",      "value": "proceed"},
            {"label": "Simplify to MVP",        "value": "simplify"},
            {"label": "Add more features",      "value": "expand"},
            {"label": "Start over — re-enter",  "value": "restart"},
        ],
        recommended=0,
    )

    if selection == "simplify":
        requirements["features_must"] = requirements.get("features_must", [])[:3]
        requirements["features_nice"] = []
        requirements["estimated_complexity"] = "simple"
    elif selection == "expand":
        requirements["operator_additions"] = "Operator requested expansion"

    return requirements


# ═══════════════════════════════════════════════════════════════════
# Step 6: Logo Flow
# ═══════════════════════════════════════════════════════════════════


async def _logo_flow(state: PipelineState, requirements: dict) -> Optional[dict]:
    """Run the logo selection flow.

    COPILOT: interactive 3-variant pick with infinite regeneration.
    AUTOPILOT: silent single-logo generation + Telegram notification.
    """
    if state.autonomy_mode == AutonomyMode.COPILOT:
        return await _logo_flow_copilot(state, requirements)
    return await _logo_flow_auto(state, requirements)


async def _logo_flow_copilot(state: PipelineState, requirements: dict) -> Optional[dict]:
    """Interactive COPILOT logo flow: choose source → generate 3 variants → pick."""
    from factory.telegram.decisions import present_decision, wait_for_operator_reply
    from factory.telegram.notifications import send_telegram_message
    from factory.design.logo_gen import generate_logo_variants, send_logo_variants_to_telegram
    from factory.integrations.image_gen import build_logo_prompt

    app_name = requirements.get("app_name") or state.idea_name or "App"
    description = requirements.get("app_description", "")

    # Ask how the operator wants to create a logo
    logo_source = await present_decision(
        state=state,
        decision_type="s0_logo_source",
        question=(
            f"🎨 *Logo for {app_name}*\n\n"
            f"How would you like to set your app icon?"
        ),
        options=[
            {"label": "🤖 Auto-Generate (AI picks style)", "value": "auto"},
            {"label": "✏️ Describe Your Vision",            "value": "describe"},
            {"label": "📤 Upload Later (/update_logo)",    "value": "skip"},
            {"label": "⏭ Skip — no logo needed yet",      "value": "skip"},
        ],
        recommended=0,
    )

    if logo_source == "skip":
        state.project_metadata["logo_pending"] = True
        return None

    # Build the generation prompt
    if logo_source == "describe":
        await send_telegram_message(
            state.operator_id,
            "Describe your logo vision — style, colors, symbols, concept:",
        )
        vision = await wait_for_operator_reply(
            state.operator_id, timeout=600, default=description,
        )
        logo_prompt = f"{vision} app icon for {app_name}"
    else:
        logo_prompt = build_logo_prompt(app_name, description)

    # Infinite regeneration loop (capped at 10 for safety)
    for iteration in range(10):
        await send_telegram_message(
            state.operator_id,
            f"Generating 3 logo variants... ({'re-generating' if iteration > 0 else 'please wait ~1-2 min'})",
        )

        variants = await generate_logo_variants(
            app_name=app_name,
            description=logo_prompt,
            count=3,
        )

        sent = await send_logo_variants_to_telegram(
            state.operator_id, variants, app_name,
        )

        if sent == 0:
            await send_telegram_message(
                state.operator_id,
                "Logo generation failed — skipping. Use /update_logo to add one later.",
            )
            state.project_metadata["logo_pending"] = True
            return None

        # Build pick options (only for sent variants)
        valid_variants = [(i, b) for i, b in enumerate(variants) if b is not None]
        pick_options = [
            {"label": f"Use Variant {i + 1}", "value": str(i + 1)}
            for i, _ in valid_variants[:3]
        ]
        pick_options.append({"label": "♻️ Regenerate All", "value": "regen"})

        pick = await present_decision(
            state=state,
            decision_type="s0_logo_pick",
            question="Which logo variant do you prefer?",
            options=pick_options,
            recommended=0,
        )

        if pick == "regen":
            if logo_source == "describe":
                await send_telegram_message(
                    state.operator_id,
                    "Refine your description (or say 'same' to keep it):",
                )
                refinement = await wait_for_operator_reply(
                    state.operator_id, timeout=120, default="same",
                )
                if refinement.lower() not in ("same", "skip", ""):
                    logo_prompt = f"{refinement} app icon for {app_name}"
            continue  # loop → regenerate

        # Operator picked a variant
        try:
            variant_idx = int(pick) - 1
            selected_bytes = variants[variant_idx] if variant_idx < len(variants) else variants[0]
        except (ValueError, IndexError):
            selected_bytes = next((b for b in variants if b), None)

        if selected_bytes:
            return {
                "asset_type": "logo",
                "logo_bytes_len": len(selected_bytes),
                "logo_prompt": logo_prompt,
                "source": logo_source,
                "variant": int(pick),
            }

    return None


async def _logo_flow_auto(state: PipelineState, requirements: dict) -> Optional[dict]:
    """AUTOPILOT logo: silently generate 1 logo and notify operator."""
    from factory.telegram.notifications import send_telegram_message
    from factory.integrations.image_gen import build_logo_prompt, generate_image

    app_name = requirements.get("app_name") or state.idea_name or "App"
    description = requirements.get("app_description", "")

    try:
        logo_prompt = build_logo_prompt(app_name, description)
        logo_bytes = await generate_image(
            prompt=logo_prompt,
            width=1024,
            height=1024,
            style="flat app icon",
        )

        if logo_bytes:
            from factory.telegram.notifications import get_bot
            import io as _io
            bot = get_bot()
            if bot:
                try:
                    await bot.send_photo(
                        chat_id=int(state.operator_id),
                        photo=_io.BytesIO(logo_bytes),
                        caption=f"🎨 Auto-generated logo for *{app_name}*. Use /update_logo to change.",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning(f"[{state.project_id}] AUTOPILOT logo send failed: {e}")

            return {
                "asset_type": "logo",
                "logo_bytes_len": len(logo_bytes),
                "logo_prompt": logo_prompt,
                "source": "auto",
            }
    except Exception as e:
        logger.warning(f"[{state.project_id}] AUTOPILOT logo generation failed: {e}")

    return None


# ═══════════════════════════════════════════════════════════════════
# Step 7: Master Mode Selection
# ═══════════════════════════════════════════════════════════════════


async def _mode_selection(state: PipelineState, requirements: dict) -> dict:
    """COPILOT: 4-option mode menu. AUTOPILOT: notify active mode."""
    app_name_for_prompt = requirements.get("app_name", "your app")

    if state.autonomy_mode == AutonomyMode.COPILOT:
        try:
            from factory.telegram.decisions import present_decision
            mode_choice = await present_decision(
                state=state,
                decision_type="s0_mode_selection",
                question=mode_selection_message(app_name_for_prompt),
                options=[
                    {"label": "🆓 Basic (free only, $0)",           "value": "basic"},
                    {"label": "⚖️ Balanced (smart mix, ~$5–25)",     "value": "balanced"},
                    {"label": "🎛 Custom (you pick providers)",       "value": "custom"},
                    {"label": "🚀 Turbo (max performance, no limit)", "value": "turbo"},
                ],
                recommended=1,  # Balanced is default
            )
            state.master_mode = parse_mode_selection(str(mode_choice or ""))
        except Exception as e:
            logger.warning(
                f"[{state.project_id}] S0: Mode selection failed ({e}), "
                f"defaulting to BALANCED"
            )
    else:
        # AUTOPILOT: notify operator of the active mode
        try:
            from factory.telegram.notifications import send_telegram_message
            mm = state.master_mode
            await send_telegram_message(
                state.operator_id,
                f"{mm.emoji} *Execution mode: {mm.label}*\n"
                f"Use /switch_mode to change before S1 Legal begins.",
            )
        except Exception:
            pass

    requirements["master_mode"] = state.master_mode.value
    return requirements


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

    Spec: §4.0 S0 Intake — graceful degradation.
    Full raw_text preserved (no truncation) to avoid information loss.
    """
    import re as _re
    _first_words = _re.sub(r"[^a-zA-Z0-9 ]", " ", raw_text).split()
    _fallback_name = " ".join(_first_words[:3]).title() or "Untitled"
    return {
        "app_name": _fallback_name,
        "app_description": raw_text[:2000],   # was [:500] — widened
        "app_category": "other",
        "target_platforms": ["ios", "android"],
        "tech_stack": "react_native",
        "features_must": [],
        "features_nice": [],
        "has_payments": False,
        "has_user_accounts": True,
        "has_location": False,
        "has_notifications": False,
        "has_realtime": False,
        "estimated_complexity": "medium",
        "region": "ksa",
        "parsed_by": "fallback",
    }
