"""
AI Factory Pipeline v5.8 — Decision Queue (4-Way Copilot Menus)

Implements:
  - §3.7 4-Way Decision Matrix (Copilot mode)
  - §5.3 Callback handler for inline keyboard decisions
  - §7.1.2 Free-text reply mechanism (Setup Wizard)
  - Decision polling with 1-hour timeout (DR Scenario #10)

In Copilot mode, the pipeline presents 4 options at key decision
points. The operator taps one. Timeout (1 hour) auto-selects the
recommended option.

In Autopilot mode, decisions are made automatically — this module
is not invoked.

Spec Authority: v5.8 §3.7, §5.3
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


async def resolve_decision(decision_id: str, selected_value: str) -> bool:
    """Record operator's decision choice.

    Called from callback handler when operator taps an option.
    Returns True if decision existed, False otherwise.
    """
    if decision_id not in _pending_decisions:
        _resolved_decisions.pop(decision_id, None)
        return False

    entry = _pending_decisions[decision_id]
    # Support both dict entries and asyncio.Future entries
    if hasattr(entry, "set_result"):
        # It's a Future
        if not entry.done():
            entry.set_result(selected_value)
    else:
        entry["resolved"] = True
        entry["selected"] = selected_value
    _resolved_decisions[decision_id] = selected_value
    return True


async def get_decision_result(decision_id: str) -> Optional[str]:
    """Get the result of a decision (or None if pending)."""
    return _resolved_decisions.get(decision_id)


# ═══════════════════════════════════════════════════════════════════
# Deploy Decision Store (FIX-08)
# ═══════════════════════════════════════════════════════════════════

_deploy_decisions: dict[str, dict] = {}


async def record_deploy_decision(
    project_id: str,
    operator_id: str = "",
    confirmed: bool = True,
) -> None:
    """Record deploy confirm/cancel decision.

    Spec: §4.6.1 — Pre-Deploy Operator Acknowledgment Gate (FIX-08).
    """
    _deploy_decisions[project_id] = {
        "confirmed": confirmed,
        "operator_id": operator_id,
    }
    logger.info(
        f"Deploy decision for {project_id}: "
        f"{'CONFIRMED' if confirmed else 'CANCELLED'} by {operator_id}"
    )


async def check_deploy_decision(project_id: str) -> Optional[bool]:
    """Check if a deploy decision exists.

    Returns: True (confirmed), False (cancelled), None (pending).
    """
    decision = _deploy_decisions.get(project_id)
    if decision is None:
        return None
    return decision["confirmed"]


async def clear_deploy_decision(project_id: str) -> None:
    """Clear deploy decision after processing."""
    _deploy_decisions.pop(project_id, None)


# ═══════════════════════════════════════════════════════════════════
# Operator State Tracking
# ═══════════════════════════════════════════════════════════════════

_operator_states: dict[str, dict] = {}


async def set_operator_state(
    operator_id: str, state: str, context: Optional[dict] = None,
) -> None:
    """Set conversational state for operator — write-through to Supabase."""
    _operator_states[operator_id] = {"state": state, "context": context or {}}
    try:
        from factory.integrations.supabase import set_operator_state_db
        await set_operator_state_db(operator_id, state, context)
    except Exception as e:
        logger.warning(f"[decisions] Failed to persist operator state to DB: {e}")


async def get_operator_state(operator_id: str) -> Optional[dict]:
    """Get current conversational state — memory first, Supabase fallback."""
    if operator_id in _operator_states:
        return _operator_states[operator_id]
    try:
        from factory.integrations.supabase import get_operator_state_db
        row = await get_operator_state_db(operator_id)
        if row and row.get("state") and row["state"] not in ("__prefs", "__cleared"):
            val = {"state": row["state"], "context": row.get("context") or {}}
            _operator_states[operator_id] = val
            return val
    except Exception as e:
        logger.warning(f"[decisions] Failed to load operator state from DB: {e}")
    return None


async def clear_operator_state(operator_id: str) -> None:
    """Clear conversational state — clears memory and Supabase."""
    _operator_states.pop(operator_id, None)
    try:
        from factory.integrations.supabase import set_operator_state_db
        await set_operator_state_db(operator_id, "__cleared", {})
    except Exception as e:
        logger.warning(f"[decisions] Failed to clear operator state in DB: {e}")


# ═══════════════════════════════════════════════════════════════════
# Operator Preferences
# ═══════════════════════════════════════════════════════════════════

_operator_prefs: dict[str, dict] = {}

_PREFS_DEFAULTS: dict = {"autonomy_mode": "autopilot", "execution_mode": "cloud"}
_PREFS_STATE_KEY = "__prefs"


def get_operator_preferences(operator_id: str) -> dict:
    """Get operator's stored preferences (sync — memory cache only).

    Use load_operator_preferences() to populate from Supabase first.
    """
    return _operator_prefs.get(operator_id, dict(_PREFS_DEFAULTS))


async def load_operator_preferences(operator_id: str) -> dict:
    """Load preferences from Supabase into memory cache, return them."""
    if operator_id in _operator_prefs:
        return _operator_prefs[operator_id]
    try:
        from factory.integrations.supabase import get_operator_state_db
        row = await get_operator_state_db(operator_id + _PREFS_STATE_KEY)
        if row and row.get("context"):
            prefs = {**_PREFS_DEFAULTS, **row["context"]}
            _operator_prefs[operator_id] = prefs
            return prefs
    except Exception as e:
        logger.warning(f"[decisions] Failed to load preferences from DB: {e}")
    prefs = dict(_PREFS_DEFAULTS)
    _operator_prefs[operator_id] = prefs
    return prefs


async def set_operator_preference(
    operator_id: str, key: str, value: Any,
) -> None:
    """Set a single operator preference — write-through to Supabase."""
    if operator_id not in _operator_prefs:
        _operator_prefs[operator_id] = dict(_PREFS_DEFAULTS)
    _operator_prefs[operator_id][key] = value
    try:
        from factory.integrations.supabase import set_operator_state_db
        await set_operator_state_db(
            operator_id + _PREFS_STATE_KEY,
            _PREFS_STATE_KEY,
            _operator_prefs[operator_id],
        )
    except Exception as e:
        logger.warning(f"[decisions] Failed to persist preference to DB: {e}")


# ═══════════════════════════════════════════════════════════════════
# §3.7 4-Way Decision Presenter
# ═══════════════════════════════════════════════════════════════════


async def present_decision(
    state: PipelineState,
    decision_type: str,
    question: str = "",
    options: list[dict[str, str]] = None,
    recommended: int = 0,
    timeout_seconds: int = 3600,
    message: str = "",  # alias for question
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
    if options is None:
        options = []
    question = question or message  # accept either kwarg
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


# ═══════════════════════════════════════════════════════════════════
# §7.1.2 Free-Text Reply Mechanism (Setup Wizard)
# ═══════════════════════════════════════════════════════════════════

# Pending free-text replies: {operator_id: asyncio.Future}
_pending_replies: dict[str, asyncio.Future] = {}


async def wait_for_operator_reply(
    operator_id: str,
    timeout: int = 300,
    default: str = "SKIP",
) -> str:
    """Wait for a free-text reply from an operator.

    Spec: §7.1.2 — Each key has a 300-second entry timeout with SKIP default.

    Used by the setup wizard to collect API keys and other free-text
    input from the operator via Telegram.

    Args:
        operator_id: Telegram user ID string.
        timeout: Seconds to wait before returning default.
        default: Value returned on timeout.

    Returns:
        The operator's text reply, or default on timeout.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _pending_replies[operator_id] = future

    try:
        result = await asyncio.wait_for(future, timeout=timeout)
        logger.info(
            f"[Reply] Operator {operator_id} replied ({len(result)} chars)"
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(
            f"[Reply] Timeout ({timeout}s) for operator {operator_id}, "
            f"using default: {default}"
        )
        return default
    finally:
        _pending_replies.pop(operator_id, None)


async def resolve_reply(operator_id: str, text: str) -> bool:
    """Resolve a pending free-text reply with the operator's message.

    Called by handle_message() when it detects a pending reply
    for the current operator.

    Args:
        operator_id: Telegram user ID string.
        text: The operator's message text.

    Returns:
        True if a pending reply was resolved, False otherwise.
    """
    future = _pending_replies.get(operator_id)
    if future is None or future.done():
        return False

    future.set_result(text)
    logger.debug(f"[Reply] Resolved pending reply for {operator_id}")
    return True


def has_pending_reply(operator_id: str) -> bool:
    """Check if an operator has a pending reply future.

    Used by handle_message() to decide whether to intercept free-text
    input for the wizard vs. normal handling.
    """
    future = _pending_replies.get(operator_id)
    return future is not None and not future.done()


# ═══════════════════════════════════════════════════════════════════
# §4.1 v5.8 — Platform Multi-Select (14 canonical platforms)
# ═══════════════════════════════════════════════════════════════════

ALL_PLATFORMS: list[dict] = [
    {"id": "ios",          "label": "iOS (iPhone/iPad)"},
    {"id": "android",      "label": "Android (Phone/Tablet)"},
    {"id": "web",          "label": "Web (Browser/PWA)"},
    {"id": "macos",        "label": "macOS Desktop"},
    {"id": "windows",      "label": "Windows Desktop"},
    {"id": "tvos",         "label": "tvOS (Apple TV)"},
    {"id": "watchos",      "label": "watchOS (Apple Watch)"},
    {"id": "android_tv",   "label": "Android TV"},
    {"id": "wear_os",      "label": "Wear OS (Android Watch)"},
    {"id": "kaios",        "label": "KaiOS (Feature Phone)"},
    {"id": "harmonyos",    "label": "HarmonyOS (Huawei)"},
    {"id": "tizen_tv",     "label": "Samsung Tizen TV"},
    {"id": "tizen_watch",  "label": "Samsung Galaxy Watch"},
    {"id": "linux",        "label": "Linux Desktop"},
]

_PLATFORM_SHORTCUTS: dict[str, list[str]] = {
    "mobile":  ["ios", "android"],
    "web":     ["web"],
    "all":     ["ios", "android", "web"],
    "full":    ["ios", "android", "web", "macos", "windows"],
    "ios":     ["ios"],
    "android": ["android"],
}


def _parse_platform_reply(reply: str, default: list[str]) -> list[str]:
    """Parse operator's platform selection reply.

    Accepts:
      - Shortcuts: "mobile", "all", "full", "web"
      - Comma-separated numbers: "1,2,3"
      - Platform IDs: "ios,android"
    """
    reply = reply.strip().lower()

    # Check named shortcuts first
    if reply in _PLATFORM_SHORTCUTS:
        return _PLATFORM_SHORTCUTS[reply]

    # Parse comma/space-separated tokens
    tokens = [t.strip() for t in reply.replace(" ", ",").split(",") if t.strip()]
    result: list[str] = []

    for token in tokens:
        # Try as 1-indexed number
        try:
            idx = int(token) - 1
            if 0 <= idx < len(ALL_PLATFORMS):
                pid = ALL_PLATFORMS[idx]["id"]
                if pid not in result:
                    result.append(pid)
            continue
        except ValueError:
            pass

        # Try as platform ID or label match
        for p in ALL_PLATFORMS:
            if token == p["id"] or token in p["label"].lower():
                if p["id"] not in result:
                    result.append(p["id"])
                break

    return result if result else default


async def present_platform_multiselect(
    state: "PipelineState",
    timeout_seconds: int = 3600,
    default: list[str] | None = None,
) -> list[str]:
    """Present a 14-platform multi-select to the operator.

    Spec: v5.8 §4.1 — S0 platform selection.
    COPILOT: sends numbered list, waits for text reply.
    AUTOPILOT: returns default (["ios", "android"]).

    Args:
        state: Pipeline state.
        timeout_seconds: Wait timeout (default 1 hour).
        default: Platforms to return on timeout / AUTOPILOT.

    Returns:
        List of selected platform IDs.
    """
    if default is None:
        default = ["ios", "android"]

    if state.autonomy_mode == AutonomyMode.AUTOPILOT:
        logger.info(f"[Autopilot] Platform default: {default}")
        return default

    # Build the numbered list message
    lines = ["📱 *Select target platforms* — reply with numbers (comma-separated):\n"]
    for i, p in enumerate(ALL_PLATFORMS, 1):
        lines.append(f"  {i:2}. {p['label']}")
    lines.append(
        "\n*Shortcuts:* `mobile` (1,2) · `all` (1-3) · `full` (1-5)\n"
        "_Example: `1,2,3` or `mobile`_"
    )

    await notify_operator(
        state,
        "\n".join(lines),
        NotificationType.DECISION_NEEDED,
    )

    reply = await wait_for_operator_reply(
        state.operator_id,
        timeout=timeout_seconds,
        default=",".join(str(i + 1) for i, p in enumerate(ALL_PLATFORMS) if p["id"] in default),
    )

    selected = _parse_platform_reply(reply, default)
    logger.info(f"[{state.project_id}] Platforms selected: {selected}")
    return selected