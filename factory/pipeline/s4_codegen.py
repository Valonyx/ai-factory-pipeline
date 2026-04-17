"""
AI Factory Pipeline v5.8 — S4 Code Generation Node

Implements:
  - §4.4 S4 CodeGen (full generation + retry fix mode)
  - Phase 0: Tech inventory — discover, check wired status, Scout-verify, classify
  - Phase 0.5: Operator Telegram wiring requests (cost + instructions) for unwired tech
  - Phase 1: Code generation enriched with design tokens (S3) + legal texts (S1)
  - Phase 1.5: Per-screen expansion to 100+ files
  - Phase 2: Security rules
  - Phase 3: CI/CD configuration
  - Phase 4: Quick Fix validation
  - Phase 5: Mother Memory codegen nodes
  - §4.4.2 CI/CD configuration generation
  - War Room targeted fix on retry (§2.2.8)

Automation levels:
  FULL_AI       — AI generates all code automatically
  AI_GUIDED     — AI generates code; requires a wired service (env vars present)
  HUMAN_REQUIRED — needs operator action (account, API key, payment)
  NOT_AUTOMATABLE — physical hardware / proprietary / manual process only

Spec Authority: v5.8 §4.4, §4.4.2
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from factory.core.state import (
    AIRole,
    PipelineState,
    Stage,
    TechStack,
)
from factory.core.roles import call_ai
from factory.pipeline.graph import pipeline_node, register_stage_node
from factory.pipeline.stage_chain import inject_chain_context as _inject_cc

logger = logging.getLogger("factory.pipeline.s4_codegen")


# ═══════════════════════════════════════════════════════════════════
# §4.4 Tech Inventory System
# ═══════════════════════════════════════════════════════════════════

class AutomationLevel(str, Enum):
    FULL_AI          = "full_ai"          # AI generates everything, no service needed
    AI_GUIDED        = "ai_guided"        # AI generates code when service is wired
    HUMAN_REQUIRED   = "human_required"   # account/key/payment needed first
    NOT_AUTOMATABLE  = "not_automatable"  # physical/proprietary; AI provides instructions


@dataclass
class TechItem:
    id: str
    name: str
    category: str               # "database", "auth", "payments", "push", "analytics", etc.
    why_needed: str
    env_vars: list[str]         # env var names that confirm it's wired
    wired: bool = False
    capability: AutomationLevel = AutomationLevel.AI_GUIDED
    cost_estimate: str = "Unknown"
    monthly_cost: str = ""
    setup_url: str = ""
    setup_instructions: str = ""
    alternatives: list[str] = field(default_factory=list)
    scout_verified: bool = False
    skip: bool = False          # operator chose to skip


# Catalog of known services with their check env vars and defaults
# Used as a starting point; Strategist adds project-specific extras.
_KNOWN_TECH_CATALOG: dict[str, dict] = {
    # ── Core/Framework ────────────────────────────────────────────
    "flutterflow": {
        "category": "framework", "env_vars": [],
        "capability": AutomationLevel.FULL_AI,
        "cost_estimate": "Free (Community) / $30+/mo (Pro)",
        "setup_url": "https://flutterflow.io",
    },
    "react_native": {
        "category": "framework", "env_vars": [],
        "capability": AutomationLevel.FULL_AI,
        "cost_estimate": "Free (open source)",
        "setup_url": "https://reactnative.dev",
    },
    "swift": {
        "category": "framework", "env_vars": [],
        "capability": AutomationLevel.FULL_AI,
        "cost_estimate": "Free (requires Apple Developer: $99/year for distribution)",
        "setup_url": "https://developer.apple.com/programs/",
    },
    "kotlin": {
        "category": "framework", "env_vars": [],
        "capability": AutomationLevel.FULL_AI,
        "cost_estimate": "Free (Google Play: $25 one-time)",
        "setup_url": "https://play.google.com/console",
    },
    "unity": {
        "category": "framework", "env_vars": [],
        "capability": AutomationLevel.FULL_AI,
        "cost_estimate": "Free (Personal) / $185/mo (Pro)",
        "setup_url": "https://unity.com/pricing",
    },
    # ── Database / Backend ─────────────────────────────────────────
    "supabase": {
        "category": "database",
        "env_vars": ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (500MB) / $25/mo (Pro)",
        "setup_url": "https://supabase.com",
    },
    "firebase": {
        "category": "database",
        "env_vars": ["FIREBASE_PROJECT_ID", "FIREBASE_CREDENTIALS"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (Spark) / Pay-as-you-go (Blaze)",
        "setup_url": "https://console.firebase.google.com",
    },
    "mongodb_atlas": {
        "category": "database",
        "env_vars": ["MONGODB_URI"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (512MB) / $57+/mo (Dedicated)",
        "setup_url": "https://mongodb.com/atlas",
    },
    "postgresql": {
        "category": "database",
        "env_vars": ["DATABASE_URL"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (self-hosted) / $15+/mo (managed)",
        "setup_url": "https://neon.tech or https://railway.app",
    },
    # ── Authentication ─────────────────────────────────────────────
    "supabase_auth": {
        "category": "auth",
        "env_vars": ["SUPABASE_URL", "SUPABASE_ANON_KEY"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Included with Supabase",
        "setup_url": "https://supabase.com/docs/guides/auth",
    },
    "firebase_auth": {
        "category": "auth",
        "env_vars": ["FIREBASE_PROJECT_ID"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free up to 10k/month, then $0.0055/MAU",
        "setup_url": "https://firebase.google.com/docs/auth",
    },
    # ── Payments (KSA) ─────────────────────────────────────────────
    "moyasar": {
        "category": "payments",
        "env_vars": ["MOYASAR_API_KEY", "MOYASAR_SECRET_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "2.25% + SAR 1 per transaction (no setup fee)",
        "monthly_cost": "Transaction-based only",
        "setup_url": "https://moyasar.com/ar/signup",
        "alternatives": ["tap_payments", "payfort"],
    },
    "tap_payments": {
        "category": "payments",
        "env_vars": ["TAP_SECRET_KEY", "TAP_PUBLISHABLE_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "2.75% per transaction (domestic); CR required",
        "setup_url": "https://tap.company/en-sa",
        "alternatives": ["moyasar"],
    },
    "stc_pay": {
        "category": "payments",
        "env_vars": ["STC_PAY_MERCHANT_ID", "STC_PAY_API_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "Free for customers; merchant fees negotiated",
        "setup_url": "https://b.stcpay.com.sa",
        "alternatives": ["moyasar"],
    },
    "tamara": {
        "category": "payments",
        "env_vars": ["TAMARA_API_KEY", "TAMARA_MERCHANT_URL"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "~4–6% merchant fee (BNPL)",
        "setup_url": "https://merchants.tamara.co",
        "alternatives": ["tabby"],
    },
    "apple_pay": {
        "category": "payments",
        "env_vars": ["APPLE_PAY_MERCHANT_ID"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "No fee (uses existing payment processor)",
        "setup_url": "https://developer.apple.com/apple-pay/",
        "alternatives": [],
    },
    # ── Push Notifications ─────────────────────────────────────────
    "fcm": {
        "category": "push",
        "env_vars": ["FIREBASE_PROJECT_ID", "FCM_SERVER_KEY"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (unlimited)",
        "setup_url": "https://firebase.google.com/docs/cloud-messaging",
    },
    "onesignal": {
        "category": "push",
        "env_vars": ["ONESIGNAL_APP_ID", "ONESIGNAL_API_KEY"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (10k subs) / $9+/mo",
        "setup_url": "https://onesignal.com",
    },
    # ── SMS / OTP ──────────────────────────────────────────────────
    "twilio": {
        "category": "sms",
        "env_vars": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "$0.0079/SMS (US); KSA rates vary ~$0.05/SMS",
        "setup_url": "https://twilio.com",
        "alternatives": ["unifonic", "taqnyat"],
    },
    "unifonic": {
        "category": "sms",
        "env_vars": ["UNIFONIC_ACCOUNT_SID", "UNIFONIC_SENDER_ID"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "~0.05–0.08 SAR/SMS (KSA); account approval required",
        "setup_url": "https://unifonic.com",
        "alternatives": ["twilio", "taqnyat"],
    },
    # ── Storage ────────────────────────────────────────────────────
    "supabase_storage": {
        "category": "storage",
        "env_vars": ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "1GB free, $0.021/GB/mo after",
        "setup_url": "https://supabase.com/docs/guides/storage",
    },
    "aws_s3": {
        "category": "storage",
        "env_vars": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_S3_BUCKET"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "$0.023/GB/mo + data transfer costs",
        "setup_url": "https://aws.amazon.com/s3/",
    },
    "cloudinary": {
        "category": "storage",
        "env_vars": ["CLOUDINARY_URL"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (25 credits) / $89+/mo",
        "setup_url": "https://cloudinary.com",
    },
    # ── Analytics ─────────────────────────────────────────────────
    "firebase_analytics": {
        "category": "analytics",
        "env_vars": ["FIREBASE_PROJECT_ID"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free",
        "setup_url": "https://firebase.google.com/docs/analytics",
    },
    "mixpanel": {
        "category": "analytics",
        "env_vars": ["MIXPANEL_TOKEN"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (20M events/mo) / $28+/mo",
        "setup_url": "https://mixpanel.com",
    },
    # ── Maps ──────────────────────────────────────────────────────
    "google_maps": {
        "category": "maps",
        "env_vars": ["GOOGLE_MAPS_API_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "$200 free credit/mo; $7/1000 map loads after",
        "setup_url": "https://console.cloud.google.com",
    },
    # ── AI / ML ───────────────────────────────────────────────────
    "openai": {
        "category": "ai",
        "env_vars": ["OPENAI_API_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "GPT-4o: $2.50/1M input tokens; GPT-4o-mini: $0.15/1M",
        "setup_url": "https://platform.openai.com",
        "alternatives": ["anthropic", "gemini"],
    },
    "anthropic": {
        "category": "ai",
        "env_vars": ["ANTHROPIC_API_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "Sonnet 4.6: $3/1M input; Haiku 4.5: $0.25/1M",
        "setup_url": "https://console.anthropic.com",
    },
    # ── CI/CD & Build ─────────────────────────────────────────────
    "github_actions": {
        "category": "ci_cd",
        "env_vars": ["GITHUB_TOKEN"],
        "capability": AutomationLevel.AI_GUIDED,
        "cost_estimate": "Free (public repos, 2000 min/mo private)",
        "setup_url": "https://github.com/features/actions",
    },
    "apple_developer": {
        "category": "distribution",
        "env_vars": ["APPLE_DEVELOPER_TEAM_ID", "APPLE_CERT_P12"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "$99/year (Individual) / $299/year (Enterprise)",
        "setup_url": "https://developer.apple.com/programs/",
    },
    "google_play_console": {
        "category": "distribution",
        "env_vars": ["GOOGLE_PLAY_JSON_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "$25 one-time registration",
        "setup_url": "https://play.google.com/console",
    },
    # ── Email ─────────────────────────────────────────────────────
    "sendgrid": {
        "category": "email",
        "env_vars": ["SENDGRID_API_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "Free (100/day) / $19.95+/mo",
        "setup_url": "https://sendgrid.com",
        "alternatives": ["resend", "mailgun"],
    },
    "resend": {
        "category": "email",
        "env_vars": ["RESEND_API_KEY"],
        "capability": AutomationLevel.HUMAN_REQUIRED,
        "cost_estimate": "Free (3000/mo) / $20+/mo",
        "setup_url": "https://resend.com",
    },
}


def _check_wired_status(item_id: str, env_vars: list[str], state: PipelineState) -> bool:
    """Check if a tech item is already wired.

    Wired means: all required env vars are present in os.environ
    OR in state.project_metadata (operator may have stored keys there).
    """
    if not env_vars:
        return True  # No env vars required → always wired (e.g. open-source framework)

    meta = state.project_metadata or {}
    for var in env_vars:
        in_env  = bool(os.environ.get(var))
        in_meta = bool(meta.get(var) or meta.get(var.lower()))
        if not (in_env or in_meta):
            return False
    return True


async def _scout_verify_tech_item(
    state: PipelineState,
    item: TechItem,
) -> TechItem:
    """Scout verifies a tech item: confirms it's available in KSA, gets current pricing.

    Updates item.cost_estimate, item.setup_instructions, item.scout_verified.
    Non-fatal: if Scout fails, returns item unchanged.
    """
    try:
        research = await call_ai(
            role=AIRole.SCOUT,
            prompt=(
                f"Research '{item.name}' ({item.category}) for a KSA-based app project.\n\n"
                f"Return ONLY a JSON object with these fields:\n"
                f'{{\n'
                f'  "available_in_ksa": true/false,\n'
                f'  "current_pricing": "one-line pricing summary",\n'
                f'  "monthly_cost_usd": "estimate or null",\n'
                f'  "setup_steps": ["step 1", "step 2", "step 3"],\n'
                f'  "required_documents": ["CR", "IBAN", "..."] or [],\n'
                f'  "ksa_alternative": "name of better KSA alternative or null",\n'
                f'  "api_ready": true/false\n'
                f'}}\n\n'
                f"Known info: {item.cost_estimate}"
            ),
            state=state,
            action="general",
        )

        # Extract JSON from Scout response
        start = research.find("{")
        end   = research.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(research[start:end])

            if data.get("current_pricing"):
                item.cost_estimate = data["current_pricing"]
            if data.get("monthly_cost_usd"):
                item.monthly_cost = data["monthly_cost_usd"]

            steps = data.get("setup_steps", [])
            if steps:
                item.setup_instructions = "\n".join(
                    f"  {i+1}. {s}" for i, s in enumerate(steps)
                )

            ksa_alt = data.get("ksa_alternative")
            if ksa_alt and ksa_alt not in item.alternatives:
                item.alternatives.insert(0, ksa_alt)

            item.scout_verified = True

    except Exception as e:
        logger.warning(
            f"[{state.project_id}] Scout verify failed for {item.name}: {e}"
        )

    return item


async def _run_tech_inventory(
    state: PipelineState,
    blueprint_data: dict,
    requirements: dict,
) -> list[TechItem]:
    """Full tech inventory: discover → check wired → Scout-verify → classify.

    Spec: v5.8 §4.4 Phase 0

    Returns list of TechItem objects, each with wired status and capability level.
    """
    stack_value = blueprint_data.get("selected_stack", "flutterflow")
    app_name    = blueprint_data.get("app_name", state.project_id)
    services    = blueprint_data.get("services", {})
    env_vars_bp = blueprint_data.get("env_vars", {})
    features    = requirements.get("features_must", [])
    auth_method = blueprint_data.get("auth_method", "email")
    has_payments = requirements.get("has_payments", False) or "payment" in str(features).lower()
    has_maps    = "map" in str(features).lower() or "location" in str(features).lower()
    has_push    = "notification" in str(features).lower() or "push" in str(features).lower()
    has_ai_feat = "ai" in str(features).lower() or "chat" in str(features).lower()

    # ── Step 1: Strategist identifies all needed tech for this specific project ──
    logger.info(f"[{state.project_id}] Tech inventory: Strategist identifying required tech")
    _tech_inv_base = (
        f"List ALL tech services, APIs, SDKs, and providers required to "
        f"fully implement '{app_name}'.\n\n"
        f"Stack: {stack_value}\n"
        f"Features: {features[:15]}\n"
        f"Auth method: {auth_method}\n"
        f"Services from blueprint: {services}\n"
        f"Env vars specified: {list(env_vars_bp.keys())[:20]}\n"
        f"Has payments: {has_payments}\n"
        f"Has maps: {has_maps}\n"
        f"Has push notifications: {has_push}\n"
        f"Has AI features: {has_ai_feat}\n\n"
        f"Return ONLY a JSON array:\n"
        f'[\n'
        f'  {{\n'
        f'    "id": "snake_case_id",\n'
        f'    "name": "Service Name",\n'
        f'    "category": "database|auth|payments|push|analytics|maps|storage|email|sms|ai|ci_cd|framework|other",\n'
        f'    "why_needed": "one sentence explaining why this app needs it",\n'
        f'    "env_vars": ["ENV_VAR_NAME"],\n'
        f'    "required": true\n'
        f'  }}\n'
        f']\n\n'
        f"Only include services that are truly necessary. "
        f"Be specific — use exact service names (e.g. Moyasar, not just Payments)."
    )
    strategist_raw = await call_ai(
        role=AIRole.STRATEGIST,
        prompt=_inject_cc(_tech_inv_base, state, current_stage="s4_codegen", compact=True),
        state=state,
        action="plan_architecture",
    )

    # Parse Strategist output
    discovered: list[dict] = []
    try:
        start = strategist_raw.find("[")
        end   = strategist_raw.rfind("]") + 1
        if start >= 0 and end > start:
            discovered = json.loads(strategist_raw[start:end])
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[{state.project_id}] Tech inventory: Strategist parse failed — using known catalog")

    # ── Step 2: Build TechItem list — merge discovered with known catalog ──
    items: list[TechItem] = []
    seen_ids: set[str] = set()

    for raw in discovered:
        item_id = raw.get("id", "").lower().replace("-", "_")
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        # Use catalog defaults if known; otherwise use Strategist-provided values
        catalog = _KNOWN_TECH_CATALOG.get(item_id, {})
        item = TechItem(
            id           = item_id,
            name         = raw.get("name", item_id),
            category     = raw.get("category", catalog.get("category", "other")),
            why_needed   = raw.get("why_needed", ""),
            env_vars     = raw.get("env_vars") or catalog.get("env_vars", []),
            capability   = catalog.get("capability", AutomationLevel.AI_GUIDED),
            cost_estimate= catalog.get("cost_estimate", "Unknown — research needed"),
            setup_url    = catalog.get("setup_url", ""),
            alternatives = catalog.get("alternatives", []),
        )
        items.append(item)

    # Ensure the selected stack itself is in the list
    if stack_value not in seen_ids:
        catalog = _KNOWN_TECH_CATALOG.get(stack_value, {})
        items.insert(0, TechItem(
            id=stack_value, name=stack_value.replace("_", " ").title(),
            category="framework", why_needed="Selected app development stack",
            env_vars=catalog.get("env_vars", []),
            capability=catalog.get("capability", AutomationLevel.FULL_AI),
            cost_estimate=catalog.get("cost_estimate", "See docs"),
            setup_url=catalog.get("setup_url", ""),
        ))
        seen_ids.add(stack_value)

    # ── Step 3: Check wired status for each item ──
    for item in items:
        item.wired = _check_wired_status(item.id, item.env_vars, state)

    # ── Step 4: Scout-verify unwired HUMAN_REQUIRED items (costs + instructions) ──
    # Only verify items that need operator action — to save cost
    verify_targets = [
        i for i in items
        if not i.wired and i.capability in (
            AutomationLevel.HUMAN_REQUIRED,
            AutomationLevel.AI_GUIDED,
        )
    ]
    for item in verify_targets[:8]:  # cap at 8 Scout calls
        item = await _scout_verify_tech_item(state, item)

    wired_count    = sum(1 for i in items if i.wired)
    unwired_count  = sum(1 for i in items if not i.wired)
    logger.info(
        f"[{state.project_id}] Tech inventory: {len(items)} items — "
        f"{wired_count} wired, {unwired_count} need attention"
    )
    return items


async def _handle_unwired_tech(
    state: PipelineState,
    items: list[TechItem],
) -> list[TechItem]:
    """Send Telegram wiring requests for each unwired HUMAN_REQUIRED tech item.

    Spec: v5.8 §4.4 Phase 0.5

    For each unwired HUMAN_REQUIRED item:
    1. Send Telegram message with: what, why, cost, signup URL, wiring instructions
    2. Present 3-option menu: Done / Skip / Use Alternative
    3. If Done: prompt for API key/env var values and store in state.project_metadata
    4. If Skip: mark item.skip = True (pipeline continues with AI stub)
    5. If Use Alternative: present alternatives list and repeat

    For AI_GUIDED unwired items: send a softer warning (non-blocking).
    For NOT_AUTOMATABLE: send detailed instructions + AI will write a manual guide.
    """
    try:
        from factory.telegram.decisions import present_decision, wait_for_operator_reply
        from factory.telegram.notifications import send_telegram_message
    except Exception as e:
        logger.warning(f"[{state.project_id}] Telegram unavailable for wiring requests: {e}")
        return items

    human_required_unwired = [
        i for i in items
        if not i.wired and not i.skip
        and i.capability == AutomationLevel.HUMAN_REQUIRED
    ]
    ai_guided_unwired = [
        i for i in items
        if not i.wired and not i.skip
        and i.capability == AutomationLevel.AI_GUIDED
    ]
    not_automatable = [
        i for i in items
        if i.capability == AutomationLevel.NOT_AUTOMATABLE
    ]

    # ── Soft warning for AI_GUIDED unwired ──
    if ai_guided_unwired:
        names = ", ".join(i.name for i in ai_guided_unwired[:5])
        await send_telegram_message(
            state.operator_id,
            f"⚠️ *Missing service credentials*\n\n"
            f"The following services are needed but their API keys are not wired:\n"
            f"{names}\n\n"
            f"Code will be generated with placeholder env vars. "
            f"Wire them in your environment to enable full functionality.",
            parse_mode="Markdown",
        )

    # ── NOT_AUTOMATABLE notice ──
    if not_automatable:
        names = ", ".join(i.name for i in not_automatable[:3])
        await send_telegram_message(
            state.operator_id,
            f"📋 *Manual implementation required*\n\n"
            f"{names} cannot be fully automated.\n"
            f"AI will generate a detailed implementation guide with step-by-step "
            f"instructions for you to follow.",
            parse_mode="Markdown",
        )

    # ── HUMAN_REQUIRED — interactive wiring loop ──
    for item in human_required_unwired:
        env_var_list = "\n".join(f"  • `{v}`" for v in item.env_vars) if item.env_vars else "  (none)"
        setup_steps  = item.setup_instructions or "  (Scout research in progress — see setup URL)"
        alternatives_text = ""
        if item.alternatives:
            alternatives_text = (
                f"\n\n*Alternatives:* {', '.join(item.alternatives[:3])}"
            )

        await send_telegram_message(
            state.operator_id,
            f"🔧 *Action required: {item.name}*\n\n"
            f"📦 *Category:* {item.category}\n"
            f"❓ *Why needed:* {item.why_needed}\n"
            f"💰 *Cost:* {item.cost_estimate}\n"
            f"{'💵 *Monthly estimate:* ' + item.monthly_cost + chr(10) if item.monthly_cost else ''}"
            f"🔗 *Signup/Setup URL:* {item.setup_url or 'See documentation'}\n\n"
            f"*Setup steps:*\n{setup_steps}\n\n"
            f"*Env vars to wire after setup:*\n{env_var_list}"
            f"{alternatives_text}",
            parse_mode="Markdown",
        )

        options = [
            {"label": "Done — I've set it up", "value": "done"},
            {"label": "Skip — generate stub code", "value": "skip"},
        ]
        if item.alternatives:
            options.append({
                "label": f"Use alternative ({item.alternatives[0]})",
                "value": f"alt:{item.alternatives[0]}",
            })

        try:
            choice = await present_decision(
                state=state,
                decision_type="tech_wiring",
                question=f"How would you like to proceed with *{item.name}*?",
                options=options,
                recommended=0,
            )
        except Exception:
            choice = "skip"

        if choice == "done":
            # Re-check wired status
            item.wired = _check_wired_status(item.id, item.env_vars, state)
            if not item.wired and item.env_vars:
                # Ask operator to paste the keys
                await send_telegram_message(
                    state.operator_id,
                    f"Please paste your *{item.name}* credentials.\n"
                    f"Send them as:\n"
                    + "\n".join(f"`{v}=your_value_here`" for v in item.env_vars),
                    parse_mode="Markdown",
                )
                try:
                    raw_keys = await wait_for_operator_reply(state, timeout_seconds=600)
                    # Parse KEY=value lines
                    for line in raw_keys.strip().splitlines():
                        if "=" in line:
                            k, _, v = line.partition("=")
                            k = k.strip()
                            v = v.strip()
                            if k in item.env_vars:
                                state.project_metadata[k] = v
                                os.environ[k] = v
                    item.wired = _check_wired_status(item.id, item.env_vars, state)
                    if item.wired:
                        await send_telegram_message(
                            state.operator_id,
                            f"✅ *{item.name}* wired successfully!",
                            parse_mode="Markdown",
                        )
                except Exception:
                    pass

        elif choice == "skip":
            item.skip = True
            await send_telegram_message(
                state.operator_id,
                f"⏭ *{item.name}* skipped — placeholder code will be generated.",
                parse_mode="Markdown",
            )

        elif choice and choice.startswith("alt:"):
            alt_name = choice[4:]
            item.skip = True
            await send_telegram_message(
                state.operator_id,
                f"🔄 Noted: will use *{alt_name}* instead of *{item.name}*. "
                f"Code will be adapted.",
                parse_mode="Markdown",
            )
            # Record the alternative preference in metadata
            state.project_metadata[f"tech_alt_{item.id}"] = alt_name

    return items


async def _generate_tech_summary_message(
    state: PipelineState, items: list[TechItem],
) -> None:
    """Send a tech stack summary to the operator before code generation starts."""
    try:
        from factory.telegram.notifications import send_telegram_message

        wired      = [i for i in items if i.wired]
        skipped    = [i for i in items if i.skip]
        full_ai    = [i for i in items if i.capability == AutomationLevel.FULL_AI]
        not_auto   = [i for i in items if i.capability == AutomationLevel.NOT_AUTOMATABLE]

        lines = ["🛠 *Tech Stack Summary*\n"]
        lines.append(f"✅ Wired ({len(wired)}): " + ", ".join(i.name for i in wired[:6]))
        if skipped:
            lines.append(f"⏭ Skipped ({len(skipped)}): " + ", ".join(i.name for i in skipped[:4]))
        if full_ai:
            lines.append(f"🤖 Full AI ({len(full_ai)}): " + ", ".join(i.name for i in full_ai[:4]))
        if not_auto:
            lines.append(f"📋 Manual guide ({len(not_auto)}): " + ", ".join(i.name for i in not_auto[:3]))
        lines.append(f"\n🚀 Starting code generation...")

        await send_telegram_message(
            state.operator_id,
            "\n".join(lines),
            parse_mode="Markdown",
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# Full Pipeline Context — S0→S1→S2→S3 Constraint Envelope for S4
# ═══════════════════════════════════════════════════════════════════


@dataclass
class PipelineContext:
    """All upstream stage outputs distilled into a constraint envelope for S4.

    S4 CodeGen must honour EVERY field here. Nothing gets re-decided.
    """
    # ── S0: Intake ────────────────────────────────────────────────
    app_name: str = ""
    app_description: str = ""
    app_category: str = ""
    market: str = "ksa"
    target_platforms: list = field(default_factory=list)
    features_must: list = field(default_factory=list)
    features_nice: list = field(default_factory=list)
    estimated_complexity: str = "medium"
    has_payments: bool = False
    has_realtime: bool = False
    has_location: bool = False
    has_notifications: bool = False
    has_user_accounts: bool = True

    # ── S1: Legal ─────────────────────────────────────────────────
    blocked_features: list = field(default_factory=list)   # MUST NOT implement
    required_consents: list = field(default_factory=list)  # MUST wire in code
    data_classification: str = "internal"
    risk_level: str = "MEDIUM"
    payment_mode: str = "SANDBOX"                          # SANDBOX | LIVE
    pdpl_obligations: list = field(default_factory=list)
    compliance_matrix: list = field(default_factory=list)
    inapp_texts: dict = field(default_factory=dict)        # consent banner, etc.
    required_legal_docs: list = field(default_factory=list)
    legal_classification: str = "internal"

    # ── S2: Blueprint ─────────────────────────────────────────────
    selected_stack: str = "flutterflow"
    screens: list = field(default_factory=list)
    data_model: list = field(default_factory=list)
    api_endpoints: list = field(default_factory=list)
    auth_method: str = "email"
    services: dict = field(default_factory=dict)
    env_vars_spec: dict = field(default_factory=dict)      # from blueprint env_vars
    data_residency: str = "KSA"
    business_model: str = "general"
    compliance_artifacts: list = field(default_factory=list)
    brand_assets: dict = field(default_factory=dict)       # logo_path, splash_path
    ieee_docs_summary: dict = field(default_factory=dict)  # {doc_id: first 800 chars}
    ieee_doc_count: int = 0
    design_system: str = "material3"
    color_palette: dict = field(default_factory=dict)
    typography: dict = field(default_factory=dict)

    # ── S3: Design ────────────────────────────────────────────────
    project_type: str = "standard_app"
    design_tokens: dict = field(default_factory=dict)
    mockup_paths: list = field(default_factory=list)       # per-screen wireframe paths
    platform_assets: dict = field(default_factory=dict)   # icon sizes, splash specs
    specialist_docs: dict = field(default_factory=dict)   # GDD, art_bible, etc. (games)
    visual_style: str = "minimal"
    layout_patterns: list = field(default_factory=list)


def _build_full_pipeline_context(
    state: PipelineState,
    blueprint_data: dict,
) -> PipelineContext:
    """Build the full constraint envelope from all upstream stage outputs.

    S4 will never re-decide anything — it only implements what S0→S3 specified.
    """
    s0 = state.s0_output or {}
    s1 = state.s1_output or {}
    s2 = blueprint_data  # already passed in as blueprint_data
    s3 = state.s3_output or {}

    # ── IEEE docs: extract first 800 chars of each doc as a summary ──
    raw_ieee = s2.get("ieee_docs") or {}
    ieee_summary = {
        doc_id: (content[:800] + "…" if len(content) > 800 else content)
        for doc_id, content in raw_ieee.items()
    }

    # ── S3 design tokens: merge from both s3 vibe and s2 color_palette ──
    s3_vibe = s3.get("vibe") or s3.get("design_system") or {}
    palette = (
        s3_vibe.get("color_palette")
        or s3.get("color_palette")
        or s2.get("color_palette")
        or {}
    )
    typography = (
        s3_vibe.get("typography")
        or s3.get("typography")
        or s2.get("typography")
        or {}
    )
    design_tokens = s3.get("design_tokens") or {}
    if not design_tokens and palette:
        for k, v in palette.items():
            design_tokens[f"color-{k.replace('_', '-')}"] = v
        for k, v in typography.items():
            design_tokens[f"typography-{k.replace('_', '-')}"] = v

    # ── S3 specialist docs (games etc.): carry key doc keys only ──
    specialist = s3.get("specialist") or {}
    # Keep only first 600 chars of each specialist doc (cost-conscious)
    specialist_summary = {
        k: (str(v)[:600] + "…" if len(str(v)) > 600 else str(v))
        for k, v in specialist.items()
    }

    ctx = PipelineContext(
        # S0
        app_name            = s0.get("app_name") or s2.get("app_name") or state.project_id,
        app_description     = s0.get("app_description") or s2.get("app_description") or "",
        app_category        = s0.get("app_category") or s2.get("app_category") or "general",
        market              = s0.get("market", "ksa"),
        target_platforms    = (
            s0.get("target_platforms")
            or s2.get("target_platforms")
            or ["ios", "android"]
        ),
        features_must       = s0.get("features_must") or [],
        features_nice       = s0.get("features_nice") or [],
        estimated_complexity= s0.get("estimated_complexity", "medium"),
        has_payments        = bool(s0.get("has_payments") or s2.get("payment_mode") not in (None, "NONE")),
        has_realtime        = bool(s0.get("has_realtime") or s2.get("services", {}).get("realtime")),
        has_location        = bool(s0.get("has_location")),
        has_notifications   = bool(s0.get("has_notifications")),
        has_user_accounts   = bool(s0.get("has_user_accounts", True)),

        # S1
        blocked_features    = s1.get("blocked_features") or s2.get("blocked_features") or [],
        required_consents   = s1.get("required_consents") or [],
        data_classification = s1.get("data_classification") or s2.get("legal_classification") or "internal",
        risk_level          = s1.get("risk_level") or s1.get("overall_risk", "MEDIUM"),
        payment_mode        = s1.get("payment_mode") or s2.get("payment_mode") or "SANDBOX",
        pdpl_obligations    = s1.get("pdpl_obligations") or [],
        compliance_matrix   = s1.get("compliance_matrix") or s2.get("compliance_matrix") or [],
        inapp_texts         = s1.get("inapp_texts") or {},
        required_legal_docs = s1.get("required_legal_docs") or s2.get("required_legal_docs") or [],
        legal_classification= s1.get("data_classification") or s2.get("legal_classification") or "internal",

        # S2
        selected_stack      = s2.get("selected_stack", "flutterflow"),
        screens             = s2.get("screens") or [],
        data_model          = s2.get("data_model") or [],
        api_endpoints       = s2.get("api_endpoints") or [],
        auth_method         = s2.get("auth_method", "email"),
        services            = s2.get("services") or {},
        env_vars_spec       = s2.get("env_vars") or {},
        data_residency      = s2.get("data_residency", "KSA"),
        business_model      = s2.get("business_model", "general"),
        compliance_artifacts= s2.get("compliance_artifacts") or [],
        brand_assets        = s2.get("brand_assets") or {},
        ieee_docs_summary   = ieee_summary,
        ieee_doc_count      = s2.get("ieee_doc_count", len(ieee_summary)),
        design_system       = s2.get("design_system") or s3_vibe.get("design_system", "material3"),
        color_palette       = palette,
        typography          = typography,

        # S3
        project_type        = s3.get("project_type", "standard_app"),
        design_tokens       = design_tokens,
        mockup_paths        = s3.get("mockup_paths") or [],
        platform_assets     = s3.get("platform_assets") or {},
        specialist_docs     = specialist_summary,
        visual_style        = s3.get("visual_style") or s3_vibe.get("visual_style", "minimal"),
        layout_patterns     = s3_vibe.get("layout_patterns") or ["cards", "bottom_nav"],
    )

    logger.info(
        f"Pipeline context built: "
        f"platforms={ctx.target_platforms}, "
        f"screens={len(ctx.screens)}, "
        f"blocked={len(ctx.blocked_features)}, "
        f"consents={len(ctx.required_consents)}, "
        f"ieee_docs={ctx.ieee_doc_count}, "
        f"payment_mode={ctx.payment_mode}, "
        f"risk={ctx.risk_level}"
    )
    return ctx


def _build_constraint_block(ctx: PipelineContext) -> str:
    """Render the full constraint envelope as a prompt injection block.

    This is the single source of truth injected into EVERY codegen prompt.
    The Engineer reads this before writing any file.
    """
    lines: list[str] = [
        "═══════════════════════════════════════════════════",
        "  PIPELINE CONSTRAINT ENVELOPE — READ BEFORE CODING",
        "═══════════════════════════════════════════════════",
        "",
        f"App: {ctx.app_name} | Category: {ctx.app_category}",
        f"Stack: {ctx.selected_stack} | Design system: {ctx.design_system}",
        f"Platforms: {ctx.target_platforms}",
        f"Market: {ctx.market.upper()} | Data residency: {ctx.data_residency}",
        f"Payment mode: {ctx.payment_mode} (use test keys if SANDBOX)",
        f"Risk level: {ctx.risk_level}",
        f"Auth: {ctx.auth_method}",
        "",
    ]

    # Blocked features — hard constraint
    if ctx.blocked_features:
        lines.append("🚫 BLOCKED FEATURES — MUST NOT implement:")
        for f in ctx.blocked_features[:8]:
            lines.append(f"   • {f}")
        lines.append("")

    # Required consents — must appear in code
    if ctx.required_consents:
        lines.append("✅ REQUIRED CONSENT SCREENS — MUST implement:")
        for c in ctx.required_consents[:6]:
            lines.append(f"   • {c}")
        lines.append("")

    # PDPL obligations
    if ctx.pdpl_obligations:
        lines.append("⚖️  PDPL OBLIGATIONS (wire into data layer):")
        for p in ctx.pdpl_obligations[:4]:
            lines.append(f"   • {p}")
        lines.append("")

    # In-app legal texts
    if ctx.inapp_texts:
        lines.append("📜 IN-APP LEGAL TEXTS (use exact strings from S1):")
        for k, v in list(ctx.inapp_texts.items())[:5]:
            lines.append(f"   {k}: {str(v)[:120]}")
        lines.append("")

    # Services (backend)
    if ctx.services:
        lines.append(f"🔧 Services: {ctx.services}")

    # Key features
    if ctx.features_must:
        lines.append(f"⭐ Must-have features: {ctx.features_must[:10]}")
    if ctx.features_nice:
        lines.append(f"✨ Nice-to-have features: {ctx.features_nice[:6]}")

    # Capability flags
    flags = []
    if ctx.has_payments:
        flags.append(f"payments({'SANDBOX' if ctx.payment_mode == 'SANDBOX' else 'LIVE'})")
    if ctx.has_realtime:
        flags.append("realtime")
    if ctx.has_location:
        flags.append("location")
    if ctx.has_notifications:
        flags.append("push-notifications")
    if flags:
        lines.append(f"🏷  Capabilities: {', '.join(flags)}")

    # Design tokens summary
    if ctx.color_palette:
        primary = ctx.color_palette.get("primary", "#1976D2")
        secondary = ctx.color_palette.get("secondary", "#FF9800")
        lines.append(f"🎨 Colors: primary={primary}, secondary={secondary}")
    if ctx.typography:
        lines.append(f"🔤 Typography: {ctx.typography}")
    if ctx.visual_style:
        lines.append(f"🖼  Visual style: {ctx.visual_style} | "
                     f"Layout: {ctx.layout_patterns}")

    # Screens
    lines.append(f"\n📱 Screens ({len(ctx.screens)}):")
    for s in ctx.screens[:10]:
        lines.append(f"   • {s.get('name')} — {s.get('purpose', '')[:60]}")

    # API endpoints
    if ctx.api_endpoints:
        lines.append(f"\n🌐 API Endpoints ({len(ctx.api_endpoints)}):")
        for ep in ctx.api_endpoints[:8]:
            lines.append(f"   {ep.get('method','GET')} {ep.get('path','/')} — {ep.get('purpose','')[:50]}")

    # Data model
    if ctx.data_model:
        lines.append(f"\n🗄  Data Model ({len(ctx.data_model)} collections):")
        for c in ctx.data_model[:6]:
            fields = [f['name'] for f in c.get('fields', [])[:5]]
            lines.append(f"   {c.get('collection')}: {fields}")

    # Brand assets
    if ctx.brand_assets.get("logo_path"):
        lines.append(f"\n🖼  Logo: {ctx.brand_assets['logo_path']}")
    if ctx.brand_assets.get("splash_path"):
        lines.append(f"💫 Splash: {ctx.brand_assets['splash_path']}")

    # IEEE docs
    if ctx.ieee_docs_summary:
        lines.append(f"\n📐 IEEE Blueprint docs available ({ctx.ieee_doc_count}):")
        for doc_id in list(ctx.ieee_docs_summary.keys())[:6]:
            lines.append(f"   • {doc_id}")

    # S3 Mockups
    if ctx.mockup_paths:
        lines.append(f"\n📋 Wireframe mockups: {len(ctx.mockup_paths)} screens at:")
        for p in ctx.mockup_paths[:3]:
            lines.append(f"   {p}")

    # Specialist docs (games etc.)
    if ctx.specialist_docs:
        lines.append(f"\n🎮 Specialist design docs: {list(ctx.specialist_docs.keys())}")

    lines.append("")
    lines.append("═══════════════════════════════════════════════════")
    return "\n".join(lines)


def _build_ieee_context(ctx: PipelineContext) -> str:
    """Inject the most relevant IEEE doc sections into the prompt.

    Prioritises: api_spec, data_model, security_arch, srs, sad.
    """
    if not ctx.ieee_docs_summary:
        return ""

    priority_docs = ["api_spec", "data_model", "security_arch", "srs", "sad"]
    lines = ["\n── IEEE Blueprint Extracts (authoritative spec) ──"]
    injected = 0
    for doc_id in priority_docs:
        if doc_id in ctx.ieee_docs_summary:
            snippet = ctx.ieee_docs_summary[doc_id][:500]
            lines.append(f"\n[{doc_id.upper()}]\n{snippet}")
            injected += 1
            if injected >= 3:
                break

    return "\n".join(lines) if injected else ""


# ═══════════════════════════════════════════════════════════════════
# Drift Validation — Scout checks generated files against blueprint
# ═══════════════════════════════════════════════════════════════════


async def _validate_no_drift(
    state: PipelineState,
    files: dict[str, str],
    ctx: PipelineContext,
) -> dict:
    """Scout validates that generated code does not drift from the blueprint.

    Checks:
    1. All required screens have corresponding files
    2. Blocked features are NOT present in generated code
    3. Consent screens exist (if required_consents is non-empty)
    4. Payment mode is respected (no live keys in SANDBOX mode)
    5. All must-have features are addressed

    Returns a dict with drift_found (bool), issues (list), and a fix summary.
    """
    screen_names  = [s.get("name", "") for s in ctx.screens]
    file_paths    = list(files.keys())
    # Sample of code content for Scout review (first 300 chars of each file)
    code_sample   = {
        p: c[:300] for p, c in list(files.items())[:25]
        if isinstance(c, str)
    }

    verdict = await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"Validate that this generated codebase aligns with its blueprint.\n\n"
            f"BLUEPRINT REQUIREMENTS:\n"
            f"  Required screens: {screen_names}\n"
            f"  Must-have features: {ctx.features_must[:10]}\n"
            f"  BLOCKED features (must NOT appear): {ctx.blocked_features}\n"
            f"  Required consents: {ctx.required_consents}\n"
            f"  Payment mode: {ctx.payment_mode} "
            f"({'test/sandbox keys only' if ctx.payment_mode == 'SANDBOX' else 'live keys allowed'})\n"
            f"  Auth method: {ctx.auth_method}\n"
            f"  Target platforms: {ctx.target_platforms}\n\n"
            f"GENERATED FILES ({len(file_paths)} total):\n"
            f"{file_paths[:40]}\n\n"
            f"CODE SAMPLE (first 300 chars of up to 25 files):\n"
            f"{json.dumps(code_sample, indent=2)[:5000]}\n\n"
            f"Return ONLY a JSON object:\n"
            f'{{\n'
            f'  "drift_found": true/false,\n'
            f'  "missing_screens": ["screen_name"],\n'
            f'  "blocked_feature_violations": ["feature_name"],\n'
            f'  "missing_consents": ["consent_name"],\n'
            f'  "payment_mode_violations": ["file_path: description"],\n'
            f'  "missing_features": ["feature_name"],\n'
            f'  "severity": "LOW|MEDIUM|HIGH",\n'
            f'  "summary": "one sentence"\n'
            f'}}'
        ),
        state=state,
        action="general",
    )

    try:
        start = verdict.find("{")
        end   = verdict.rfind("}") + 1
        result = json.loads(verdict[start:end]) if start >= 0 else {}
    except (json.JSONDecodeError, TypeError):
        result = {}

    drift_found = result.get("drift_found", False)

    if drift_found:
        severity = result.get("severity", "MEDIUM")
        summary  = result.get("summary", "Drift detected")
        logger.warning(
            f"[{state.project_id}] Blueprint drift detected [{severity}]: {summary}"
        )

        # Notify operator if HIGH severity
        if severity == "HIGH":
            try:
                from factory.telegram.notifications import notify_operator
                from factory.core.state import NotificationType
                await notify_operator(
                    state,
                    NotificationType.WARNING,
                    f"⚠️ *Blueprint drift detected in generated code*\n"
                    f"Severity: {severity}\n{summary}\n\n"
                    f"Missing screens: {result.get('missing_screens', [])}\n"
                    f"Violations: {result.get('blocked_feature_violations', [])}",
                )
            except Exception:
                pass

        # Store drift in state errors
        state.errors.append({
            "stage": "S4_CODEGEN",
            "type": "blueprint_drift",
            "severity": severity,
            "details": result,
        })
    else:
        logger.info(f"[{state.project_id}] Blueprint drift check: PASS — no drift detected")

    return result


# ═══════════════════════════════════════════════════════════════════
# Design Token & Legal Text Injection
# ═══════════════════════════════════════════════════════════════════


def _extract_design_tokens(state: PipelineState) -> dict:
    """Extract design tokens from S3 output for injection into codegen.

    Returns a flat dict of token-name → value.
    """
    s3 = state.s3_output or {}
    vibe = s3.get("vibe") or s3.get("design_system") or {}
    palette = vibe.get("color_palette") or s3.get("color_palette") or {}
    typography = vibe.get("typography") or s3.get("typography") or {}
    spacing = vibe.get("spacing") or s3.get("spacing") or {}

    tokens: dict = {}
    for k, v in palette.items():
        tokens[f"color-{k.replace('_', '-')}"] = v
    for k, v in typography.items():
        tokens[f"typography-{k.replace('_', '-')}"] = v
    for k, v in spacing.items():
        tokens[f"spacing-{k.replace('_', '-')}"] = v

    tokens["visual-style"]   = vibe.get("visual_style", "minimal")
    tokens["design-system"]  = vibe.get("design_system", "material3")
    tokens["layout-patterns"] = str(vibe.get("layout_patterns", ["cards", "bottom_nav"]))
    return tokens


def _build_token_injection(tokens: dict) -> str:
    """Format design tokens as a prompt injection block."""
    if not tokens:
        return ""
    lines = ["Design tokens from S3 (MUST be used in generated code):"]
    for k, v in list(tokens.items())[:30]:
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _extract_legal_texts(state: PipelineState) -> dict:
    """Extract in-app legal texts from S1 output for injection into codegen."""
    s1 = state.s1_output or {}
    return s1.get("inapp_texts") or {}


def _build_legal_injection(legal_texts: dict) -> str:
    """Format legal texts as a prompt injection block."""
    if not legal_texts:
        return ""
    lines = [
        "In-app legal texts from S1 (MUST be embedded in relevant screens/components):",
    ]
    for k, v in legal_texts.items():
        lines.append(f"  {k}: {str(v)[:200]}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Per-Screen 100+ File Expansion
# ═══════════════════════════════════════════════════════════════════


async def _expand_to_100_files(
    state: PipelineState,
    files: dict[str, str],
    stack: TechStack,
    blueprint_data: dict,
    design_tokens: dict,
    legal_texts: dict,
    tech_items: list,
    ctx: "Optional[PipelineContext]" = None,
) -> dict[str, str]:
    """Expand generated files to 100+ by generating per-screen code + support files.

    Spec: v5.8 §4.4 Phase 1.5

    Generates for each screen not already in files:
      - Full screen/view/activity file
      - Corresponding ViewModel/Store/State file
      - Test stub file

    Also generates:
      - Design tokens file (constants/theme)
      - Legal texts constants file
      - Environment config template
      - Implementation guide for NOT_AUTOMATABLE tech

    ctx (PipelineContext): when provided, per-screen prompts also include the
    constraint envelope so each file stays aligned with S0→S3 decisions.
    """
    # Prefer pipeline context values when available
    screens    = (ctx.screens if ctx else None) or blueprint_data.get("screens", [])
    app_name   = (ctx.app_name if ctx else None) or blueprint_data.get("app_name", state.project_id)
    data_model = (ctx.data_model if ctx else None) or blueprint_data.get("data_model", [])
    auth       = (ctx.auth_method if ctx else None) or blueprint_data.get("auth_method", "email")
    token_ctx  = _build_token_injection(design_tokens)
    legal_ctx  = _build_legal_injection(legal_texts)

    # Build a mini constraint summary for per-screen prompts
    per_screen_constraints = ""
    if ctx:
        per_screen_constraints = (
            f"Constraints from blueprint:\n"
            f"  Payment mode: {ctx.payment_mode} "
            f"({'use test/sandbox keys' if ctx.payment_mode == 'SANDBOX' else 'live keys allowed'})\n"
            f"  Data residency: {ctx.data_residency}\n"
            f"  Blocked features (must NOT appear): {ctx.blocked_features}\n"
            f"  Required consents to wire: {ctx.required_consents}\n"
            f"  Risk level: {ctx.risk_level}\n"
            f"  Project type: {ctx.project_type}\n"
        )

    new_files: dict[str, str] = {}

    # ── Per-screen file generation ──
    for screen in screens[:15]:
        sname      = screen.get("name", "Screen")
        spurpose   = screen.get("purpose", "")
        scomponents= screen.get("components", [])
        sbindings  = screen.get("data_bindings", [])

        # Determine target file paths per stack
        if stack == TechStack.FLUTTERFLOW:
            slug    = sname.lower().replace(" ", "_")
            screen_path = f"lib/screens/{slug}_screen.dart"
            vm_path     = f"lib/viewmodels/{slug}_viewmodel.dart"
            test_path   = f"test/{slug}_screen_test.dart"
        elif stack == TechStack.REACT_NATIVE:
            slug    = sname.replace(" ", "")
            screen_path = f"src/screens/{slug}Screen.tsx"
            vm_path     = f"src/store/{slug.lower()}Store.ts"
            test_path   = f"src/__tests__/{slug}Screen.test.tsx"
        elif stack == TechStack.SWIFT:
            slug    = sname.replace(" ", "")
            screen_path = f"Sources/Views/{slug}View.swift"
            vm_path     = f"Sources/ViewModels/{slug}ViewModel.swift"
            test_path   = f"Tests/{slug}ViewTests.swift"
        elif stack == TechStack.KOTLIN:
            slug    = sname.replace(" ", "")
            package = blueprint_data.get("package_name", "com.factory.app").replace(".", "/")
            screen_path = f"app/src/main/java/{package}/ui/{slug.lower()}/{slug}Fragment.kt"
            vm_path     = f"app/src/main/java/{package}/ui/{slug.lower()}/{slug}ViewModel.kt"
            test_path   = f"app/src/test/java/{package}/ui/{slug.lower()}/{slug}ViewModelTest.kt"
        elif stack == TechStack.UNITY:
            slug    = sname.replace(" ", "")
            screen_path = f"Assets/Scripts/UI/{slug}UIController.cs"
            vm_path     = f"Assets/Scripts/Data/{slug}Data.cs"
            test_path   = f"Assets/Tests/{slug}Tests.cs"
        elif stack == TechStack.PYTHON_BACKEND:
            slug    = sname.lower().replace(" ", "_")
            screen_path = f"routers/{slug}.py"
            vm_path     = f"services/{slug}_service.py"
            test_path   = f"tests/test_{slug}.py"
        else:
            continue

        # Skip if already generated
        if screen_path in files:
            continue

        screen_code = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Write the complete {stack.value} file for screen '{sname}'.\n\n"
                f"File path: {screen_path}\n"
                f"App: {app_name}\n"
                f"Purpose: {spurpose}\n"
                f"Components: {scomponents}\n"
                f"Data bindings: {[b.get('collection') for b in sbindings[:5]]}\n"
                f"Auth method: {auth}\n\n"
                f"{per_screen_constraints}\n"
                f"{token_ctx}\n\n"
                f"{legal_ctx}\n\n"
                f"Requirements:\n"
                f"- Production-quality, complete implementation\n"
                f"- Apply design tokens for all colors, fonts, spacing\n"
                f"- Include state management (loading, error, empty states)\n"
                f"- Proper null safety / type safety\n"
                f"- Import all needed packages\n"
                f"- NEVER implement blocked features listed above\n"
                f"- Wire required consent texts where this screen collects data\n\n"
                f"Return ONLY the raw file content — no markdown fences, no explanation."
            ),
            state=state,
            action="write_code",
        )
        new_files[screen_path] = _strip_fences(screen_code)

        # ViewModel/Store/Service
        if vm_path not in files:
            vm_code = await call_ai(
                role=AIRole.ENGINEER,
                prompt=(
                    f"Write the {stack.value} ViewModel/Store/Service for '{sname}' screen.\n\n"
                    f"File path: {vm_path}\n"
                    f"App: {app_name}\n"
                    f"Data collections used: {[b.get('collection') for b in sbindings[:5]]}\n"
                    f"Auth method: {auth}\n\n"
                    f"Include: state fields, async data loading, error handling, "
                    f"CRUD operations for the data bindings.\n"
                    f"Return ONLY the raw file content — no markdown, no fences."
                ),
                state=state,
                action="write_code",
            )
            new_files[vm_path] = _strip_fences(vm_code)

        # Test stub (quick, no AI needed for stub)
        if test_path not in files:
            new_files[test_path] = _generate_test_stub(
                stack, sname, screen_path, vm_path, app_name,
            )

    # ── Design tokens constants file ──
    if design_tokens:
        tokens_file = await call_ai(
            role=AIRole.ENGINEER,
            prompt=(
                f"Generate a design tokens constants file for {stack.value}.\n\n"
                f"Tokens:\n{json.dumps(design_tokens, indent=2)[:3000]}\n\n"
                f"Requirements:\n"
                f"- Use the appropriate format for {stack.value}\n"
                f"- Flutter: lib/constants/design_tokens.dart (const Color, TextStyle, etc.)\n"
                f"- React Native: src/theme/tokens.ts (exported const object)\n"
                f"- Swift: Sources/Design/DesignTokens.swift (UIColor extension)\n"
                f"- Kotlin: app/.../ui/theme/DesignTokens.kt (object with Color)\n"
                f"- Unity: Assets/Scripts/UI/DesignTokens.cs (static class)\n"
                f"- Python: No design tokens (backend only)\n\n"
                f"Return ONLY the raw file content."
            ),
            state=state,
            action="write_code",
        )
        token_file_path = {
            TechStack.FLUTTERFLOW:    "lib/constants/design_tokens.dart",
            TechStack.REACT_NATIVE:   "src/theme/tokens.ts",
            TechStack.SWIFT:          "Sources/Design/DesignTokens.swift",
            TechStack.KOTLIN:         "app/src/main/java/com/factory/app/ui/theme/DesignTokens.kt",
            TechStack.UNITY:          "Assets/Scripts/UI/DesignTokens.cs",
            TechStack.PYTHON_BACKEND: None,
        }.get(stack)
        if token_file_path:
            new_files[token_file_path] = _strip_fences(tokens_file)

    # ── Legal texts constants file ──
    if legal_texts:
        legal_const_path = {
            TechStack.FLUTTERFLOW:    "lib/constants/legal_texts.dart",
            TechStack.REACT_NATIVE:   "src/constants/legalTexts.ts",
            TechStack.SWIFT:          "Sources/Constants/LegalTexts.swift",
            TechStack.KOTLIN:         "app/src/main/java/com/factory/app/constants/LegalTexts.kt",
            TechStack.UNITY:          "Assets/Scripts/Constants/LegalTexts.cs",
            TechStack.PYTHON_BACKEND: "constants/legal_texts.py",
        }.get(stack)
        if legal_const_path and legal_const_path not in files:
            legal_code = await call_ai(
                role=AIRole.ENGINEER,
                prompt=(
                    f"Generate a legal texts constants file for {stack.value}.\n\n"
                    f"Legal texts:\n{json.dumps(legal_texts, indent=2)[:2000]}\n\n"
                    f"Return ONLY the raw file content — constants for all the texts listed."
                ),
                state=state,
                action="write_code",
            )
            new_files[legal_const_path] = _strip_fences(legal_code)

    # ── Environment config template ──
    env_vars_needed = {}
    for item in tech_items:
        for var in item.env_vars:
            env_vars_needed[var] = f"# {item.name} — {item.why_needed}"

    if env_vars_needed:
        env_example = "\n".join(
            f"{var}=  {comment}" for var, comment in env_vars_needed.items()
        )
        new_files[".env.example"] = (
            f"# Environment variables for {app_name}\n"
            f"# Generated by AI Factory Pipeline v5.8\n"
            f"# Copy to .env and fill in your values\n\n"
            + env_example + "\n"
        )

    # ── Implementation guide for NOT_AUTOMATABLE tech ──
    not_auto = [i for i in tech_items if i.capability == AutomationLevel.NOT_AUTOMATABLE]
    if not_auto:
        guide_content = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=(
                f"Write a detailed implementation guide for components that require "
                f"manual implementation for '{app_name}'.\n\n"
                f"Components:\n"
                + "\n".join(f"- {i.name}: {i.why_needed}" for i in not_auto) +
                f"\n\nFor each:\n"
                f"1. Exact steps to implement\n"
                f"2. How AI can assist (generate configs, scaffold, test)\n"
                f"3. How to test and validate\n"
                f"4. Integration points with the generated code\n\n"
                f"Return professional Markdown."
            ),
            state=state,
            action="plan_architecture",
        )
        new_files["docs/MANUAL_IMPLEMENTATION_GUIDE.md"] = guide_content

    # ── Data model files ──
    for collection in data_model[:8]:
        cname = collection.get("collection", "item").replace(" ", "_").lower()
        cfields = collection.get("fields", [])
        model_path = {
            TechStack.FLUTTERFLOW:    f"lib/models/{cname}.dart",
            TechStack.REACT_NATIVE:   f"src/types/{cname}.ts",
            TechStack.SWIFT:          f"Sources/Models/{cname.title()}.swift",
            TechStack.KOTLIN:         f"app/src/main/java/com/factory/app/data/models/{cname.title()}.kt",
            TechStack.UNITY:          f"Assets/Scripts/Data/{cname.title()}Data.cs",
            TechStack.PYTHON_BACKEND: f"models/{cname}.py",
        }.get(stack)
        if model_path and model_path not in files and model_path not in new_files:
            model_code = await call_ai(
                role=AIRole.ENGINEER,
                prompt=(
                    f"Write the {stack.value} model/type for '{cname}'.\n\n"
                    f"Fields: {json.dumps(cfields, indent=2)[:1000]}\n\n"
                    f"Requirements:\n"
                    f"- Include toJson/fromJson (or Codable, or Serializable)\n"
                    f"- Proper null safety\n"
                    f"- Timestamp fields as DateTime/Date/Timestamp\n\n"
                    f"Return ONLY the raw file content."
                ),
                state=state,
                action="write_code",
            )
            new_files[model_path] = _strip_fences(model_code)

    # ── README ──
    if "README.md" not in files and "README.md" not in new_files:
        wired_names = [i.name for i in tech_items if i.wired]
        new_files["README.md"] = (
            f"# {app_name}\n\n"
            f"Generated by AI Factory Pipeline v5.8\n\n"
            f"## Tech Stack\n"
            f"- Framework: {stack.value}\n"
            f"- Services: {', '.join(wired_names[:8])}\n\n"
            f"## Setup\n\n"
            f"1. Copy `.env.example` to `.env` and fill in your API keys\n"
            f"2. Install dependencies (see stack-specific instructions below)\n"
            f"3. Run the app\n\n"
            f"## Environment Variables\n\n"
            f"See `.env.example` for all required variables.\n\n"
            f"## Manual Steps\n\n"
            f"See `docs/MANUAL_IMPLEMENTATION_GUIDE.md` for components requiring manual setup.\n"
        )

    merged = {**files, **new_files}
    logger.info(
        f"[{state.project_id}] File expansion: {len(files)} → {len(merged)} files "
        f"(+{len(new_files)} new)"
    )
    return merged


def _generate_test_stub(
    stack: TechStack,
    screen_name: str,
    screen_path: str,
    vm_path: str,
    app_name: str,
) -> str:
    """Generate a minimal test stub for a screen without an AI call."""
    slug = screen_name.replace(" ", "")
    if stack == TechStack.FLUTTERFLOW:
        return (
            f"// Test for {screen_name} — {app_name}\n"
            f"import 'package:flutter_test/flutter_test.dart';\n"
            f"import '../{screen_path}';\n\n"
            f"void main() {{\n"
            f"  group('{screen_name}', () {{\n"
            f"    testWidgets('renders without error', (tester) async {{\n"
            f"      // TODO: add widget test\n"
            f"    }});\n"
            f"  }});\n"
            f"}}\n"
        )
    elif stack == TechStack.REACT_NATIVE:
        return (
            f"// Test for {screen_name} — {app_name}\n"
            f"import React from 'react';\n"
            f"import {{ render }} from '@testing-library/react-native';\n"
            f"import {slug}Screen from '../../screens/{slug}Screen';\n\n"
            f"describe('{screen_name}', () => {{\n"
            f"  it('renders correctly', () => {{\n"
            f"    // TODO: add test\n"
            f"  }});\n"
            f"}});\n"
        )
    elif stack == TechStack.SWIFT:
        return (
            f"// Test for {screen_name} — {app_name}\n"
            f"import XCTest\n"
            f"@testable import App\n\n"
            f"final class {slug}ViewTests: XCTestCase {{\n"
            f"    func test{slug}ViewExists() throws {{\n"
            f"        // TODO: add SwiftUI snapshot test\n"
            f"    }}\n"
            f"}}\n"
        )
    elif stack == TechStack.KOTLIN:
        return (
            f"// Test for {screen_name} — {app_name}\n"
            f"import org.junit.Test\n\n"
            f"class {slug}ViewModelTest {{\n"
            f"    @Test\n"
            f"    fun `initial state is loading`() {{\n"
            f"        // TODO: add ViewModel unit test\n"
            f"    }}\n"
            f"}}\n"
        )
    elif stack == TechStack.PYTHON_BACKEND:
        slug_lower = screen_name.lower().replace(" ", "_")
        return (
            f"# Test for {screen_name} — {app_name}\n"
            f"import pytest\n"
            f"from httpx import AsyncClient\n"
            f"from main import app\n\n"
            f"@pytest.mark.anyio\n"
            f"async def test_{slug_lower}_endpoint():\n"
            f"    async with AsyncClient(app=app, base_url='http://test') as ac:\n"
            f"        # TODO: add endpoint test\n"
            f"        pass\n"
        )
    return f"// Test stub for {screen_name}\n// TODO: implement tests\n"


# ═══════════════════════════════════════════════════════════════════
# Mother Memory — CodeGen Nodes
# ═══════════════════════════════════════════════════════════════════


async def _write_codegen_to_mother_memory(
    state: PipelineState,
    files: dict,
    stack: TechStack,
    tech_items: list,
) -> None:
    """Write codegen decisions to Mother Memory.

    Stores: tech_stack_final, file_count, wired_services.
    """
    try:
        from factory.memory.mother_memory import store_pipeline_decision

        wired   = [i.name for i in tech_items if i.wired]
        skipped = [i.name for i in tech_items if i.skip]

        await store_pipeline_decision(
            project_id=state.project_id,
            stage="s4_codegen",
            decision_type="tech_stack_final",
            content=(
                f"Stack: {stack.value} | "
                f"Total files: {len(files)} | "
                f"Wired services: {wired[:8]} | "
                f"Skipped: {skipped[:4]}"
            ),
            operator_id=str(state.operator_id),
        )

        file_categories: dict[str, int] = {}
        for path in files:
            ext = Path(path).suffix or "other"
            file_categories[ext] = file_categories.get(ext, 0) + 1

        await store_pipeline_decision(
            project_id=state.project_id,
            stage="s4_codegen",
            decision_type="file_inventory",
            content=(
                f"File count: {len(files)} | "
                f"By extension: {dict(list(file_categories.items())[:8])}"
            ),
            operator_id=str(state.operator_id),
        )

        logger.info(
            f"[{state.project_id}] S4 → Mother Memory: codegen nodes stored"
        )
    except Exception as e:
        logger.warning(
            f"[{state.project_id}] S4 Mother Memory write failed (non-fatal): {e}"
        )


# ═══════════════════════════════════════════════════════════════════
# §4.4 S4 CodeGen Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S4_CODEGEN)
async def s4_codegen_node(state: PipelineState) -> PipelineState:
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

    # Retry when: retry_count > 0 with prior failures, or previous_stage was S6_TEST
    s5_has_failures = bool(
        state.s6_output and not state.s6_output.get("passed", True)
        and state.s6_output.get("failures")
    )
    is_retry = (
        state.retry_count > 0 and s5_has_failures
    ) or state.previous_stage == Stage.S6_TEST

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
    ctx: "Optional[PipelineContext]" = None,
) -> str:
    """Build a stack-specific, detailed codegen prompt for the Engineer.

    Each stack gets targeted instructions for conventions, file structure,
    and must-have patterns — reducing hallucinations and improving output quality.

    When ctx is provided (Phase 6+), the full constraint envelope is prepended
    so the Engineer never drifts from S0→S3 decisions.
    """
    screens_json = json.dumps(screens[:10], indent=2)[:2500]
    model_json = json.dumps(data_model, indent=2)[:1800]
    api_json = json.dumps(api_endpoints, indent=2)[:1200]
    colors = json.dumps(
        (ctx.color_palette if ctx else None)
        or blueprint_data.get("color_palette", {})
    )
    typography = (ctx.typography if ctx else None) or blueprint_data.get("typography", {})
    features = (ctx.features_must if ctx else None) or blueprint_data.get("features_must", [])

    # Build constraint envelope from full pipeline context
    constraint_block = _build_constraint_block(ctx) if ctx else ""
    ieee_block       = _build_ieee_context(ctx) if ctx else ""

    base = (
        f"{constraint_block}\n\n"
        f"{ieee_block}\n\n"
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
        f"IMPORTANT: Do NOT implement any BLOCKED FEATURES listed in the constraint envelope above.\n"
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
    Phase 0:   Tech inventory — discover, check wired, Scout-verify, classify
    Phase 0.5: Operator Telegram wiring requests for unwired tech
    Phase 1:   Generate code files (enriched with design tokens + legal texts)
    Phase 1.5: Per-screen expansion to 100+ files
    Phase 2:   Security rules
    Phase 3:   CI/CD configuration
    Phase 4:   Quick Fix validation
    Phase 5:   Mother Memory codegen nodes
    """
    stack_value = blueprint_data.get("selected_stack", "flutterflow")
    try:
        stack = TechStack(stack_value)
    except ValueError:
        stack = TechStack.FLUTTERFLOW

    screens       = blueprint_data.get("screens", [])
    data_model    = blueprint_data.get("data_model", [])
    api_endpoints = blueprint_data.get("api_endpoints", [])
    auth_method   = blueprint_data.get("auth_method", "email")
    app_name      = blueprint_data.get("app_name", state.project_id)
    requirements  = state.s0_output or {}

    # ── Build full pipeline context (S0→S1→S2→S3 constraint envelope) ──
    ctx = _build_full_pipeline_context(state, blueprint_data)

    # ── Phase 0: Tech Inventory ──
    tech_items = await _run_tech_inventory(state, blueprint_data, requirements)

    # ── Phase 0.5: Handle Unwired Tech (Telegram operator interaction) ──
    tech_items = await _handle_unwired_tech(state, tech_items)

    # Send summary before starting generation
    await _generate_tech_summary_message(state, tech_items)

    # ── Design tokens and legal texts come from the pipeline context ──
    design_tokens = ctx.design_tokens
    legal_texts   = ctx.inapp_texts
    token_injection = _build_token_injection(design_tokens)
    legal_injection = _build_legal_injection(legal_texts)

    # ── Phase 1: Generate code files ──
    from factory.core.stage_enrichment import enrich_prompt

    # Build wired services context for the Engineer
    wired_services   = [i.name for i in tech_items if i.wired and i.category != "framework"]
    skipped_services = [i.name for i in tech_items if i.skip]
    tech_context = (
        f"Wired services (use these, credentials available): {wired_services[:10]}\n"
        f"Skipped services (generate TODO stubs for these): {skipped_services[:5]}\n"
    )

    code_prompt = _build_codegen_prompt(
        stack=stack,
        app_name=app_name,
        screens=screens,
        data_model=data_model,
        api_endpoints=api_endpoints,
        auth_method=auth_method,
        blueprint_data=blueprint_data,
        ctx=ctx,                           # ← full constraint envelope injected
    )
    # Append tech context + any additional token/legal text not already in ctx block
    code_prompt = (
        code_prompt
        + f"\n\n{tech_context}"
        + (f"\n\n{token_injection}" if token_injection else "")
        + (f"\n\n{legal_injection}" if legal_injection else "")
    )
    code_prompt = await enrich_prompt(
        "s4_codegen", code_prompt, state,
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

    # ── Phase 4: Quick Fix validation pass ──
    files = await _quick_fix_validation(state, files, stack)

    # ── Phase 1.5: Per-screen expansion to 100+ files ──
    files = await _expand_to_100_files(
        state, files, stack, blueprint_data,
        design_tokens, legal_texts, tech_items,
        ctx=ctx,                           # ← pass ctx so per-screen code stays aligned
    )

    # ── Phase 1.6: Blueprint drift validation ──
    drift_result = await _validate_no_drift(state, files, ctx)
    drift_found  = drift_result.get("drift_found", False)

    # ── Phase 5: Mother Memory codegen nodes ──
    await _write_codegen_to_mother_memory(state, files, stack, tech_items)

    # ── Build tech inventory summary for state ──
    tech_summary = [
        {
            "id": i.id, "name": i.name, "category": i.category,
            "wired": i.wired, "skip": i.skip,
            "capability": i.capability.value,
            "cost_estimate": i.cost_estimate,
        }
        for i in tech_items
    ]

    state.s4_output = {
        "generated_files": files,
        "file_count": len(files),
        "stack": stack.value,
        "generation_mode": "full",
        "tech_inventory": tech_summary,
        "wired_services": [i.name for i in tech_items if i.wired],
        "skipped_services": [i.name for i in tech_items if i.skip],
        "design_tokens_injected": bool(design_tokens),
        "legal_texts_injected": bool(legal_texts),
        "blueprint_drift": {
            "checked": True,
            "drift_found": drift_found,
            "severity": drift_result.get("severity", "LOW"),
            "missing_screens": drift_result.get("missing_screens", []),
            "violations": drift_result.get("blocked_feature_violations", []),
        },
        # Pipeline context snapshot (key fields only — not full content)
        "pipeline_context": {
            "target_platforms": ctx.target_platforms,
            "blocked_features": ctx.blocked_features,
            "payment_mode": ctx.payment_mode,
            "data_residency": ctx.data_residency,
            "risk_level": ctx.risk_level,
            "ieee_doc_count": ctx.ieee_doc_count,
            "project_type": ctx.project_type,
        },
    }

    # ── Quality Gate (Issue 17) ──────────────────────────────────────
    # Skip gates in dry-run / test mode (DRY_RUN=true).
    if not os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes"):
        from factory.core.quality_gates import GateResult, raise_if_failed, QualityGateFailure
        from factory.core.halt import HaltCode, HaltReason, set_halt
        from factory.core.mode_router import MasterMode

        _gen_files: dict = (state.s4_output or {}).get("generated_files") or {}
        file_count = len(_gen_files)

        min_files = {
            MasterMode.BASIC: 10,
            MasterMode.BALANCED: 50,
            MasterMode.CUSTOM: 50,
            MasterMode.TURBO: 150,
        }.get(state.master_mode, 50)

        _gate_results = [
            GateResult(
                name="min_file_count",
                passed=file_count >= min_files,
                observed=file_count,
                required=min_files,
                message=f"Generated {file_count} files, need >={min_files}" if file_count < min_files else "",
            ),
        ]

        total_sloc = sum(
            len([ln for ln in content.splitlines() if ln.strip()])
            for content in _gen_files.values()
            if isinstance(content, str)
        )
        min_sloc = {
            MasterMode.BASIC: 200,
            MasterMode.BALANCED: 2000,
            MasterMode.CUSTOM: 2000,
            MasterMode.TURBO: 8000,
        }.get(state.master_mode, 2000)

        _gate_results.append(GateResult(
            name="min_sloc",
            passed=total_sloc >= min_sloc,
            observed=total_sloc,
            required=min_sloc,
            message=(
                f"Total SLOC {total_sloc} < {min_sloc} (skeleton output suspected)"
                if total_sloc < min_sloc else ""
            ),
        ))

        try:
            raise_if_failed(
                "S4_CODEGEN", _gate_results,
                recommended_action="retry S4_CODEGEN with higher model",
            )
        except QualityGateFailure as qgf:
            set_halt(state, HaltReason(
                code=HaltCode.QUALITY_GATE_FAILED,
                title="CodeGen failed quality gate",
                detail=qgf.format_for_telegram()[:600],
                stage="S4_CODEGEN",
                failing_gate="codegen_output",
                remediation_steps=["Retry CodeGen with /continue", "/cancel"],
            ))
            state.legal_halt = True
            return state

    # ── Commit to GitHub repo ──
    await _commit_to_github(state, files, app_name, stack)

    logger.info(
        f"[{state.project_id}] S4 CodeGen complete: "
        f"{len(files)} files, {len(tech_items)} tech items "
        f"({sum(1 for i in tech_items if i.wired)} wired), "
        f"stack={stack.value}"
    )
    return state


async def _commit_to_github(
    state: "PipelineState",
    files: dict,
    app_name: str,
    stack: "TechStack",
) -> None:
    """Create a GitHub repo and commit all generated files.

    Spec: §4.4 — commit to operator's GitHub account via GitHubClient.
    Non-fatal: pipeline continues even if GitHub is unavailable.
    """
    try:
        from factory.integrations.github import get_github
        import re as _re

        gh = get_github()
        if not gh.is_connected():
            logger.info(f"[{state.project_id}] S3: GitHub not connected — skipping commit")
            return

        # Sanitise repo name: lowercase, dashes only
        repo_name = _re.sub(r"[^a-z0-9-]", "-", app_name.lower())[:50].strip("-")
        repo_name = repo_name or f"factory-{state.project_id[:8]}"

        # Create repo (idempotent — skip if already exists)
        if not await gh.repo_exists(repo_name):
            await gh.create_repo(repo_name, private=True)
            logger.info(f"[{state.project_id}] S3: Created GitHub repo: {repo_name}")
        else:
            logger.info(f"[{state.project_id}] S3: GitHub repo exists: {repo_name}")

        # Commit all generated files in one batch
        commit_result = await gh.commit_files(
            repo=repo_name,
            files=files,
            message=(
                f"feat: initial generated code — AI Factory Pipeline v5.8\n\n"
                f"Stack: {stack.value}\n"
                f"Files: {len(files)}\n"
                f"Project: {state.project_id}"
            ),
        )

        state.s4_output["github_repo"] = repo_name
        state.s4_output["github_commit_count"] = commit_result.get("files", 0)
        state.project_metadata["github_repo"] = repo_name

        logger.info(
            f"[{state.project_id}] S3: Committed {commit_result.get('files', 0)} "
            f"files to github/{repo_name}"
        )

        from factory.telegram.notifications import send_telegram_message
        await send_telegram_message(
            state.operator_id,
            f"📦 {len(files)} files committed to GitHub repo: {repo_name}",
        )

    except Exception as e:
        logger.warning(f"[{state.project_id}] S3: GitHub commit failed (non-fatal): {e}")


# ═══════════════════════════════════════════════════════════════════
# Retry Fix Mode (from S5 test failures)
# ═══════════════════════════════════════════════════════════════════


async def _codegen_retry_fix(state: PipelineState) -> PipelineState:
    """Targeted fix mode when retrying from S5 test failures.

    Spec: §4.4 (retry path)
    Uses War Room escalation (L1→L2→L3) for each failure.
    """
    test_failures = (state.s6_output or {}).get("failures", [])
    existing_files = (state.s4_output or {}).get("generated_files", {})

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
                "stage": "S4_CODEGEN",
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

    state.s4_output["generated_files"] = existing_files
    state.s4_output["generation_mode"] = "retry_fix"
    state.s4_output["fixes_applied"] = fixed_count
    state.s4_output["unresolved"] = unresolved

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
                "stage": "S4_CODEGEN",
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
register_stage_node("s4_codegen", s4_codegen_node)


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
        state.s4_output = {
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
        state.s4_output = {
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
