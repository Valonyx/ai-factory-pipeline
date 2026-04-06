"""
AI Factory Pipeline v5.6 — Telegram Bot Setup

Implements:
  - §5.1 Bot architecture (registration, webhook, polling)
  - §5.1.2 Operator authentication (whitelist from Supabase)
  - §5.2 Command handler registration (16 commands)
  - §5.3 Callback handler + free-text handler

Spec Authority: v5.6 §5.1–§5.3
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Optional

from factory.core.state import (
    AutonomyMode,
    ExecutionMode,
    PipelineState,
    Stage,
)
from factory.telegram.messages import (
    format_welcome_message,
    format_help_message,
    format_status_message,
    format_cost_message,
    format_project_started,
    truncate_message,
)
from factory.telegram.notifications import (
    send_telegram_message,
    set_bot_instance,
)
from factory.telegram.decisions import (
    get_operator_state,
    set_operator_state,
    clear_operator_state,
    get_operator_preferences,
    set_operator_preference,
    store_operator_decision,
    record_deploy_decision,
)

logger = logging.getLogger("factory.telegram.bot")


# ═══════════════════════════════════════════════════════════════════
# §5.1.2 Operator Authentication
# ═══════════════════════════════════════════════════════════════════


async def authenticate_operator(update: Any) -> bool:
    """Check if the Telegram user is in the operator whitelist.

    Spec: §5.1.2
    In production, checks Supabase operator_whitelist table.
    In dry-run, all operators are allowed.
    """
    user_id = str(update.effective_user.id)

    try:
        from factory.integrations.supabase import check_operator_whitelist
        allowed = await check_operator_whitelist(user_id)
        if not allowed:
            await update.message.reply_text(
                "🚫 Unauthorized. Contact admin for access."
            )
            return False
        return True
    except Exception:
        # Supabase not configured — allow all in dry-run mode
        logger.debug(f"Auth check skipped for {user_id} (dry-run mode)")
        return True


def require_auth(fn):
    """Decorator requiring operator authentication.

    Spec: §5.1.2
    """
    @wraps(fn)
    async def wrapper(update: Any, context: Any):
        if not await authenticate_operator(update):
            return
        return await fn(update, context)
    return wrapper


# ═══════════════════════════════════════════════════════════════════
# Project State Helpers (Supabase-backed with in-memory fallback)
# Spec: §5.6 (Session Schema), §2.9 (Triple-Write)
# ═══════════════════════════════════════════════════════════════════

from factory.integrations.supabase import (
    get_active_project as _sb_get_active,
    upsert_active_project as _sb_upsert_active,
    archive_project as _sb_archive,
    upsert_pipeline_state,
)

# In-memory fallback for when Supabase is unavailable
_active_projects_fallback: dict[str, dict] = {}


async def get_active_project(operator_id: str) -> Optional[dict]:
    """Get active project — routes to Supabase with in-memory fallback.

    Spec: §5.6 (Session Schema)
    """
    result = await _sb_get_active(operator_id)
    if result is not None:
        return result
    return _active_projects_fallback.get(operator_id)


async def update_project_state(state: PipelineState) -> None:
    """Update project state — triple-write to Supabase + in-memory fallback.

    Spec: §2.9 (Triple-Write), §5.6 (active_projects)
    """
    success = await _sb_upsert_active(state.operator_id, state)
    if success:
        await upsert_pipeline_state(state.project_id, state)
    else:
        _active_projects_fallback[state.operator_id] = {
            "project_id": state.project_id,
            "current_stage": state.current_stage.value,
            "state_json": state.model_dump(mode="json"),
        }


async def archive_project(project_id: str) -> None:
    """Archive project — moves from active to archived in Supabase.

    Spec: §5.6
    """
    for op_id in list(_active_projects_fallback.keys()):
        proj = _active_projects_fallback.get(op_id, {})
        if proj.get("project_id") == project_id:
            state = PipelineState.model_validate(proj["state_json"])
            await _sb_archive(project_id, state)
            _active_projects_fallback.pop(op_id, None)
            return
    # If not in fallback, find via Supabase and archive there
    try:
        from factory.integrations.supabase import get_supabase_client
        client = get_supabase_client()
        resp = client.table("active_projects").select("*").eq("project_id", project_id).execute()
        if resp.data:
            row = resp.data[0]
            state = PipelineState.model_validate(row.get("state_json", {"project_id": project_id, "operator_id": row.get("operator_id", "")}))
            await _sb_archive(project_id, state)
        else:
            logger.info(f"Project {project_id} archive requested (Supabase)")
    except Exception as e:
        logger.warning(f"archive_project fallback failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# §5.2 Command Handlers (16 commands)
# ═══════════════════════════════════════════════════════════════════


@require_auth
async def cmd_start(update: Any, context: Any):
    """§5.2: /start — Welcome message."""
    user = update.effective_user.first_name
    await update.message.reply_text(format_welcome_message(user))


@require_auth
async def cmd_new_project(update: Any, context: Any):
    """§5.2: /new — Start a new project."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)

    if active:
        await update.message.reply_text(
            f"📋 Active project: {active['project_id']} "
            f"at {active['current_stage']}\n"
            f"Use /cancel first, or /continue."
        )
        return

    description = " ".join(context.args) if context.args else None
    if description:
        await _start_project(update, user_id, description)
    else:
        await set_operator_state(user_id, "awaiting_project_description")
        await update.message.reply_text(
            "📝 Describe your app idea.\n"
            "Send text, screenshots, voice, or documents."
        )


@require_auth
async def cmd_status(update: Any, context: Any):
    """§5.2: /status — Show project progress."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project. /new to start.")
        return

    state = PipelineState.model_validate(active["state_json"])
    await update.message.reply_text(format_status_message(state))


@require_auth
async def cmd_cost(update: Any, context: Any):
    """§5.2: /cost — Show budget breakdown."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])
    await update.message.reply_text(format_cost_message(state))


@require_auth
async def cmd_mode(update: Any, context: Any):
    """§5.2: /mode — Toggle execution mode."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])

    if context.args and context.args[0].lower() in ("cloud", "local", "hybrid"):
        target = context.args[0].lower()
        state.execution_mode = ExecutionMode(target)
        await update_project_state(state)
        emoji_map = {"cloud": "☁️", "local": "💻", "hybrid": "🔀"}
        await update.message.reply_text(
            f"{emoji_map[target]} Switched to {target.upper()}."
        )
    else:
        await update.message.reply_text(
            f"Current: {state.execution_mode.value}\n"
            f"Usage: /mode cloud | /mode local | /mode hybrid"
        )


@require_auth
async def cmd_autonomy(update: Any, context: Any):
    """§5.2: /autonomy — Toggle Autopilot/Copilot."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)

    if not active:
        prefs = await get_operator_preferences(user_id)
        current = prefs.get("autonomy_mode", "autopilot")
        new_mode = "copilot" if current == "autopilot" else "autopilot"
        await set_operator_preference(user_id, "autonomy_mode", new_mode)
        emoji = "👨‍✈️" if new_mode == "copilot" else "🤖"
        await update.message.reply_text(
            f"{emoji} Default set to {new_mode.upper()}."
        )
        return

    state = PipelineState.model_validate(active["state_json"])
    new_mode = (
        AutonomyMode.COPILOT
        if state.autonomy_mode == AutonomyMode.AUTOPILOT
        else AutonomyMode.AUTOPILOT
    )
    state.autonomy_mode = new_mode
    await update_project_state(state)

    if new_mode == AutonomyMode.COPILOT:
        await update.message.reply_text(
            "👨‍✈️ COPILOT mode.\n"
            "I'll ask at key decisions (4 options each).\n"
            "Timeout: 1hr → auto-picks recommendation."
        )
    else:
        await update.message.reply_text(
            "🤖 AUTOPILOT mode.\n"
            "All decisions automatic. Notified for: "
            "legal halts, budget breakers, completion."
        )


@require_auth
async def cmd_restore(update: Any, context: Any):
    """§5.2: /restore State_#N — Time travel."""
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text(
            "Usage: /restore State_#5\nSee: /snapshots"
        )
        return

    try:
        arg = context.args[0]
        snapshot_id = (
            int(arg.replace("State_#", ""))
            if "State_#" in arg
            else int(arg)
        )
    except ValueError:
        await update.message.reply_text(
            "Invalid ID. Use: /restore State_#5"
        )
        return

    await update.message.reply_text(
        f"⏪ Restoring to snapshot #{snapshot_id}...\n"
        f"(Full restore requires Supabase — stub for dry-run)"
    )


@require_auth
async def cmd_snapshots(update: Any, context: Any):
    """§5.2: /snapshots — List time-travel snapshots."""
    await update.message.reply_text(
        "📸 Snapshots: (requires Supabase connection)\n"
        "Use /restore State_#N to restore."
    )


@require_auth
async def cmd_continue(update: Any, context: Any):
    """§5.2: /continue — Resume halted pipeline."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])

    if (
        state.current_stage != Stage.HALTED
        and not state.legal_halt
        and not state.circuit_breaker_triggered
    ):
        await update.message.reply_text(
            "Pipeline running. /status to check."
        )
        return

    state.legal_halt = False
    state.legal_halt_reason = None
    state.circuit_breaker_triggered = False

    if state.current_stage == Stage.HALTED and state.previous_stage:
        state.current_stage = state.previous_stage

    await update_project_state(state)
    await update.message.reply_text(
        f"▶️ Resuming from {state.current_stage.value}..."
    )


@require_auth
async def cmd_cancel(update: Any, context: Any):
    """§5.2: /cancel — Cancel and archive project."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    project_id = active["project_id"]
    await archive_project(project_id)
    await update.message.reply_text(
        f"🗑️ {project_id} archived. Snapshots preserved."
    )


@require_auth
async def cmd_warroom(update: Any, context: Any):
    """§5.2: /warroom — Show War Room log."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])
    msg = "🔴 WAR ROOM ACTIVE\n\n" if state.war_room_active else "🛠️ War Room\n\n"

    if not state.war_room_history:
        msg += "No activations."
    else:
        msg += f"Total: {len(state.war_room_history)}\n"
        for wr in state.war_room_history[-5:]:
            icon = "✅" if wr.get("resolved") else "❌"
            msg += (
                f"{icon} L{wr.get('level', '?')} — "
                f"{wr.get('error', '')[:80]}\n"
            )

    await update.message.reply_text(msg)


@require_auth
async def cmd_legal(update: Any, context: Any):
    """§5.2: /legal — Show legal compliance log."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])
    msg = (
        f"⚖️ LEGAL HALT: {state.legal_halt_reason}\n\n"
        if state.legal_halt
        else "⚖️ Legal Log\n\n"
    )

    if not state.legal_checks_log:
        msg += "No checks recorded yet."
    else:
        for check in state.legal_checks_log[-10:]:
            icon = "✅" if check.get("passed") else "❌"
            msg += (
                f"{icon} {check.get('check', '?')} "
                f"({check.get('stage', '?')}/{check.get('phase', '?')})\n"
            )

    if state.legal_documents:
        msg += f"\n📋 Docs: {', '.join(state.legal_documents.keys())}"

    await update.message.reply_text(msg)


@require_auth
async def cmd_deploy_confirm(update: Any, context: Any):
    """§4.6.3 (FIX-08): /deploy_confirm — Confirm deployment."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No pending deploy confirmation.")
        return

    await record_deploy_decision(active["project_id"], "confirm")
    await update.message.reply_text("✅ Deployment confirmed. Starting S6...")


@require_auth
async def cmd_deploy_cancel(update: Any, context: Any):
    """§4.6.3 (FIX-08): /deploy_cancel — Cancel deployment."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No pending deploy to cancel.")
        return

    await record_deploy_decision(active["project_id"], "cancel")
    await update.message.reply_text("❌ Deployment cancelled. Returned to S5.")


@require_auth
async def cmd_setup(update: Any, context: Any):
    """§7.1.2: /setup — Run the setup wizard to configure API keys."""
    user_id = str(update.effective_user.id)

    async def send_to_operator(text: str) -> None:
        await update.message.reply_text(text, parse_mode="Markdown")

    from factory.setup.wizard import run_setup_wizard
    await run_setup_wizard(operator_id=user_id, send_message=send_to_operator)


@require_auth
async def cmd_help(update: Any, context: Any):
    """§5.2: /help — Show all commands."""
    await update.message.reply_text(format_help_message())


# ═══════════════════════════════════════════════════════════════════
# §5.3 Callback Handler
# ═══════════════════════════════════════════════════════════════════


async def handle_callback(update: Any, context: Any):
    """Handle inline keyboard callbacks.

    Spec: §5.3
    Dispatches based on callback_data prefix.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = str(query.from_user.id)

    if data.startswith("mode_"):
        mode = data.replace("mode_", "")
        active = await get_active_project(user_id)
        if active:
            state = PipelineState.model_validate(active["state_json"])
            state.execution_mode = ExecutionMode(mode)
            await update_project_state(state)
            emoji_map = {"cloud": "☁️", "local": "💻", "hybrid": "🔀"}
            await query.edit_message_text(
                f"{emoji_map.get(mode, '')} {mode.upper()}"
            )

    elif data.startswith("restore_confirm_"):
        parts = data.split("_")
        await query.edit_message_text("⏪ Restoring... (stub for dry-run)")

    elif data.startswith("cancel_confirm_"):
        pid = data.replace("cancel_confirm_", "")
        await archive_project(pid)
        await query.edit_message_text(f"🗑️ {pid} archived.")

    elif data.startswith("decision_"):
        payload = data.replace("decision_", "")
        await store_operator_decision(user_id, payload)
        await query.edit_message_text(f"✅ Decision recorded.")

    elif data in ("project_continue", "project_archive_new", "cancel_abort", "restore_cancel"):
        await query.edit_message_text("OK.")


# ═══════════════════════════════════════════════════════════════════
# §5.3 Free-Text Handler
# ═══════════════════════════════════════════════════════════════════


async def handle_message(update: Any, context: Any):
    """Handle free-text messages (project descriptions, etc.).

    Spec: §5.3
    If operator is in 'awaiting_project_description' state,
    treat the message as a project brief. Otherwise, provide guidance.
    """
    if not await authenticate_operator(update):
        return

    user_id = str(update.effective_user.id)

    # §7.1.2 — Intercept if wizard is awaiting a free-text reply
    from factory.telegram.decisions import has_pending_reply, resolve_reply
    if update.message and update.message.text and has_pending_reply(user_id):
        resolved = await resolve_reply(user_id, update.message.text.strip())
        if resolved:
            return  # Wizard captured this message

    op_state = await get_operator_state(user_id)

    if op_state == "awaiting_project_description":
        desc = update.message.text or ""
        await clear_operator_state(user_id)
        await _start_project(update, user_id, desc)
    else:
        # Treat as implicit /new
        text = update.message.text or ""
        if len(text) > 20:
            await _start_project(update, user_id, text)
        else:
            await update.message.reply_text(
                "Send a project description, or use /help."
            )


# ═══════════════════════════════════════════════════════════════════
# Project Launcher
# ═══════════════════════════════════════════════════════════════════


async def _start_project(
    update: Any,
    user_id: str,
    description: str,
    attachments: Optional[list] = None,
) -> None:
    """Create and launch a new pipeline project.

    Spec: §5.2 (/new → _start_project)
    """
    import uuid

    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    prefs = await get_operator_preferences(user_id)

    state = PipelineState(
        project_id=project_id,
        operator_id=user_id,
        autonomy_mode=AutonomyMode(
            prefs.get("autonomy_mode", "autopilot"),
        ),
        execution_mode=ExecutionMode(
            prefs.get("execution_mode", "cloud"),
        ),
        project_metadata={
            "raw_input": description,
            "attachments": attachments or [],
        },
    )

    await update_project_state(state)
    await update.message.reply_text(
        format_project_started(project_id, state)
    )

    logger.info(
        f"[{project_id}] Project started by {user_id}: "
        f"{description[:100]}..."
    )


# ═══════════════════════════════════════════════════════════════════
# §5.1 Bot Setup
# ═══════════════════════════════════════════════════════════════════


async def setup_bot() -> Any:
    """Build and configure the Telegram bot application.

    Spec: §5.1.1
    Registers all 16 commands + callback + message handlers.

    Returns:
        Configured telegram.ext.Application (or mock for dry-run).
    """
    try:
        from telegram.ext import (
            Application,
            CommandHandler,
            MessageHandler,
            CallbackQueryHandler,
            filters,
        )
        from factory.core.secrets import get_secret

        token = get_secret("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — bot in dry-run mode")
            return None

        app = Application.builder().token(token).build()

        # ── Project lifecycle ──
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("new", cmd_new_project))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("cost", cmd_cost))

        # ── Execution control ──
        app.add_handler(CommandHandler("mode", cmd_mode))
        app.add_handler(CommandHandler("autonomy", cmd_autonomy))

        # ── Time travel ──
        app.add_handler(CommandHandler("restore", cmd_restore))
        app.add_handler(CommandHandler("snapshots", cmd_snapshots))

        # ── Pipeline flow ──
        app.add_handler(CommandHandler("continue", cmd_continue))
        app.add_handler(CommandHandler("cancel", cmd_cancel))

        # ── Deploy gate (FIX-08) ──
        app.add_handler(CommandHandler("deploy_confirm", cmd_deploy_confirm))
        app.add_handler(CommandHandler("deploy_cancel", cmd_deploy_cancel))

        # ── Diagnostics ──
        app.add_handler(CommandHandler("warroom", cmd_warroom))
        app.add_handler(CommandHandler("legal", cmd_legal))
        app.add_handler(CommandHandler("setup", cmd_setup))
        app.add_handler(CommandHandler("help", cmd_help))

        # ── Inline callbacks ──
        app.add_handler(CallbackQueryHandler(handle_callback))

        # ── Free-text + media ──
        app.add_handler(MessageHandler(
            filters.TEXT | filters.PHOTO
            | filters.Document.ALL | filters.VOICE,
            handle_message,
        ))

        set_bot_instance(app.bot)
        logger.info("Telegram bot configured with 16 command handlers")
        return app

    except ImportError as e:
        logger.warning(f"python-telegram-bot not available: {e}")
        return None


async def run_bot_polling() -> None:
    """Run the Telegram bot in polling mode (local dev, no webhook required).

    Spec: §5.1.1 — polling is the local-dev alternative to the production webhook.
    Use when Cloud Run is not yet deployed.

    Run: python scripts/run_bot.py
    """
    app = await setup_bot()
    if app is None:
        logger.error(
            "Bot not configured — set TELEGRAM_BOT_TOKEN and try again."
        )
        return
    logger.info("Starting Telegram bot in polling mode (Ctrl+C to stop)…")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    # Block until Ctrl+C
    import asyncio
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Bot stopped.")