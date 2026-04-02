"""
AI Factory Pipeline v5.6 — Telegram Module

Telegram Command Center for operator interaction.
"""

from factory.telegram.messages import (
    format_status_message,
    format_cost_message,
    format_halt_message,
    format_welcome_message,
    format_help_message,
    format_project_started,
    truncate_message,
    TELEGRAM_CONFIG,
    STAGE_EMOJI,
    MODE_EMOJI,
    AUTONOMY_EMOJI,
)

from factory.telegram.notifications import (
    send_telegram_message,
    send_telegram_file,
    send_telegram_content,
    notify_operator,
    send_telegram_budget_alert,
    set_bot_instance,
    get_bot,
)

from factory.telegram.decisions import (
    present_decision,
    store_operator_decision,
    record_deploy_decision,
    check_deploy_decision,
    clear_deploy_decision,
    set_operator_state,
    get_operator_state,
    clear_operator_state,
    get_operator_preferences,
    set_operator_preference,
)

from factory.telegram.bot import (
    setup_bot,
    authenticate_operator,
    require_auth,
    get_active_project,
    update_project_state,
)

__all__ = [
    "setup_bot",
    "notify_operator",
    "send_telegram_message",
    "send_telegram_file",
    "present_decision",
    "format_status_message",
]