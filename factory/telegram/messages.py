"""
AI Factory Pipeline v5.6 — Telegram Message Formatting

Implements:
  - §5.1 Message formatting and constants
  - §5.4 Notification templates
  - Telegram 4096 character limit enforcement

Spec Authority: v5.6 §5.1, §5.4
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
    PipelineState,
    Stage,
)

logger = logging.getLogger("factory.telegram.messages")


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
    "S3_CODEGEN":    "💻",
    "S4_BUILD":      "🔨",
    "S5_TEST":       "🧪",
    "S6_DEPLOY":     "🚀",
    "S7_VERIFY":     "✅",
    "S8_HANDOFF":    "🎉",
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
        "S0_INTAKE", "S1_LEGAL", "S2_BLUEPRINT", "S3_CODEGEN",
        "S4_BUILD", "S5_TEST", "S6_DEPLOY", "S7_VERIFY", "S8_HANDOFF",
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
        f"📊 {state.project_id}\n"
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
    msg = f"💰 {state.project_id}\n\n"

    for phase, cost in sorted(state.phase_costs.items()):
        bar_filled = min(10, int(cost / 0.20))
        bar_empty = max(0, 10 - bar_filled)
        bar = "█" * bar_filled + "░" * bar_empty
        msg += f"  {phase}: ${cost:.3f} [{bar}] $2.00\n"

    msg += (
        f"\nTotal: ${state.total_cost_usd:.2f} "
        f"({state.total_cost_usd * 3.75:.2f} SAR)"
    )

    if state.war_room_history:
        msg += f"\nWar Room: {len(state.war_room_history)} activations"

    return truncate_message(msg)


def format_halt_message(state: PipelineState) -> str:
    """Format the halt notification.

    Spec: §4.10 (Halt Handler)
    """
    reason = state.legal_halt_reason or "Unknown (check errors)"
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
        f"🏭 Welcome to AI Factory v5.6, {first_name}!\n\n"
        f"🔧 Builds apps from your description.\n"
        f"📱 Stacks: FlutterFlow, React Native, Swift, "
        f"Kotlin, Unity, Python\n"
        f"🚀 Deploys: iOS, Android, Web\n\n"
        f"Just describe your app idea, or /new to start.\n"
        f"Current: Cloud | Autopilot\n\n"
        f"/help for all commands."
    )


def format_help_message() -> str:
    """Format the /help command reference.

    Spec: §5.2 (/help)
    """
    return (
        "🏭 AI Factory v5.6\n\n"
        "Project: /new /status /cost /continue /cancel\n"
        "Control: /mode /autonomy\n"
        "Time Travel: /snapshots /restore State_#N\n"
        "Deploy: /deploy_confirm /deploy_cancel\n"
        "Compliance: /force_continue I accept compliance risk\n"
        "Budget: /admin budget_override\n"
        "Diagnostics: /warroom /legal\n\n"
        "Or just describe an app to build."
    )


def format_project_started(
    project_id: str, state: PipelineState,
) -> str:
    """Format the project creation confirmation.

    Spec: §5.2 (/new)
    """
    mode_str = MODE_EMOJI.get(state.execution_mode.value, "")
    auto_str = AUTONOMY_EMOJI.get(state.autonomy_mode.value, "")

    return (
        f"🚀 Project {project_id} started!\n"
        f"Mode: {mode_str} {state.execution_mode.value}\n"
        f"Autonomy: {auto_str} {state.autonomy_mode.value}\n"
        f"Processing..."
    )