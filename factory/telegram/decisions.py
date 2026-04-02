"""
AI Factory Pipeline v5.6 — Decision Queue (4-Way Copilot Menus)

Implements:
  - §3.7 4-Way Decision Matrix (Copilot mode)
  - §5.3 Callback handler for inline keyboard decisions
  - Decision polling with 1-hour timeout (DR Scenario #10)

In Copilot mode, the pipeline presents 4 options at key decision
points. The operator taps one. Timeout (1 hour) auto-selects the
recommended option.

In Autopilot mode, decisions are made automatically — this module
is not invoked.

Spec Authority: v5.6 §3.7, §5.3
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from factory.core.state import (
    AutonomyMode,
    PipelineState,
    NotificationType,
)
from factory.telegram.notifications import notify_operator

logger = logging.getLogger("factory.telegram.decisions")


# ═══════════════════════════════════════════════════════════════════
# Decision Storage (in-memory for dry-run, Supabase for production)
# ═══════════════════════════════════════════════════════════════════

# In-memory decision store for local/dry-run mode
_pending_decisions: dict[str, dict] = {}
_resolved_decisions: dict[str, str] = {}


async def store_decision_request(
    decision_id: str,
    project_id: str,
    operator_id: str,
    decision_type: str,
    options: list[dict],
    recommended: int = 0,
) -> None:
    """Store a pending decision request.

    Args:
        decision_id: Unique decision identifier.
        project_id: Project this decision belongs to.
        operator_id: Telegram user ID.
        decision_type: Category (stack_selection, design_choice, etc.).
        options: List of option dicts with 'label' and 'value'.
        recommended: Index of recommended option (default 0).
    """
    _pending_decisions[decision_id] = {
        "project_id": project_id,
        "operator_id": operator_id,
        "decision_type": decision_type,
        "options": options,
        "recommended": recommended,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
        "selected": None,
    }


async def resolve_decision(decision_id: str, selected_value: str) -> None:
    """Record operator's decision choice.

    Called from callback handler when operator taps an option.
    """
    if decision_id in _pending_decisions:
        _pending_decisions[decision_id]["resolved"] = True
        _pending_decisions[decision_id]["selected"] = selected_value
    _resolved_decisions[decision_id] = selected_value


async def get_decision_result(decision_id: str) -> Optional[str]:
    """Get the result of a decision (or None if pending)."""
    return _resolved_decisions.get(decision_id)


# ═══════════════════════════════════════════════════════════════════
# Deploy Decision Store (FIX-08)
# ═══════════════════════════════════════════════════════════════════

_deploy_decisions: dict[str, str] = {}


async def record_deploy_decision(
    project_id: str, decision: str,
) -> None:
    """Record deploy confirm/cancel decision.

    Spec: §4.6.3 (FIX-08)
    """
    _deploy_decisions[project_id] = decision


async def check_deploy_decision(project_id: str) -> Optional[str]:
    """Check if operator has made a deploy decision.

    Returns 'confirm', 'cancel', or None.
    """
    return _deploy_decisions.get(project_id)


async def clear_deploy_decision(project_id: str) -> None:
    """Clear deploy decision after processing."""
    _deploy_decisions.pop(project_id, None)


# ═══════════════════════════════════════════════════════════════════
# Operator State Tracking
# ═══════════════════════════════════════════════════════════════════

_operator_states: dict[str, str] = {}


async def set_operator_state(operator_id: str, state: str) -> None:
    """Set conversational state for operator.

    Spec: §5.3 (awaiting_project_description, etc.)
    """
    _operator_states[operator_id] = state


async def get_operator_state(operator_id: str) -> Optional[str]:
    """Get current conversational state."""
    return _operator_states.get(operator_id)


async def clear_operator_state(operator_id: str) -> None:
    """Clear conversational state after processing."""
    _operator_states.pop(operator_id, None)


# ═══════════════════════════════════════════════════════════════════
# Operator Preferences
# ═══════════════════════════════════════════════════════════════════

_operator_prefs: dict[str, dict] = {}


async def get_operator_preferences(operator_id: str) -> dict:
    """Get operator's stored preferences.

    Defaults: autopilot mode, cloud execution.
    """
    return _operator_prefs.get(operator_id, {
        "autonomy_mode": "autopilot",
        "execution_mode": "cloud",
    })


async def set_operator_preference(
    operator_id: str, key: str, value: Any,
) -> None:
    """Set a single operator preference."""
    if operator_id not in _operator_prefs:
        _operator_prefs[operator_id] = {
            "autonomy_mode": "autopilot",
            "execution_mode": "cloud",
        }
    _operator_prefs[operator_id][key] = value


# ═══════════════════════════════════════════════════════════════════
# §3.7 4-Way Decision Presenter
# ═══════════════════════════════════════════════════════════════════


async def present_decision(
    state: PipelineState,
    decision_type: str,
    question: str,
    options: list[dict[str, str]],
    recommended: int = 0,
    timeout_seconds: int = 3600,
) -> str:
    """Present a 4-way decision menu to the operator.

    Spec: §3.7
    In Copilot mode: sends inline keyboard, waits for response.
    In Autopilot mode: auto-selects recommended option.

    Args:
        state: Pipeline state.
        decision_type: Category (stack_selection, design_choice, etc.).
        question: Question text shown above options.
        options: List of dicts with 'label' and 'value' keys.
                 Maximum 4 options per spec.
        recommended: Index of the recommended option.
        timeout_seconds: Timeout before auto-selecting (default 1 hour).

    Returns:
        The 'value' of the selected option.
    """
    # Autopilot: auto-select recommendation
    if state.autonomy_mode == AutonomyMode.AUTOPILOT:
        selected = options[recommended]["value"]
        logger.info(
            f"[Autopilot] Auto-selected '{selected}' for {decision_type}"
        )
        return selected

    # Copilot: present inline keyboard
    decision_id = f"dec_{uuid.uuid4().hex[:8]}"

    await store_decision_request(
        decision_id=decision_id,
        project_id=state.project_id,
        operator_id=state.operator_id,
        decision_type=decision_type,
        options=options,
        recommended=recommended,
    )

    # Build inline keyboard
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard_rows = []
        for i, opt in enumerate(options[:4]):  # Max 4 options
            label = opt["label"]
            if i == recommended:
                label = f"⭐ {label} (recommended)"
            keyboard_rows.append([
                InlineKeyboardButton(
                    label,
                    callback_data=f"decision_{decision_id}_{opt['value']}",
                )
            ])

        markup = InlineKeyboardMarkup(keyboard_rows)

        await notify_operator(
            state,
            NotificationType.DECISION_NEEDED,
            f"{question}\n\n"
            f"Timeout: {timeout_seconds // 60} min → auto-selects recommended.",
            reply_markup=markup,
        )
    except ImportError:
        # Telegram not available (dry-run) — auto-select
        logger.info(
            f"[DryRun] Decision '{decision_type}' auto-selected: "
            f"{options[recommended]['value']}"
        )
        return options[recommended]["value"]

    # Poll for decision
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        result = await get_decision_result(decision_id)
        if result is not None:
            logger.info(
                f"[Copilot] Operator selected '{result}' for {decision_type}"
            )
            return result
        await asyncio.sleep(5)

    # Timeout — auto-select recommended
    selected = options[recommended]["value"]
    logger.warning(
        f"[Copilot] Decision timeout for {decision_type}, "
        f"auto-selected: {selected}"
    )
    await notify_operator(
        state,
        NotificationType.INFO,
        f"⏱️ Decision timeout — auto-selected: {options[recommended]['label']}",
    )
    return selected


async def store_operator_decision(
    operator_id: str, callback_data: str,
) -> None:
    """Process a decision callback from inline keyboard.

    Spec: §5.3
    Called from callback handler.
    callback_data format: "decision_{decision_id}_{value}"
    """
    parts = callback_data.split("_", 2)
    if len(parts) < 2:
        logger.warning(f"Invalid decision callback: {callback_data}")
        return

    # Parse: the format is "{decision_id}_{value}"
    # decision_id is "dec_XXXXXXXX", value is everything after
    remaining = callback_data  # Already has "decision_" prefix stripped
    # Find the decision_id pattern: "dec_XXXXXXXX"
    if remaining.startswith("dec_"):
        # dec_XXXXXXXX_value
        dec_parts = remaining.split("_", 2)
        if len(dec_parts) >= 3:
            decision_id = f"dec_{dec_parts[1]}"
            value = dec_parts[2]
            await resolve_decision(decision_id, value)
            logger.info(
                f"Decision {decision_id} resolved: {value} "
                f"by operator {operator_id}"
            )