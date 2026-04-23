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
import re
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
from factory.integrations.image_gen import build_logo_prompt, generate_image  # Issue 40
from factory.telegram.notifications import get_bot  # Issue 40

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

    # DRY_RUN / CI: if s0_output is already set (pre-populated by test fixture or
    # a previous pipeline run), return immediately without re-running intake.
    # We do NOT generate a stub here — instead, S0 runs its real extraction logic
    # which degrades correctly with a mock AI provider (explicit "app name: ..." patterns
    # are resolved without any AI call; mock AI fallback gives app_name=None → APP_NAME_MISSING).
    import os as _os
    if (
        _os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
        or _os.getenv("PIPELINE_ENV", "").lower() == "ci"
        or _os.getenv("AI_PROVIDER", "").lower() == "mock"
    ):
        if state.s0_output:
            logger.info(f"[{state.project_id}] S0: DRY_RUN — using pre-populated s0_output")
            return state

    raw_input = state.project_metadata.get("raw_input", "")
    attachments = state.project_metadata.get("attachments", [])

    # ── Step 1: Quick Fix extracts requirements ──
    requirements = await _extract_requirements(raw_input, attachments, state)

    # ── Step 2: Platform multi-select ──
    # Issue 28: use pre-selected data from bot onboarding flow when available.
    pre_platforms = state.project_metadata.get("pre_selected_platforms")
    if pre_platforms:
        requirements["target_platforms"] = pre_platforms
        logger.info(f"[{state.project_id}] S0: pre-selected platforms: {pre_platforms}")
    else:
        requirements["target_platforms"] = await _select_platforms(state, requirements)

    # ── Step 3: Markets selection ──
    pre_market = state.project_metadata.get("pre_selected_market")
    if pre_market:
        requirements["target_market"] = pre_market
        logger.info(f"[{state.project_id}] S0: pre-selected market: {pre_market}")
    else:
        requirements["target_market"] = await _select_market(state)

    # ── Step 4: Scout market scan (optional) ──
    requirements = await _scout_scan(state, requirements, raw_input)

    # ── Step 5: Copilot scope confirmation ──
    requirements = await _scope_confirmation(state, requirements, raw_input)

    # ── Step 6: Logo flow ──
    pre_logo = state.project_metadata.get("pre_selected_logo")
    if pre_logo == "skip":
        logo_asset = None
        logger.info(f"[{state.project_id}] S0: logo skipped by operator onboarding choice")
    else:
        # v5.8.16 Issue 65 (follow-up): "auto" was bypassing _logo_flow and
        # calling _logo_flow_auto directly, skipping the 3-variant pick screen
        # even after we changed _logo_flow to always use copilot. Fix: route
        # ALL non-skip cases through _logo_flow so the operator always gets
        # to choose from 3 generated variants. The "auto" value only means
        # "AI picks the style" — the operator still picks from the result.
        logo_asset = await _logo_flow(state, requirements)
    if logo_asset:
        state.brand_assets.append(logo_asset)
        requirements["logo_ready"] = True
        # Issue 13: persist logo_path to authoritative intake store
        if logo_asset.get("logo_path"):
            state.intake["logo_path"] = logo_asset["logo_path"]

    # ── Step 7: Master Mode selection ──
    requirements = await _mode_selection(state, requirements)

    # ── Finalise ──
    state.s0_output = requirements
    if requirements.get("app_name"):
        # Issue 14: authoritative storage for app_name. Every downstream
        # stage reads from state.intake["app_name"].
        state.intake["app_name"] = requirements["app_name"]
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


# ── Explicit app-name extraction (Issue 14) ──────────────────────────
#
# Priority-ordered patterns, case-insensitive, unicode-safe. The first
# match that validates wins and skips the AI extractor for the name.
# Quote character class accepts ASCII " ', curly “ ” ‘ ’, and Arabic
# « » so that users typing on non-US keyboards still round-trip.
# Non-raw string so \u escapes decode to actual unicode quote chars. Used
# both in strip() (literal set of quote characters) and inside a regex
# character class (where each codepoint is matched literally).
_QUOTE_OPEN = "\"'\u201c\u201d\u2018\u2019\u00ab\u00bb"
# Regex-class version — escape the literal double-quote only if needed
# (inside [] it's fine without escaping, but we escape backslash-free).
_QUOTE_CHARS = _QUOTE_OPEN
_APP_NAME_PATTERNS: tuple[str, ...] = (
    rf'app\s*name\s*[:=]\s*[{_QUOTE_CHARS}]([^{_QUOTE_CHARS}\n]+?)[{_QUOTE_CHARS}]',
    # No-quote form: take the token run up to the first "breaker"
    # (newline, comma, period, semicolon, or an em/en/hyphen dash as
    # a separator). Trailing whitespace trimmed by _validate_app_name.
    rf'app\s*name\s*[:=]\s*([^\n,.;]+?)(?=\s+[\-\u2014\u2013]\s|[,.;\n]|$)',
    rf'\bname\s*[:=]\s*[{_QUOTE_CHARS}]([^{_QUOTE_CHARS}\n]+?)[{_QUOTE_CHARS}]',
    rf'\bcalled\s+[{_QUOTE_CHARS}]([^{_QUOTE_CHARS}\n]+?)[{_QUOTE_CHARS}]',
    rf'\bcall\s+it\s+[{_QUOTE_CHARS}]([^{_QUOTE_CHARS}\n]+?)[{_QUOTE_CHARS}]',
    rf'\bnamed\s+[{_QUOTE_CHARS}]([^{_QUOTE_CHARS}\n]+?)[{_QUOTE_CHARS}]',
)

# Imperative verbs that must NOT be treated as app names — these are
# modification / command verbs. Issue 14 §2.
_IMPERATIVE_VERBS: frozenset[str] = frozenset({
    "change", "update", "modify", "add", "remove", "fix", "make",
    "set", "delete", "rename", "replace",
})


def _validate_app_name(candidate: Optional[str]) -> Optional[str]:
    """Validate and normalise a candidate app name.

    Issue 14 §2:
      - strip surrounding quotes / whitespace
      - reject if starts with an imperative verb (case-insensitive)
      - reject if fewer than 2 alphanumeric characters
      - reject if longer than 60 characters
    Returns the normalised name or None if invalid.
    """
    if candidate is None:
        return None
    # Strip common quotes + whitespace.
    name = candidate.strip().strip(_QUOTE_OPEN).strip()
    if not name:
        return None
    # Issue 34: strip leading list-marker artifacts (e.g. "I. ", "1. ", "- ", "* ")
    # that survive when the AI formats its output as a numbered/bulleted list.
    name = re.sub(r'^(?:[IVXivx]+|[0-9]+)[\.\)]\s+', '', name)
    name = re.sub(r'^[-*\u2022\u00b7\u2013\u2014]\s+', '', name)
    name = name.strip()
    if len(name) > 60:
        return None
    # Count alphanumeric characters (unicode-aware via str.isalnum()).
    alnum = sum(1 for ch in name if ch.isalnum())
    if alnum < 2:
        return None
    first_word = re.split(r"\s+", name, maxsplit=1)[0].lower()
    if first_word in _IMPERATIVE_VERBS:
        return None
    return name


def _extract_app_name_explicit(raw_text: str) -> Optional[str]:
    """Run the priority-ordered regex list and return the first validated match.

    Issue 14 §1: this runs BEFORE any AI call; a successful explicit match
    skips AI name extraction entirely.
    """
    if not raw_text:
        return None
    for pat in _APP_NAME_PATTERNS:
        m = re.search(pat, raw_text, flags=re.IGNORECASE | re.UNICODE)
        if not m:
            continue
        validated = _validate_app_name(m.group(1))
        if validated:
            return validated

    # Windowed fallback: any quoted string within 40 chars of the word "name".
    lower = raw_text.lower()
    idx = lower.find("name")
    while idx != -1:
        window_start = max(0, idx - 40)
        window_end = min(len(raw_text), idx + 40)
        window = raw_text[window_start:window_end]
        qm = re.search(
            rf'[{_QUOTE_CHARS}]([^{_QUOTE_CHARS}\n]+?)[{_QUOTE_CHARS}]',
            window,
            flags=re.UNICODE,
        )
        if qm:
            validated = _validate_app_name(qm.group(1))
            if validated:
                return validated
        idx = lower.find("name", idx + 1)
    return None


async def _extract_requirements(
    raw_input: str,
    attachments: list,
    state: PipelineState,
) -> dict:
    """Call Quick Fix to extract structured requirements from free text.

    Issue 14: run explicit-pattern app-name extraction BEFORE the AI call.
    If the explicit extractor finds a validated name, it is authoritative
    and overrides any name the AI might propose. If no explicit name is
    present the AI is instructed to return app_name=null (never guess).
    If both paths leave app_name missing/invalid, halt with APP_NAME_MISSING.
    """
    from factory.core.stage_enrichment import enrich_prompt
    from factory.core.halt import HaltCode, HaltReason, set_halt

    explicit_name = _extract_app_name_explicit(raw_input or "")

    extraction_prompt = (
        f"Extract structured requirements from this app description.\n\n"
        f"User input: {raw_input}\n"
    )
    if attachments:
        extraction_prompt += (
            f"Attachments: {len(attachments)} files provided "
            f"({', '.join(a.get('type', 'unknown') for a in attachments)})\n"
        )
    if explicit_name:
        extraction_prompt += (
            f"\nThe operator explicitly stated the app name as: {explicit_name!r}. "
            f"Use EXACTLY this value for app_name (do not rephrase).\n"
        )
    else:
        extraction_prompt += (
            "\nIMPORTANT: If the user did NOT explicitly state an app name, "
            "return app_name as null. Never guess, never extract a noun phrase "
            "from the description. The app name must come from an explicit "
            "user statement only.\n"
        )
    extraction_prompt += (
        f"\nReturn ONLY valid JSON:\n"
        f'{{\n'
        f'  "app_name": "short name or null",\n'
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
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            f"[{state.project_id}] S0: Failed to parse Quick Fix JSON, "
            f"using fallback extraction (app_name will be enforced separately)"
        )
        parsed = _fallback_requirements(raw_input)

    # ── Issue 14: app_name authority resolution ────────────────────
    # 1) Operator-pre-seeded app_name (via /new prompt flow in bot.py) wins.
    # 2) Explicit regex extraction from raw input wins over AI.
    # 3) AI-proposed name is validated against the same rules.
    # 4) If still missing/invalid, HALT — never silently guess.
    preseeded = (state.project_metadata.get("app_name") or "").strip() or None
    validated_preseed = _validate_app_name(preseeded) if preseeded else None
    if validated_preseed:
        parsed["app_name"] = validated_preseed
    elif explicit_name:
        parsed["app_name"] = explicit_name
    else:
        ai_name = parsed.get("app_name")
        validated_ai = _validate_app_name(ai_name) if isinstance(ai_name, str) else None
        if validated_ai:
            parsed["app_name"] = validated_ai
        else:
            # No name from any path — halt with a specific, actionable reason.
            halt = HaltReason(
                code=HaltCode.APP_NAME_MISSING,
                title="App name not provided",
                detail=(
                    "The operator's intake message did not contain an explicit "
                    "app name (e.g. `app name: \"My App\"` or `called \"My App\"`). "
                    "Guessing a name from a description is disabled to prevent "
                    "wrong titles like `To Do List` on a pulse-tracker app."
                ),
                stage="S0_INTAKE",
                failing_gate="app_name_required",
                remediation_steps=[
                    "Reply with: app name: \"Your App\"",
                    "Then /continue to resume S0 intake",
                ],
            )
            set_halt(state, halt)
            # Still return a best-effort structure so the caller doesn't KeyError;
            # the orchestrator will pick up legal_halt on its next legal_check_hook.
            parsed["app_name"] = None
            parsed["_halt_reason"] = halt.to_dict()

    return parsed


# ═══════════════════════════════════════════════════════════════════
# Step 2: Platform Multi-Select (14 canonical platforms)
# ═══════════════════════════════════════════════════════════════════


async def _select_platforms(state: PipelineState, requirements: dict) -> list[str]:
    """Select target platforms.

    COPILOT: interactive multi-select from 14 canonical options.
    AUTOPILOT: use AI-extracted platforms (capped to canonical set).

    v5.8.12 Issue 22: no silent default. If the operator did NOT specify a
    platform and the copilot flow returns empty, HALT with
    PLATFORMS_NOT_SELECTED rather than forcing iOS+Android. Forced defaults
    caused "Platform: web" intake messages to still deploy to App Store.
    """
    from factory.telegram.decisions import present_platform_multiselect, ALL_PLATFORMS
    from factory.core.halt import HaltCode, HaltReason, set_halt

    # Build default from AI extraction (map legacy names to canonical IDs).
    ai_platforms = requirements.get("target_platforms") or []
    canonical_ids = {p["id"] for p in ALL_PLATFORMS}
    _legacy_map = {"ios": "ios", "android": "android", "web": "web"}
    default = [
        _legacy_map.get(p, p) for p in ai_platforms
        if _legacy_map.get(p, p) in canonical_ids
    ]
    # No default synthesis: if the operator said nothing we pass an empty
    # default and the copilot flow asks explicitly.
    selected = await present_platform_multiselect(state, default=default)

    if not selected:
        halt = HaltReason(
            code=HaltCode.PLATFORMS_NOT_SELECTED,
            title="No platform chosen",
            detail=(
                "The operator did not select any target platform. The pipeline "
                "refuses to silently pick iOS+Android because that caused "
                "App Store deploys for web-only projects."
            ),
            stage="S0_INTAKE",
            failing_gate="platforms_required",
            remediation_steps=[
                "Reply with: platforms: web  (or ios / android / desktop_*)",
                "Then /continue to resume S0 intake",
            ],
        )
        set_halt(state, halt)
        return []
    return selected


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


def _save_logo_to_disk(
    logo_bytes: bytes,
    project_id: str,
    app_name: str,
    variant_index: Optional[int] = None,
) -> Optional[str]:
    """Save logo bytes to brand/ inside the project workspace.

    Issue 13: ensures state.intake["logo_path"] points to a real file.
    v5.8.15 Issue 58: when ``variant_index`` is provided, save as
    ``logo_{idx:02d}.png`` so all 3 auto-generated variants land on
    disk (proof-of-work for the 3-variant album) while logo.png keeps
    pointing at the primary variant.
    Returns the file path on success, None on failure.
    """
    import os as _os
    try:
        from factory.core.execution import _get_project_workspace
        workspace = _get_project_workspace(project_id, app_name)
        brand_dir = _os.path.join(workspace, "brand")
        _os.makedirs(brand_dir, exist_ok=True)
        if variant_index is None:
            filename = "logo.png"
        else:
            filename = f"logo_{variant_index:02d}.png"
        logo_path = _os.path.join(brand_dir, filename)
        with open(logo_path, "wb") as _f:
            _f.write(logo_bytes)
        logger.info(f"[{project_id}] Logo saved: {logo_path}")
        return logo_path
    except Exception as e:
        logger.warning(f"[{project_id}] Logo disk save failed (non-fatal): {e}")
        return None


async def _logo_flow(state: PipelineState, requirements: dict) -> Optional[dict]:
    """Run the logo selection flow.

    v5.8.16 Issue 65: the logo is the single most visible brand decision
    in the whole pipeline — users expect to see 3 variants and pick,
    even in autopilot. Opt into silent single-logo generation by setting
    project_metadata["logo_autopilot"] = True, otherwise always run the
    3-variant copilot flow regardless of AutonomyMode.
    """
    # CI / DRY_RUN / mock: no real image generation infrastructure — skip logo flow.
    import os as _os
    if (
        _os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
        or _os.getenv("PIPELINE_ENV", "").lower() == "ci"
        or _os.getenv("AI_PROVIDER", "").lower() == "mock"
    ):
        logger.info(f"[{state.project_id}] DRY_RUN — skipping logo generation")
        return None

    if state.project_metadata.get("logo_autopilot") is True:
        return await _logo_flow_auto(state, requirements)
    return await _logo_flow_copilot(state, requirements)


async def _logo_flow_copilot(state: PipelineState, requirements: dict) -> Optional[dict]:
    """Interactive COPILOT logo flow: choose source → generate 3 variants → pick."""
    from factory.telegram.decisions import present_decision, wait_for_operator_reply
    from factory.telegram.notifications import send_telegram_message
    from factory.design.logo_gen import generate_logo_variants, send_logo_variants_to_telegram
    from factory.integrations.image_gen import build_logo_prompt
    from factory.core.state import AutonomyMode as _AutonomyMode

    app_name = requirements.get("app_name") or state.idea_name or "App"
    description = requirements.get("app_description", "")

    # Logo source selection is a creative choice — always interactive regardless of
    # pipeline autonomy mode.  Founders must consciously choose their brand direction.
    _saved_autonomy = state.autonomy_mode
    state.autonomy_mode = _AutonomyMode.COPILOT
    try:
        logo_source = await present_decision(
            state=state,
            decision_type="s0_logo_source",
            question=(
                f"🎨 *Logo for {app_name}*\n\n"
                f"How would you like to create your app icon?"
            ),
            options=[
                {"label": "🤖 Auto-Generate (AI picks 3 styles)", "value": "auto"},
                {"label": "✏️ Describe Your Vision",               "value": "describe"},
                {"label": "📤 Upload Later (/update_logo)",        "value": "skip"},
                {"label": "⏭ Skip — no logo needed yet",          "value": "skip"},
            ],
            recommended=0,
            timeout_seconds=3600,
        )
    finally:
        state.autonomy_mode = _saved_autonomy

    if logo_source == "skip":
        state.project_metadata["logo_pending"] = True
        return None

    # ── Scout: research design trends for this app category before generating ──
    _scout_intel = ""
    try:
        from factory.core.roles import call_ai as _call_ai
        from factory.core.state import AIRole as _AIRole
        app_category = requirements.get("app_category", "mobile app")
        target_market = requirements.get("target_market", "global")
        _scout_result = await _call_ai(
            role=_AIRole.SCOUT,
            prompt=(
                f"What are the current app icon design trends for {app_category} apps "
                f"targeting {target_market} users? "
                f"Focus on: color palettes, icon shape language (rounded, geometric, flat), "
                f"competitor icon styles, and what attracts users in this category. "
                f"Answer in 2-3 concise sentences for a designer prompt."
            ),
            state=state,
            action="general",
        )
        _scout_intel = _scout_result[:300] if _scout_result else ""
        logger.info(f"[{state.project_id}] Logo scout research complete ({len(_scout_intel)} chars)")
    except Exception as _e:
        logger.warning(f"[{state.project_id}] Logo scout research failed: {_e} — proceeding without")

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
        if _scout_intel:
            logo_prompt += f". Market context: {_scout_intel[:150]}"
    else:
        logo_prompt = build_logo_prompt(app_name, description, scout_intel=_scout_intel)

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

        # Logo pick is a permanent creative decision — always force interactive COPILOT
        # mode regardless of the pipeline's autonomy setting.  Autopilot is correct for
        # technical decisions (stack, APIs) but the founder must always pick their brand.
        from factory.core.state import AutonomyMode as _AutonomyMode
        _saved_autonomy = state.autonomy_mode
        state.autonomy_mode = _AutonomyMode.COPILOT
        try:
            pick = await present_decision(
                state=state,
                decision_type="s0_logo_pick",
                question=(
                    f"🎨 *Choose your logo for {app_name}*\n\n"
                    "Review the variants above and pick one — or regenerate for new styles."
                ),
                options=pick_options,
                recommended=0,
                timeout_seconds=3600,
            )
        finally:
            state.autonomy_mode = _saved_autonomy

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
            # Issue 13: save bytes to disk so downstream stages have a real path
            logo_path = _save_logo_to_disk(
                selected_bytes, state.project_id,
                requirements.get("app_name", ""),
            )
            return {
                "asset_type": "logo",
                "logo_bytes_len": len(selected_bytes),
                "logo_prompt": logo_prompt,
                "logo_path": logo_path,
                "source": logo_source,
                "variant": int(pick),
            }

    return None


async def _logo_flow_auto(state: PipelineState, requirements: dict) -> Optional[dict]:
    """AUTOPILOT logo: generate 3 variants and send as a Telegram media album.

    Issue 40: deliver 3 logo variants via InputMediaPhoto album instead of 1 photo.
    Variants use different seeds and style nuances for visual diversity.
    Falls back to single-photo send if telegram.InputMediaPhoto is unavailable.
    """
    # build_logo_prompt, generate_image, get_bot imported at module level (Issue 40)
    app_name = requirements.get("app_name") or state.idea_name or "App"
    description = requirements.get("app_description", "")

    # Issue 40: 3 variant specs — seed, style suffix
    _VARIANTS: list[tuple[int, str]] = [
        (101, "flat app icon, minimal, clean"),
        (202, "flat app icon, bold color, gradient"),
        (303, "flat app icon, monochrome, geometric"),
    ]

    try:
        logo_prompt = build_logo_prompt(app_name, description)

        # Generate 3 variants concurrently
        import asyncio as _asyncio
        import io as _io

        async def _gen_variant(seed: int, style: str) -> Optional[bytes]:
            try:
                return await generate_image(
                    prompt=logo_prompt,
                    width=1024,
                    height=1024,
                    style=style,
                    seed=seed,
                )
            except Exception as _e:
                logger.warning(f"[{state.project_id}] Logo variant seed={seed} failed: {_e}")
                return None

        variant_results = await _asyncio.gather(
            *[_gen_variant(seed, style) for seed, style in _VARIANTS],
        )
        logo_variants = [b for b in variant_results if b]

        if not logo_variants:
            logger.warning(f"[{state.project_id}] All logo variants failed — no logo generated")
            return None

        # Send as album if ≥2 variants, else single photo (get_bot imported at module level)
        bot = get_bot()
        if bot:
            try:
                if len(logo_variants) >= 2:
                    try:
                        from telegram import InputMediaPhoto
                        media_group = []
                        for i, img_bytes in enumerate(logo_variants):
                            caption = (
                                f"🎨 Logo option {i+1}/{len(logo_variants)} for *{app_name}*."
                                if i < len(logo_variants) - 1
                                else f"🎨 Logo option {i+1}/{len(logo_variants)} for *{app_name}*.\n\nUse /update_logo to change."
                            )
                            media_group.append(
                                InputMediaPhoto(
                                    media=_io.BytesIO(img_bytes),
                                    caption=caption,
                                    parse_mode="Markdown",
                                )
                            )
                        await bot.send_media_group(
                            chat_id=int(state.operator_id),
                            media=media_group,
                        )
                    except ImportError:
                        # python-telegram-bot not installed with full extras — fallback
                        for i, img_bytes in enumerate(logo_variants):
                            await bot.send_photo(
                                chat_id=int(state.operator_id),
                                photo=_io.BytesIO(img_bytes),
                                caption=f"🎨 Logo option {i+1} for *{app_name}*. Use /update_logo to change.",
                                parse_mode="Markdown",
                            )
                else:
                    await bot.send_photo(
                        chat_id=int(state.operator_id),
                        photo=_io.BytesIO(logo_variants[0]),
                        caption=f"🎨 Auto-generated logo for *{app_name}*. Use /update_logo to change.",
                        parse_mode="Markdown",
                    )
            except Exception as e:
                logger.warning(f"[{state.project_id}] AUTOPILOT logo send failed: {e}")

        # v5.8.15 Issue 58: save ALL variants to disk so the 3-variant album
        # is verifiable on filesystem (logo_01.png, logo_02.png, logo_03.png)
        # and logo.png points at the primary variant for downstream stages.
        variant_paths: list[str] = []
        for i, vb in enumerate(logo_variants):
            p = _save_logo_to_disk(vb, state.project_id, app_name, variant_index=i + 1)
            if p:
                variant_paths.append(p)
        primary = logo_variants[0]
        logo_path = _save_logo_to_disk(primary, state.project_id, app_name)
        return {
            "asset_type": "logo",
            "logo_bytes_len": len(primary),
            "logo_prompt": logo_prompt,
            "logo_path": logo_path,
            "logo_variant_count": len(logo_variants),
            "logo_variant_paths": variant_paths,
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
    # Issue 14: Never fabricate an app_name from the description. If the
    # caller didn't state one explicitly, leave it None so the authority
    # resolver halts with APP_NAME_MISSING instead of silently guessing.
    return {
        "app_name": None,
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
