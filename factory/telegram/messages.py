"""
AI Factory Pipeline v5.8 — Telegram Message Formatting

Implements:
  - §5.1 Message formatting and constants
  - §5.4 Notification templates
  - Telegram 4096 character limit enforcement

Spec Authority: v5.8 §5.1, §5.4
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from factory.core.state import (
    AutonomyMode,
    ExecutionMode,
    NotificationType,
    PHASE_BUDGET_LIMITS,
    PipelineState,
    Stage,
)

logger = logging.getLogger("factory.telegram.messages")


# ─── Issue 38: Markdown escape helper ─────────────────────────────────────────

def escape_md(text: str) -> str:
    """Escape all Telegram Markdown V1 special characters in *text*.

    Telegram Markdown V1 treats _ * ` [ as special. Any dynamic string
    (provider names, file paths, user input) passed with parse_mode='Markdown'
    must be escaped first.

    Usage:
        await bot.send_message(chat_id, escape_md(provider_name), parse_mode='Markdown')
    """
    # V1 special chars: _ * ` [
    for ch in ("\\", "_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text



# ═══════════════════════════════════════════════════════════════════
# §5.1 Telegram Configuration
# ═══════════════════════════════════════════════════════════════════

TELEGRAM_CONFIG: dict[str, Any] = {
    "bot_token": "from_gcp_secret_manager",
    "webhook_url": os.getenv(
        "TELEGRAM_WEBHOOK_URL",
        "https://factory-bot-XXXX.run.app/webhook",
    ),
    "allowed_operators": [],
    "max_message_length": 4096,
    "photo_max_size_mb": 10,
    "document_max_size_mb": 50,
}

# ═══════════════════════════════════════════════════════════════════
# Emoji Maps
# ═══════════════════════════════════════════════════════════════════

STAGE_EMOJI: dict[str, str] = {
    "S0_INTAKE":     "📥",
    "S1_LEGAL":      "⚖️",
    "S2_BLUEPRINT":  "🏗️",
    "S3_DESIGN":     "🎨",
    "S4_CODEGEN":    "💻",
    "S5_BUILD":      "🔨",
    "S6_TEST":       "🧪",
    "S7_DEPLOY":     "🚀",
    "S8_VERIFY":     "✅",
    "S9_HANDOFF":    "🎉",
    "COMPLETED":     "🏁",
    "HALTED":        "🛑",
}

MODE_EMOJI: dict[str, str] = {
    "cloud":  "☁️",
    "local":  "💻",
    "hybrid": "🔀",
}

AUTONOMY_EMOJI: dict[str, str] = {
    "autopilot": "🤖",
    "copilot":   "👨‍✈️",
}

NOTIFICATION_EMOJI: dict[str, str] = {
    NotificationType.INFO:             "ℹ️",
    NotificationType.STAGE_TRANSITION: "➡️",
    NotificationType.DECISION_NEEDED:  "🤔",
    NotificationType.ERROR:            "⚠️",
    NotificationType.BUDGET_ALERT:     "💰",
    NotificationType.LEGAL_ALERT:      "⚖️",
    NotificationType.RESEARCH_NEEDED:  "🔍",
    NotificationType.WAR_ROOM:         "🔴",
    NotificationType.COMPLETION:       "🎉",
}


# ═══════════════════════════════════════════════════════════════════
# Message Formatting
# ═══════════════════════════════════════════════════════════════════


def project_display_name(project_or_state: Any) -> str:
    """Return a human-facing name for a project.

    v5.8.12 Issue 15: user-facing Telegram strings must never show the
    raw `proj_<hex>` identifier. Resolution order:
      1. state.intake["app_name"]
      2. project_metadata["app_name"] / project["app_name"]
      3. project["name"]
      4. state.idea_name
      5. humanized suffix — "Project <short-id>"

    Accepts either a PipelineState (duck-typed) or a plain dict (e.g. the
    Supabase active_project row).
    """
    if project_or_state is None:
        return "your project"

    # Dict path (Supabase active_project row or bare dict).
    if isinstance(project_or_state, dict):
        d = project_or_state
        intake = d.get("intake") or {}
        name = (
            (intake.get("app_name") if isinstance(intake, dict) else None)
            or d.get("app_name")
            or d.get("name")
            or d.get("idea_name")
        )
        if name:
            return str(name)
        pid = str(d.get("project_id") or d.get("id") or "")
        short = pid.replace("proj_", "").replace("proj-", "")[:8] or "unknown"
        return f"Project {short}"

    # Object path (PipelineState or similar).
    intake = getattr(project_or_state, "intake", None) or {}
    name = None
    if isinstance(intake, dict):
        name = intake.get("app_name")
    if not name:
        meta = getattr(project_or_state, "project_metadata", None) or {}
        name = meta.get("app_name") if isinstance(meta, dict) else None
    if not name:
        name = getattr(project_or_state, "app_name", None)
    if not name:
        name = getattr(project_or_state, "idea_name", None)
    if name:
        return str(name)
    pid = str(getattr(project_or_state, "project_id", "") or "")
    short = pid.replace("proj_", "").replace("proj-", "")[:8] or "unknown"
    return f"Project {short}"


def truncate_message(text: str, max_length: int = 4096) -> str:
    """Truncate message to Telegram's limit.

    Spec: §5.1
    Telegram messages have a hard 4096 character limit.
    Truncation adds a "(truncated)" indicator.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 20] + "\n\n_(truncated)_"


def format_stage_progress(state: PipelineState) -> str:
    """Format visual progress bar for /status command.

    Spec: §5.2 (/status)
    Shows ✅ for completed, 🔵 for current, ⚪ for pending, 🔴 for halted.
    """
    stages = [
        "S0_INTAKE", "S1_LEGAL", "S2_BLUEPRINT", "S4_CODEGEN",
        "S5_BUILD", "S6_TEST", "S7_DEPLOY", "S8_VERIFY", "S9_HANDOFF",
    ]
    current = state.current_stage.value
    current_idx = next(
        (i for i, s in enumerate(stages) if s == current), -1,
    )

    progress = ""
    for i, stage_name in enumerate(stages):
        if i < current_idx:
            progress += "✅"
        elif i == current_idx:
            if state.current_stage == Stage.HALTED:
                progress += "🔴"
            else:
                progress += "🔵"
        else:
            progress += "⚪"

    return progress


def format_status_message(state: PipelineState) -> str:
    """Format the full /status response.

    Spec: §5.2 (/status)
    """
    progress = format_stage_progress(state)
    stack_str = state.selected_stack.value if state.selected_stack else "Pending"

    try:
        created = datetime.fromisoformat(state.created_at)
        elapsed = datetime.now(timezone.utc) - created
        elapsed_str = f"{elapsed.seconds // 60}m {elapsed.seconds % 60}s"
    except (ValueError, TypeError):
        elapsed_str = "N/A"

    msg = (
        f"📊 {project_display_name(state)}\n"
        f"{progress}\n"
        f"Stage: {state.current_stage.value}\n"
        f"Stack: {stack_str}\n"
        f"Mode: {state.execution_mode.value} | "
        f"{state.autonomy_mode.value}\n"
        f"Elapsed: {elapsed_str}\n"
        f"Cost: ${state.total_cost_usd:.2f} "
        f"({state.total_cost_usd * 3.75:.2f} SAR)\n"
        f"Snapshot: #{state.snapshot_id or 0}\n"
    )

    if state.war_room_active:
        msg += "\n🔴 WAR ROOM ACTIVE"
    if state.legal_halt:
        msg += f"\n⚖️ LEGAL HALT: {(state.legal_halt_reason or '')[:80]}"
    if state.circuit_breaker_triggered:
        msg += "\n💰 CIRCUIT BREAKER"

    return truncate_message(msg)


def format_cost_message(state: PipelineState) -> str:
    """Format the /cost budget breakdown.

    Spec: §5.2 (/cost)
    """
    msg = f"💰 {project_display_name(state)}\n\n"

    # Show all phase budget categories (even if $0)
    all_phases = {**{k: 0.0 for k in PHASE_BUDGET_LIMITS}, **state.phase_costs}
    for phase, cost in sorted(all_phases.items()):
        limit = PHASE_BUDGET_LIMITS.get(phase, 2.00)
        bar_filled = min(10, int(cost / (limit / 10)))
        bar_empty = max(0, 10 - bar_filled)
        bar = "█" * bar_filled + "░" * bar_empty
        msg += f"  {phase}: ${cost:.3f} [{bar}] ${limit:.2f}\n"

    msg += (
        f"\nTotal: ${state.total_cost_usd:.2f} "
        f"({state.total_cost_usd * 3.75:.2f} SAR)"
    )

    if state.war_room_history:
        msg += f"\nWar Room: {len(state.war_room_history)} activations"

    return truncate_message(msg)


def format_halt_message(state: PipelineState, reason: str = "") -> str:
    """Format the halt notification.

    Spec: §4.10 (Halt Handler) + v5.8.12 Issue 19 (structured halt payload).
    If a structured HaltReason is attached in project_metadata, render it;
    otherwise fall back to the legacy free-text path (but never show the
    literal word "unknown" as the reason — Issue 19).
    """
    struct = state.project_metadata.get("halt_reason_struct")
    if struct:
        try:
            from factory.core.halt import HaltCode, HaltReason
            obj = HaltReason(
                code=HaltCode(struct["code"]),
                title=struct["title"],
                detail=struct["detail"],
                stage=struct.get("stage", state.current_stage.value),
                failing_gate=struct.get("failing_gate"),
                remediation_steps=list(struct.get("remediation_steps") or []),
                restore_options=list(struct.get("restore_options") or ["/continue", "/cancel"]),
            )
            return truncate_message(obj.format_for_telegram())
        except (KeyError, ValueError):
            pass  # fall through to legacy rendering

    # Legacy path — never emit the literal string "unknown".
    if not reason:
        candidates = [
            state.legal_halt_reason,
            state.project_metadata.get("halt_reason"),
            state.project_metadata.get("last_error"),
        ]
        reason = next(
            (c for c in candidates if c and c.strip() and c.strip().lower() != "unknown"),
            "No diagnostic detail captured",
        )
    errors = state.errors[-5:] if state.errors else []
    war_room = state.war_room_history[-3:] if state.war_room_history else []

    msg = (
        f"🛑 Pipeline halted at {state.current_stage.value}\n\n"
        f"Reason: {reason}\n\n"
    )

    if errors:
        msg += "Recent errors:\n"
        for e in errors:
            msg += (
                f"  • {e.get('type', 'unknown')}: "
                f"{e.get('error', '')[:200]}\n"
            )

    if war_room:
        msg += f"\nWar Room: {len(state.war_room_history)} activations\n"
        last = war_room[-1]
        msg += (
            f"  Last: L{last.get('level', '?')} — "
            f"{'Resolved' if last.get('resolved') else 'FAILED'}\n"
        )

    msg += (
        f"\n💰 Cost: ${state.total_cost_usd:.2f}\n"
        f"⏪ Restore: /restore State_#{state.snapshot_id}\n"
        f"▶️ Resume: /continue\n"
        f"❌ Cancel: /cancel"
    )

    return truncate_message(msg)


def format_welcome_message(first_name: str) -> str:
    """Format the /start welcome message.

    Spec: §5.2 (/start)
    """
    return (
        f"🏭 Welcome to AI Factory v5.8, {first_name}!\n\n"
        f"🔧 Builds apps from your description.\n"
        f"📱 Stacks: FlutterFlow, React Native, Swift, "
        f"Kotlin, Unity, Python\n"
        f"🚀 Deploys: iOS, Android, Web\n\n"
        f"Just describe your app idea, or /new to start.\n\n"
        f"Defaults: 🆓 Basic (free) | ☁️ Cloud | 🏠 Polling\n"
        f"  Change: /mode | /execution_mode | /online\n\n"
        f"/help for all commands."
    )


def format_help_message() -> str:
    """Format the /help command reference.

    Issue 25/27: three-axis mode system clearly documented;
    all commands match registered handlers.
    Spec: §5.2 (/help)
    """
    return (
        "🏭 AI Factory v5.8 — Command Reference\n\n"
        "📱 Projects\n"
        "  /new [description]        — start a new app\n"
        "  /status                   — pipeline progress\n"
        "  /cost                     — budget breakdown\n"
        "  /continue                 — resume halted pipeline\n"
        "  /cancel                   — cancel & archive project\n"
        "  /modify <url> <desc>      — modify existing repo\n"
        "  /rename <name>            — rename current project\n"
        "  /update_logo              — upload/update app logo\n\n"
        "⚙️ Three-Axis Mode System\n\n"
        "  1️⃣  Master axis — AI provider strategy\n"
        "    /basic    🆓  free-only, $0 enforced\n"
        "    /balanced ⚖️  smart paid+free mix (default)\n"
        "    /turbo    🚀  max performance, ignore cost\n"
        "    /custom   🎛  manual provider selection\n"
        "    /mode [basic|balanced|turbo|custom] — set or show\n\n"
        "  2️⃣  Execution axis — where code runs\n"
        "    /execution_mode cloud   ☁️  Render / Cloud Run\n"
        "    /execution_mode local   💻  your machine (tunnel)\n"
        "    /execution_mode hybrid  🔀  cloud build, local deploy\n\n"
        "  3️⃣  Transport axis — how bot connects to Telegram\n"
        "    /online   🌐  Render webhook (auto-reverts in 12h)\n"
        "    /local    🏠  local polling (run_bot.py)\n\n"
        "  /autonomy                 — toggle autopilot / copilot\n"
        "  /switch_stack             — guidance on changing tech stack\n"
        "  /quota                    — view monthly quota usage\n"
        "  /budget [USD]             — show or set budget cap\n\n"
        "⏪ Time Travel\n"
        "  /snapshots                — list all snapshots\n"
        "  /restore State_#N         — restore to snapshot N\n"
        "  /diff <id1> <id2>         — diff two snapshots\n"
        "  /rerun <stage>            — re-run a stage\n"
        "  /rerun_confirm            — confirm a pending rerun\n\n"
        "🚀 Deploy\n"
        "  /deploy_confirm           — confirm deployment\n"
        "  /deploy_cancel            — cancel deployment\n\n"
        "🔧 Admin\n"
        "  /admin                    — admin overrides\n"
        "  /setup                    — first-time environment setup\n"
        "  /force_continue <reason>  — override legal halt\n\n"
        "🔍 Diagnostics\n"
        "  /providers                — AI/scout/memory chain status\n"
        "  /warroom                  — war room activation log\n"
        "  /legal                    — compliance review log\n"
        "  /evaluate                 — score current project\n"
        "  /analytics                — pipeline analytics\n\n"
        "💬 Or just describe your app idea — the factory takes it from there."
    )


def format_project_started(
    project_id: str, state: PipelineState,
) -> str:
    """Format the project creation confirmation.

    Issue 46: show all three mode axes (master + execution + autonomy).
    Spec: §5.2 (/new)
    """
    exec_str   = MODE_EMOJI.get(state.execution_mode.value, "")
    auto_str   = AUTONOMY_EMOJI.get(state.autonomy_mode.value, "")
    master_str = state.master_mode.emoji   # Issue 46: was never displayed

    # Issue 15: prefer the app name; fall back to a humanized id only if
    # state truly carries nothing else.
    display = project_display_name(state)
    return (
        f"🚀 {display} started!\n"
        f"Master: {master_str} {state.master_mode.label}\n"
        f"Execution: {exec_str} {state.execution_mode.value.upper()}\n"
        f"Autonomy: {auto_str} {state.autonomy_mode.value}\n"
        f"Processing..."
    )