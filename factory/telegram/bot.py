"""
AI Factory Pipeline v5.8 — Telegram Bot Setup

Implements:
  - §5.1 Bot architecture (registration, webhook, polling)
  - §5.1.2 Operator authentication (whitelist from Supabase)
  - §5.2 Command handler registration (16 commands)
  - §5.3 Callback handler + free-text handler

Spec Authority: v5.8 §5.1–§5.3
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
from factory.core.mode_router import MasterMode, mode_selection_message
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
# Background Task Registry — prevents asyncio tasks from being GC'd
# before completion.  asyncio.create_task() returns a Task; if no
# reference is kept Python may collect it mid-run, silently killing
# the pipeline.  All long-running fire-and-forget tasks go here.
# ═══════════════════════════════════════════════════════════════════

_background_tasks: set = set()

# Per-project task registry — maps project_id → asyncio.Task
# Allows /cancel to actually cancel a running pipeline coroutine.
_project_tasks: dict = {}


def _bg(coro) -> "asyncio.Task":
    """Create a background task and keep a hard reference until it finishes."""
    import asyncio as _asyncio
    task = _asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def register_project_task(project_id: str, task: "asyncio.Task") -> None:
    """Register a pipeline task under its project_id.

    Stores in _project_tasks (for cancellation) and _background_tasks
    (for GC-prevention).  Replaces any previous task for the same project_id.
    """
    _project_tasks[project_id] = task
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(lambda _t: _project_tasks.pop(project_id, None))


def cancel_project_task(project_id: str) -> bool:
    """Cancel the asyncio.Task running the pipeline for project_id.

    Returns True if a task was found and cancel() was called,
    False if no task existed or the task was already done.
    """
    import asyncio as _asyncio
    task = _project_tasks.get(project_id)
    if task is None:
        return False
    if task.done():
        _project_tasks.pop(project_id, None)
        return False
    task.cancel()
    _project_tasks.pop(project_id, None)
    logger.info(f"[{project_id}] Pipeline task cancellation requested via cancel_project_task")
    return True


# ═══════════════════════════════════════════════════════════════════
# §5.1.2 Operator Authentication
# ═══════════════════════════════════════════════════════════════════


async def authenticate_operator(update: Any) -> bool:
    """Check if the Telegram user is the authorized operator.

    Spec: §5.1.2
    Layer 1 (fast): hardcoded operator ID check — unknown users get complete
    silence (no error reply, no acknowledgment, nothing discoverable).
    Layer 2 (Supabase): whitelist check for future multi-operator support.
    """
    from factory.telegram.ai_handler import is_operator
    user_id = str(update.effective_user.id)

    # Layer 1 — hardcoded exclusive access (silent reject for strangers)
    if not is_operator(user_id):
        logger.warning(f"Rejected unknown user {user_id} — silent drop")
        return False  # NO reply — bot is invisible to strangers

    # Layer 2 — Supabase whitelist (skipped if Supabase unavailable)
    try:
        from factory.integrations.supabase import check_operator_whitelist
        allowed = await check_operator_whitelist(user_id)
        if not allowed:
            logger.warning(f"Operator {user_id} in hardcoded list but not in Supabase whitelist")
            # Allow anyway — hardcoded list is authoritative
        return True
    except Exception:
        logger.debug(f"Supabase whitelist skipped for {user_id}")
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
        from factory.telegram.messages import project_display_name
        await update.message.reply_text(
            f"📋 Active project: {project_display_name(active)} "
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
    """§5.2: /mode — Show or set Master Execution Mode (v5.8)."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])
    arg = (context.args[0].lower() if context.args else "").strip()

    _MASTER_MODES = {"basic", "balanced", "custom", "turbo"}
    _EXEC_MODES = {"cloud", "local", "hybrid"}

    if arg in _MASTER_MODES:
        state.master_mode = MasterMode(arg)
        await update_project_state(state)
        mm = state.master_mode
        await update.message.reply_text(
            f"{mm.emoji} Master mode set to *{mm.label}*."
        )
    elif arg in _EXEC_MODES:
        # Backwards-compat: still allow /mode cloud|local|hybrid
        state.execution_mode = ExecutionMode(arg)
        await update_project_state(state)
        emoji_map = {"cloud": "☁️", "local": "💻", "hybrid": "🔀"}
        await update.message.reply_text(
            f"{emoji_map[arg]} Execution mode: {arg.upper()}."
        )
    else:
        mm = state.master_mode
        em = state.execution_mode
        await update.message.reply_text(
            f"{mm.emoji} *Master mode*: {mm.label}\n"
            f"☁️ *Execution*: {em.value}\n\n"
            f"Set master mode: /mode basic | balanced | custom | turbo\n"
            f"Set exec mode:   /mode cloud | local | hybrid"
        )


@require_auth
async def cmd_switch_mode(update: Any, context: Any):
    """v5.8: /switch_mode — Alias for /mode (set Master Execution Mode)."""
    await cmd_mode(update, context)


@require_auth
async def cmd_quota(update: Any, context: Any):
    """v5.8: /quota — Show per-provider quota usage."""
    from factory.core.quota_tracker import get_quota_tracker
    tracker = get_quota_tracker()
    lines = tracker.usage_summary()
    if lines:
        body = "\n".join(lines)
        soonest = tracker.soonest_reset()
        reset_note = (
            f"\nNext reset: {soonest.strftime('%Y-%m-%d %H:%M UTC')}"
            if soonest else ""
        )
        await update.message.reply_text(
            f"📊 *Provider Quota Usage*\n\n```\n{body}\n```{reset_note}"
        )
    else:
        await update.message.reply_text("No quota data yet.")


@require_auth
async def cmd_autonomy(update: Any, context: Any):
    """§5.2: /autonomy — Toggle Autopilot/Copilot."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)

    if not active:
        prefs = get_operator_preferences(user_id)
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

    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project to restore.")
        return

    project_id = active["project_id"]
    from factory.telegram.messages import project_display_name
    _display = project_display_name(active)
    await update.message.reply_text(f"⏪ Restoring snapshot #{snapshot_id} for {_display}...")
    try:
        from factory.integrations.supabase import restore_state
        restored = await restore_state(project_id, snapshot_id)
        if restored is None:
            await update.message.reply_text(f"Snapshot #{snapshot_id} not found.")
            return
        await update_project_state(restored)
        await update.message.reply_text(
            f"✅ Restored to snapshot #{snapshot_id} — stage: {restored.current_stage.value}\n"
            f"Use /continue to resume or /status to check."
        )
    except ValueError as e:
        await update.message.reply_text(f"⚠️ Restore failed: {e}")
    except Exception as e:
        logger.error(f"Restore error: {e}", exc_info=True)
        await update.message.reply_text(f"Restore error — check logs.")


@require_auth
async def cmd_snapshots(update: Any, context: Any):
    """§5.2: /snapshots — List time-travel snapshots."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project. /new to start.")
        return

    project_id = active["project_id"]
    try:
        from factory.integrations.supabase import list_snapshots
        snaps = await list_snapshots(project_id, limit=10)
        if not snaps:
            await update.message.reply_text("No snapshots yet for this project.")
            return
        from factory.telegram.messages import project_display_name
        lines = [f"📸 Snapshots for {project_display_name(active)}:\n"]
        for s in snaps:
            lines.append(
                f"  State_#{s['snapshot_id']} — {s.get('stage', '?')} "
                f"({s.get('created_at', '')[:16]})"
            )
        lines.append("\nUse /restore State_#N to restore.")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"Snapshots error: {e}", exc_info=True)
        await update.message.reply_text("Could not fetch snapshots — check logs.")


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
    resume_stage = state.current_stage.value
    await update.message.reply_text(
        f"▶️ Resuming from `{resume_stage}`…",
        parse_mode="Markdown",
    )

    async def _run_continue():
        try:
            from factory.orchestrator import resume_pipeline
            from factory.telegram.notifications import send_telegram_message
            final = await resume_pipeline(state)
            if final.current_stage.value == "halted":
                reason = (
                    final.project_metadata.get("halt_reason")
                    or final.legal_halt_reason
                    or "no diagnostic detail captured"
                )
                await send_telegram_message(
                    user_id,
                    f"⛔ Pipeline halted at `{resume_stage}`: {reason}",
                )
            else:
                await send_telegram_message(
                    user_id,
                    f"✅ Pipeline resumed and completed from `{resume_stage}`!\n"
                    f"Use /status to view results.",
                )
        except Exception as e:
            logger.error(f"[/continue] resume_pipeline error: {e}", exc_info=True)
            try:
                from factory.telegram.notifications import send_telegram_message
                await send_telegram_message(
                    user_id, f"⚠️ Resume error: {e}"
                )
            except Exception:
                pass

    cont_task = _bg(_run_continue())
    register_project_task(state.project_id, cont_task)


@require_auth
async def cmd_cancel(update: Any, context: Any):
    """§5.2: /cancel — Cancel and archive project."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    project_id = active["project_id"]
    from factory.telegram.messages import project_display_name
    display = project_display_name(active)
    await archive_project(project_id)
    await update.message.reply_text(
        f"🗑️ {display} archived. Snapshots preserved."
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

    await record_deploy_decision(active["project_id"], user_id, True)
    await update.message.reply_text("✅ Deployment confirmed. Starting S6...")


@require_auth
async def cmd_deploy_cancel(update: Any, context: Any):
    """§4.6.3 (FIX-08): /deploy_cancel — Cancel deployment."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No pending deploy to cancel.")
        return

    await record_deploy_decision(active["project_id"], user_id, False)
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
async def cmd_providers(update: Any, context: Any):
    """Show AI provider + memory backend chain status."""
    from factory.integrations.provider_chain import ai_chain, scout_chain
    from factory.memory.mother_memory import get_memory_chain_status
    import time

    def _format_ai_chain(chain) -> str:
        lines = []
        active = chain.get_active()
        for name in chain.chain:
            s = chain.statuses[name]
            if s.quota_exhausted and s.quota_reset_at:
                eta = int(s.quota_reset_at - time.time())
                h, m = divmod(max(eta, 0), 3600)
                mins = m // 60
                lines.append(f"  ⏳ {name}: quota — resets in {h}h {mins}m")
            elif not s.available:
                err = s.last_error[:40] if s.last_error else "unavailable"
                lines.append(f"  ❌ {name}: {err}")
            elif name == active:
                lines.append(f"  ✅ {name}: ACTIVE ← currently in use")
            else:
                lines.append(f"  ⬜ {name}: ready (standby)")
        return "\n".join(lines)

    def _format_memory_chain() -> str:
        statuses = get_memory_chain_status()
        if not statuses:
            return "  ⬜ not yet initialized"
        lines = []
        for s in statuses:
            name = s["name"]
            pending = s.get("pending_writes", 0)
            pend_str = f" ({pending} pending)" if pending else ""
            if s.get("quota_exhausted") and s.get("quota_resets_in") is not None:
                eta = s["quota_resets_in"]
                h, m = divmod(eta, 3600)
                mins = m // 60
                lines.append(f"  ⏳ {name}: quota — resets in {h}h {mins}m{pend_str}")
            elif not s["available"]:
                err_ct = s.get("consecutive_errors", 0)
                lines.append(f"  ❌ {name}: offline ({err_ct} errors){pend_str}")
            elif s == statuses[0]:  # first available = read-primary
                lines.append(f"  ✅ {name}: ACTIVE (read-primary + write){pend_str}")
            else:
                lines.append(f"  💾 {name}: write-mirror (standby read){pend_str}")
        return "\n".join(lines)

    msg = (
        "🤖 AI Provider Chain:\n"
        + _format_ai_chain(ai_chain)
        + "\n\n🔍 Scout Chain:\n"
        + _format_ai_chain(scout_chain)
        + "\n\n🧠 Mother Memory Chain (fan-out writes):\n"
        + _format_memory_chain()
        + "\n\n_All chains auto-recover when quotas reset.\n"
        "Higher-priority backends always take priority once available._"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@require_auth
async def cmd_help(update: Any, context: Any):
    """§5.2: /help — Show all commands."""
    await update.message.reply_text(format_help_message())


# ── Mode switching (local ↔ online) ──────────────────────────────

@require_auth
async def cmd_online(update: Any, context: Any):
    """Switch bot to Render webhook mode for up to 12 hours."""
    # Signal run_bot.py runner if it's active
    runner = _get_runner()
    if runner is not None:
        go_online, _ = runner.get_mode_events()
        await update.message.reply_text(
            "🌐 Switching to ONLINE mode (Render webhook).\n"
            "Auto-reverts in 12 hours or send /local to revert now."
        )
        go_online.set()
    else:
        # Called from Render (already online) or runner not attached
        await update.message.reply_text(
            "ℹ️  Already running online (Render webhook mode).\n"
            "Send /local to switch back to local polling."
        )


@require_auth
async def cmd_local(update: Any, context: Any):
    """Switch bot back to local polling mode (removes webhook)."""
    import urllib.request as _ur, json as _json, os as _os
    token = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Remove webhook directly — works whether called from Render or locally
    try:
        req = _ur.Request(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            data=b"drop_pending_updates=true",
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with _ur.urlopen(req, timeout=10) as r:
            ok = _json.loads(r.read()).get("ok", False)
    except Exception as e:
        ok = False
        logger.error(f"deleteWebhook error: {e}")

    # Signal run_bot.py runner if active
    runner = _get_runner()
    if runner is not None:
        _, go_local = runner.get_mode_events()
        go_local.set()

    if ok:
        await update.message.reply_text(
            "🏠 Switched to LOCAL polling mode.\n"
            "Run `python scripts/run_bot.py` on your machine if not already running.\n"
            "Send /online to go back online."
        )
    else:
        await update.message.reply_text("⚠️  Could not remove webhook — check logs.")


def _get_runner():
    """Return the run_bot module if it attached itself (local runner only)."""
    try:
        import sys
        mod = sys.modules.get("__main__")
        if mod and hasattr(mod, "get_mode_events"):
            return mod
        # Also check if run_bot module registered itself
        bot_mod = sys.modules.get(__name__)
        runner_mod = getattr(bot_mod, "_runner_module", None)
        return runner_mod
    except Exception:
        return None


# Module-level slot for run_bot.py to attach itself
_runner_module = None


@require_auth
async def cmd_admin(update: Any, context: Any):
    """Admin override commands: budget_override, reset_retries, dump_state."""
    user_id = str(update.effective_user.id)
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "🔧 Admin commands:\n"
            "  /admin budget_override <USD>  — raise budget cap\n"
            "  /admin reset_retries           — reset S5→S3 retry count\n"
            "  /admin dump_state              — raw state JSON\n"
            "  /admin force_stage <STAGE>     — jump to stage\n"
            "  /admin clear_halt              — clear legal/circuit halt"
        )
        return

    active = await get_active_project(user_id)
    subcmd = args[0].lower()

    if subcmd == "budget_override":
        if len(args) < 2:
            await update.message.reply_text("Usage: /admin budget_override <USD>")
            return
        try:
            new_limit = float(args[1])
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return
        if not active:
            await update.message.reply_text("No active project.")
            return
        state = PipelineState.model_validate(active["state_json"])
        state.budget_limit_usd = new_limit
        state.circuit_breaker_triggered = False
        await update_project_state(state)
        await update.message.reply_text(f"✅ Budget cap raised to ${new_limit:.2f}")

    elif subcmd == "reset_retries":
        if not active:
            await update.message.reply_text("No active project.")
            return
        state = PipelineState.model_validate(active["state_json"])
        state.retry_count = 0
        await update_project_state(state)
        await update.message.reply_text("✅ Retry count reset to 0.")

    elif subcmd == "dump_state":
        if not active:
            await update.message.reply_text("No active project.")
            return
        import json
        state = PipelineState.model_validate(active["state_json"])
        raw = json.dumps(state.model_dump(mode="json"), indent=2)
        # Telegram 4096 char limit
        for chunk in [raw[i:i+3900] for i in range(0, min(len(raw), 12000), 3900)]:
            await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")

    elif subcmd == "force_stage":
        if len(args) < 2:
            await update.message.reply_text("Usage: /admin force_stage <STAGE_NAME>")
            return
        if not active:
            await update.message.reply_text("No active project.")
            return
        try:
            target = Stage(args[1].upper())
        except ValueError:
            valid = [s.value for s in Stage]
            await update.message.reply_text(f"Unknown stage. Valid: {', '.join(valid)}")
            return
        state = PipelineState.model_validate(active["state_json"])
        state.previous_stage = state.current_stage
        state.current_stage = target
        state.legal_halt = False
        state.circuit_breaker_triggered = False
        await update_project_state(state)
        await update.message.reply_text(f"✅ Forced stage to {target.value}")

    elif subcmd == "clear_halt":
        if not active:
            await update.message.reply_text("No active project.")
            return
        state = PipelineState.model_validate(active["state_json"])
        state.legal_halt = False
        state.legal_halt_reason = None
        state.circuit_breaker_triggered = False
        await update_project_state(state)
        await update.message.reply_text("✅ Halts cleared. Use /continue to resume.")

    else:
        await update.message.reply_text(f"Unknown admin command: {subcmd}. See /admin for help.")


@require_auth
async def cmd_force_continue(update: Any, context: Any):
    """/force_continue <reason> — override a legal halt with explicit acceptance."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    reason = " ".join(context.args) if context.args else ""
    if not reason or len(reason) < 10:
        await update.message.reply_text(
            "Usage: /force_continue <explicit reason>\n\n"
            "Example: /force_continue I accept compliance risk for internal testing\n\n"
            "You must provide a reason of at least 10 characters."
        )
        return

    state = PipelineState.model_validate(active["state_json"])
    if not state.legal_halt and not state.circuit_breaker_triggered:
        await update.message.reply_text("Pipeline is not halted — nothing to override.")
        return

    halt_reason = state.legal_halt_reason or "circuit breaker"
    state.legal_halt = False
    state.legal_halt_reason = None
    state.circuit_breaker_triggered = False
    if state.current_stage == Stage.HALTED and state.previous_stage:
        state.current_stage = state.previous_stage

    # Log the override
    state.legal_checks_log.append({
        "check": "force_continue_override",
        "stage": state.current_stage.value,
        "phase": "operator",
        "passed": True,
        "reason": reason,
        "overridden_halt": halt_reason,
    })

    await update_project_state(state)
    logger.warning(
        f"[{state.project_id}] FORCE_CONTINUE by {user_id}: "
        f"overrode '{halt_reason}' — reason: {reason}"
    )
    await update.message.reply_text(
        f"⚠️ Legal halt overridden.\n"
        f"Halted reason was: {halt_reason}\n"
        f"Your acceptance: {reason}\n\n"
        f"Resuming from {state.current_stage.value}...\n"
        f"Use /continue to trigger execution."
    )


@require_auth
async def cmd_budget(update: Any, context: Any):
    """/budget [new_limit] — show or set project budget."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project.")
        return

    state = PipelineState.model_validate(active["state_json"])

    if context.args:
        try:
            new_limit = float(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /budget <USD amount>")
            return
        state.budget_limit_usd = new_limit
        state.circuit_breaker_triggered = False
        await update_project_state(state)
        await update.message.reply_text(
            f"💰 Budget updated: ${new_limit:.2f}\n"
            f"Spent so far: ${state.total_cost_usd:.4f}"
        )
    else:
        from factory.telegram.messages import format_cost_message
        await update.message.reply_text(format_cost_message(state))


@require_auth
async def cmd_modify(update: Any, context: Any):
    """§5.2: /modify <repo_url> <description> — Modify an existing codebase.

    Usage: /modify https://github.com/org/repo Add dark mode to the settings screen
    """
    user_id = str(update.effective_user.id)

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /modify <repo_url> <change description>\n\n"
            "Example: /modify https://github.com/org/repo Add a dark mode toggle"
        )
        return

    repo_url = context.args[0]
    description = " ".join(context.args[1:])

    if not repo_url.startswith(("https://", "git@", "http://")):
        await update.message.reply_text(
            f"Invalid repo URL: {repo_url}\n"
            "Provide a full GitHub/GitLab URL."
        )
        return

    active = await get_active_project(user_id)
    if active:
        from factory.telegram.messages import project_display_name
        await update.message.reply_text(
            f"Active project {project_display_name(active)} in progress.\n"
            "Use /cancel first, then /modify."
        )
        return

    import uuid
    project_id = f"mod_{uuid.uuid4().hex[:8]}"
    prefs = get_operator_preferences(user_id)

    from factory.core.state import PipelineMode
    state = PipelineState(
        project_id=project_id,
        operator_id=user_id,
        autonomy_mode=AutonomyMode(prefs.get("autonomy_mode", "autopilot")),
        execution_mode=ExecutionMode(prefs.get("execution_mode", "cloud")),
        pipeline_mode=PipelineMode.MODIFY,
        source_repo_url=repo_url,
        modification_description=description,
        project_metadata={
            "raw_input": description,
            "repo_url": repo_url,
            "attachments": [],
        },
    )

    await update_project_state(state)
    # Issue 15: MODIFY is the only place a project id appears before the
    # app name exists. Show the repo name (human-recognizable) prominently
    # and keep the id as a parenthetical so logs remain cross-referenceable.
    _repo_display = repo_url.rstrip("/").split("/")[-1] or "repo"
    await update.message.reply_text(
        f"MODIFY mode started for {_repo_display}\n\n"
        f"Repo: {repo_url}\n"
        f"Change: {description[:200]}\n\n"
        "Cloning repo and analyzing codebase..."
    )

    import asyncio

    async def _run_modify():
        try:
            from factory.orchestrator import run_pipeline
            from factory.telegram.notifications import send_telegram_message
            final = await run_pipeline(state)
            if final.current_stage.value == "halted":
                reason = (
                    final.project_metadata.get("halt_reason")
                    or final.legal_halt_reason
                    or "no diagnostic detail captured"
                )
                from factory.telegram.messages import project_display_name
                _display = project_display_name(final)
                await send_telegram_message(user_id, f"MODIFY halted for {_display}: {reason}")
            else:
                from factory.telegram.messages import project_display_name
                _display = project_display_name(final)
                await send_telegram_message(
                    user_id,
                    f"MODIFY complete for {_display}! Use /status to see the diff."
                )
        except Exception as e:
            logger.error(f"[{project_id}] MODIFY error: {e}")
            try:
                from factory.telegram.notifications import send_telegram_message
                from factory.telegram.messages import project_display_name as _pdn
                await send_telegram_message(user_id, f"MODIFY error for {_pdn(state)}: {e}")
            except Exception:
                pass

    mod_task = _bg(_run_modify())
    register_project_task(project_id, mod_task)


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
        # data format: "restore_confirm_{snapshot_id}"
        try:
            snapshot_id = int(data.split("restore_confirm_")[1])
        except (ValueError, IndexError):
            await query.edit_message_text("⚠️ Invalid restore snapshot ID.")
            return
        active = await get_active_project(user_id)
        if not active:
            await query.edit_message_text("No active project to restore.")
            return
        project_id = active["project_id"]
        from factory.telegram.messages import project_display_name
        _display = project_display_name(active)
        await query.edit_message_text(
            f"⏪ Restoring snapshot #{snapshot_id} for {_display}…",
        )
        try:
            from factory.integrations.supabase import restore_state
            restored = await restore_state(project_id, snapshot_id)
            if restored is None:
                await query.edit_message_text(
                    f"❌ Snapshot #{snapshot_id} not found for {_display}.",
                )
                return
            await update_project_state(restored)
            await query.edit_message_text(
                f"✅ Restored to snapshot #{snapshot_id} — "
                f"stage: `{restored.current_stage.value}`\n"
                f"Use /continue to resume or /status to check.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Restore callback error: {e}", exc_info=True)
            await query.edit_message_text("⚠️ Restore error — check logs.")

    elif data.startswith("cancel_confirm_"):
        pid = data.replace("cancel_confirm_", "")
        await archive_project(pid)
        await query.edit_message_text(f"🗑️ {pid} archived.")

    elif data.startswith("decision_"):
        payload = data.replace("decision_", "")
        await store_operator_decision(user_id, payload)
        await query.edit_message_text(f"✅ Decision recorded.")

    elif data.startswith("select_name:"):
        # Format: select_name:{app_name}||{description}
        payload = data[len("select_name:"):]
        parts = payload.split("||", 1)
        chosen_name = parts[0].strip()
        description = parts[1] if len(parts) > 1 else ""
        await query.edit_message_text(
            f"✅ App name set: *{chosen_name}*\n\nStarting the pipeline...",
            parse_mode="Markdown",
        )
        # We need an update-like object — use query.message as a proxy
        class _FakeUpdate:
            message = query.message
            effective_user = query.from_user
        await _start_project(_FakeUpdate(), user_id, description, app_name=chosen_name)

    elif data in ("project_continue", "project_archive_new", "cancel_abort", "restore_cancel"):
        await query.edit_message_text("OK.")

    elif data.startswith("logo_update:"):
        action = data[len("logo_update:"):]
        active = await get_active_project(user_id)
        if not active:
            await query.edit_message_text("No active project.")
            return

        if action == "auto":
            await query.edit_message_text(
                "Generating logo... (~1-2 minutes). You'll receive it when ready."
            )
            state = PipelineState.model_validate(active["state_json"])

            async def _gen_logo():
                try:
                    from factory.pipeline.s0_intake import _logo_flow_auto
                    s0_out = state.s0_output or {}
                    logo_asset = await _logo_flow_auto(state, s0_out)
                    if logo_asset:
                        state.brand_assets.append(logo_asset)
                        await update_project_state(state)
                except Exception as e:
                    logger.error(f"Auto logo gen error: {e}")
                    try:
                        from factory.telegram.notifications import send_telegram_message
                        await send_telegram_message(
                            user_id, f"Logo generation failed: {e}"
                        )
                    except Exception:
                        pass

            _bg(_gen_logo())

        elif action == "upload":
            await set_operator_state(
                user_id, "awaiting_logo_photo",
                {"project_id": active["project_id"]},
            )
            await query.edit_message_text(
                "Send me your logo image (PNG/JPG):"
            )

        elif action == "cancel":
            await clear_operator_state(user_id)
            await query.edit_message_text("Logo update cancelled.")


# ═══════════════════════════════════════════════════════════════════
# §5.3 Free-Text Handler
# ═══════════════════════════════════════════════════════════════════


async def handle_message(update: Any, context: Any):
    """Intelligent message handler — AI-powered intent routing.

    Spec: §5.3
    Flow:
      1. Silent reject for non-operators (no reply at all)
      2. Rate limit check
      3. Prompt injection protection
      4. Wizard / pending reply intercept
      5. Confirmation intercept (for destructive actions)
      6. Gemini intent classification
      7. Route to appropriate action
    """
    if not await authenticate_operator(update):
        return  # Silent — strangers see nothing

    from factory.telegram.ai_handler import (
        _check_rate_limit, _is_injection_attempt, _sanitize,
        classify_intent, ai_respond, has_pending_confirmation,
        pop_confirmation, request_confirmation, _add_to_history,
        load_history_from_memory,
    )

    user_id = str(update.effective_user.id)
    raw_text = (update.message.text or "").strip()

    # ── Pre-warm conversation history from Mother Memory on first message ──
    await load_history_from_memory(user_id)

    # ── Rate limit ──
    if not _check_rate_limit(user_id):
        await update.message.reply_text(
            "Slow down — you're sending messages too fast. Wait a moment."
        )
        return

    # ── Prompt injection protection ──
    if _is_injection_attempt(raw_text):
        logger.warning(f"Prompt injection attempt from {user_id}: {raw_text[:100]}")
        await update.message.reply_text(
            "That looks like an attempt to override my instructions. "
            "I won't act on that."
        )
        return

    text = _sanitize(raw_text)

    # ── Wizard intercept (setup wizard free-text replies) ──
    from factory.telegram.decisions import has_pending_reply, resolve_reply
    if update.message and text and has_pending_reply(user_id):
        resolved = await resolve_reply(user_id, text)
        if resolved:
            return

    # ── Operator state: awaiting project description ──
    # get_operator_state returns {"state": str, "context": {}} or None
    op_state = await get_operator_state(user_id)
    if isinstance(op_state, dict) and op_state.get("state") == "awaiting_project_description":
        await clear_operator_state(user_id)
        await _handle_start_project_intent(update, user_id, text)
        return

    if isinstance(op_state, dict) and op_state.get("state") == "awaiting_app_name":
        ctx = op_state.get("context", {})
        description = ctx.get("description", "")
        attachments = ctx.get("attachments", [])
        await clear_operator_state(user_id)
        name_input = text.strip()
        if name_input.lower() in ("skip", "/skip", "s", ""):
            await _suggest_app_names(update, user_id, description, attachments)
        else:
            await _start_project(update, user_id, description, attachments, app_name=name_input)
        return

    # ── Operator state: awaiting logo (from /update_logo) ──
    if isinstance(op_state, dict) and op_state.get("state") in (
        "awaiting_logo", "awaiting_logo_photo",
    ):
        ctx = op_state.get("context", {})
        active = await get_active_project(user_id)

        # Photo received → store as logo
        if update.message and update.message.photo and active:
            await clear_operator_state(user_id)
            await update.message.reply_text("📥 Saving your logo...")
            try:
                photo = update.message.photo[-1]  # highest resolution
                tg_file = await context.bot.get_file(photo.file_id)
                import io as _io
                buf = _io.BytesIO()
                await tg_file.download_to_memory(buf)
                logo_bytes = buf.getvalue()

                state = PipelineState.model_validate(active["state_json"])
                state.brand_assets.append({
                    "asset_type": "logo",
                    "logo_bytes_len": len(logo_bytes),
                    "source": "upload",
                })
                if state.project_metadata.get("logo_pending"):
                    del state.project_metadata["logo_pending"]
                await update_project_state(state)
                await update.message.reply_text(
                    "✅ Logo saved! It will be used in the build."
                )
            except Exception as e:
                logger.error(f"Logo upload error: {e}")
                await update.message.reply_text(f"Failed to save logo: {e}")
            return

        # Text: "auto" → generate, "cancel" → abort
        if text:
            cmd = text.strip().lower()
            await clear_operator_state(user_id)
            if cmd in ("auto", "generate", "gen") and active:
                await update.message.reply_text(
                    "Generating logo... (~1-2 minutes). You'll receive it when ready."
                )
                state = PipelineState.model_validate(active["state_json"])

                async def _gen():
                    try:
                        from factory.pipeline.s0_intake import _logo_flow_auto
                        s0_out = state.s0_output or {}
                        asset = await _logo_flow_auto(state, s0_out)
                        if asset:
                            state.brand_assets.append(asset)
                            await update_project_state(state)
                    except Exception as exc:
                        logger.error(f"Logo auto-gen failed: {exc}")

                _bg(_gen())
            elif cmd not in ("cancel", "skip", "no"):
                # Treat as description
                if active:
                    await update.message.reply_text(
                        "Generating logo from your description... (~1-2 minutes)"
                    )
                    state = PipelineState.model_validate(active["state_json"])

                    async def _gen_desc():
                        try:
                            from factory.integrations.image_gen import generate_image
                            from factory.telegram.notifications import get_bot
                            import io as _io
                            prompt = f"{cmd} app icon for {state.idea_name or 'App'}"
                            img = await generate_image(prompt=prompt, width=1024, height=1024)
                            if img:
                                bot_inst = get_bot()
                                if bot_inst:
                                    await bot_inst.send_photo(
                                        chat_id=int(user_id),
                                        photo=_io.BytesIO(img),
                                        caption="🎨 Logo from your description. Use /update_logo to change.",
                                    )
                                state.brand_assets.append({
                                    "asset_type": "logo",
                                    "logo_bytes_len": len(img),
                                    "source": "described",
                                })
                                await update_project_state(state)
                        except Exception as exc:
                            logger.error(f"Logo desc-gen failed: {exc}")

                    _bg(_gen_desc())
                else:
                    await update.message.reply_text("Logo update cancelled.")
            else:
                await update.message.reply_text("Logo update cancelled.")
        return

    # ── Confirmation intercept (yes/no for destructive actions) ──
    if has_pending_confirmation(user_id):
        if text.lower().strip() in ("yes", "y", "confirm", "ok", "sure", "do it"):
            action = pop_confirmation(user_id)
            await _execute_confirmed_action(update, user_id, action)
        else:
            pop_confirmation(user_id)
            await update.message.reply_text("Cancelled. Nothing was changed.")
        return

    # ── AI intent classification + routing ──
    if not text:
        return

    active = await get_active_project(user_id)

    # ── Issue 14 §4: modification-intent guard ──────────────────────────
    # If the message starts with a modification verb (change/update/modify/
    # add/remove/fix/make/set/replace/rename), route to the modification
    # handler instead of starting a new S0 intake. Prevents "Change platform
    # to web" from becoming an app name.
    _MOD_VERBS = (
        "change", "update", "modify", "add", "remove", "fix",
        "make", "set", "replace", "rename",
    )
    _leading = text.strip().lstrip("/.,:;!?-— ").lower()
    _first_word = _leading.split(" ", 1)[0] if _leading else ""
    if _first_word in _MOD_VERBS:
        if active:
            # Route to modification handler. If one does not accept raw free
            # text (cmd_modify requires repo URL), fall back to inserting the
            # description into modification_description on the active state.
            try:
                from factory.core.state import PipelineState
                state = PipelineState.model_validate(active.get("state_json", {}))
                state.modification_description = text.strip()
                try:
                    await update_project_state(state)
                except Exception as e:
                    logger.warning(f"modify persist failed: {e}")
                await update.message.reply_text(
                    f"📝 Modification queued for `{state.intake.get('app_name') or state.idea_name or active.get('project_id', 'project')}`:\n"
                    f"> {text.strip()[:200]}\n\n"
                    "Use /continue to apply on the next build cycle, or /modify "
                    "<repo_url> <desc> for a full modification run."
                )
            except Exception as e:
                logger.error(f"modification routing failed: {e}")
                await update.message.reply_text(
                    "I couldn't route that modification. Try /modify <repo> <desc>."
                )
            return
        else:
            await update.message.reply_text(
                "I don't have an active project to modify. Start one with /new."
            )
            return

    intent, confidence = await classify_intent(text)

    logger.info(f"[{user_id}] intent={intent} confidence={confidence:.2f} msg={text[:60]}")

    if intent == "start_project" and confidence >= 0.6:
        await _handle_start_project_intent(update, user_id, text)

    elif intent == "check_status":
        if active:
            from factory.core.state import PipelineState
            try:
                state = PipelineState.model_validate(active.get("state_json", {}))
                reply = await ai_respond(user_id, text, active, intent=intent)
                status_summary = format_status_message(state)
                await update.message.reply_text(f"{reply}\n\n{status_summary}")
            except Exception:
                reply = await ai_respond(user_id, text, active, intent=intent)
                await update.message.reply_text(reply)
        else:
            reply = await ai_respond(user_id, text, None, intent=intent)
            await update.message.reply_text(reply)

    elif intent == "cancel_project":
        if active:
            request_confirmation(user_id, "cancel_project")
            from factory.telegram.messages import project_display_name
            await update.message.reply_text(
                f"You're about to cancel {project_display_name(active)} "
                f"(currently at {active.get('current_stage', '?')}).\n\n"
                "This cannot be undone. Reply 'yes' to confirm, or anything else to abort."
            )
        else:
            await update.message.reply_text("No active project to cancel.")

    elif intent in ("ask_question", "casual_chat", "unclear"):
        reply = await ai_respond(user_id, text, active, intent=intent)
        await update.message.reply_text(reply)

    else:
        # Fallback: AI decides
        reply = await ai_respond(user_id, text, active, intent=intent)
        await update.message.reply_text(reply)


async def _handle_start_project_intent(
    update: Any,
    user_id: str,
    description: str,
) -> None:
    """Safety gate before launching pipeline: show cost estimate and confirm."""
    from factory.telegram.ai_handler import request_confirmation, _add_to_history

    # Estimate cost based on typical S0-S8 run
    estimated_cost = "$0.05–$0.15 (Gemini free tier, no charge)"

    request_confirmation(user_id, f"start_project:{description}")
    _add_to_history(user_id, "user", description)

    # Show full description (up to 400 chars) so the operator can verify
    desc_preview = description if len(description) <= 400 else description[:397] + "..."
    await update.message.reply_text(
        f"Got it — building:\n\"{desc_preview}\"\n\n"
        f"Estimated cost: {estimated_cost}\n\n"
        "Reply 'yes' to start, or anything else to cancel."
    )


async def _execute_confirmed_action(
    update: Any,
    user_id: str,
    action: str | None,
) -> None:
    """Execute a previously confirmed destructive action."""
    if not action:
        await update.message.reply_text("Action expired. Nothing was done.")
        return

    if action.startswith("start_project:"):
        description = action[len("start_project:"):]
        await _ask_app_name(update, user_id, description)

    elif action == "cancel_project":
        active = await get_active_project(user_id)
        if active:
            project_id = active.get("project_id", "")
            from factory.telegram.messages import project_display_name
            _display = project_display_name(active)
            await archive_project(project_id)
            await update.message.reply_text(
                f"{_display} has been cancelled and archived."
            )
        else:
            await update.message.reply_text("No active project found.")


# ═══════════════════════════════════════════════════════════════════
# App Name Flow
# ═══════════════════════════════════════════════════════════════════


async def _ask_app_name(
    update: Any,
    user_id: str,
    description: str,
    attachments: Optional[list] = None,
) -> None:
    """Step 1 of project launch: ask the operator for the app name.

    If the description already contains an explicit app name (e.g. 'app name: "Pulsey AI"'
    or 'called "Pulsey AI"'), auto-extract it and skip the prompt entirely.
    Otherwise, set awaiting_app_name state so the next free-text reply is captured.
    Operator can type a name or 'skip' to get AI-generated suggestions.
    """
    import re as _re
    # Patterns: 'app name: "X"', 'app name: X', 'called "X"', 'app called X'
    _name_patterns = [
        r'app\s+name\s*[:\-–]\s*["\u201c]([^"\u201d]{2,40})["\u201d]',
        r'app\s+name\s*[:\-–]\s*([A-Z][A-Za-z0-9 \-]{1,39})(?:[,.\n]|$)',
        r'(?:app\s+)?called\s+["\u201c]([^"\u201d]{2,40})["\u201d]',
        r'(?:app\s+)?called\s+([A-Z][A-Za-z0-9 \-]{1,39})(?:[,.\n]|$)',
        r'name[:\s]+["\u201c]([^"\u201d]{2,40})["\u201d]',
    ]
    for _pat in _name_patterns:
        _m = _re.search(_pat, description, _re.IGNORECASE)
        if _m:
            extracted_name = _m.group(1).strip().strip('"').strip()
            if extracted_name:
                await _start_project(update, user_id, description, attachments, app_name=extracted_name)
                return

    await set_operator_state(
        user_id,
        "awaiting_app_name",
        {"description": description, "attachments": attachments or []},
    )
    await update.message.reply_text(
        "What should your app be called?\n\n"
        "Type the name (e.g. *Pulsey*) or type `skip` to get AI name suggestions.",
        parse_mode="Markdown",
    )


async def _suggest_app_names(
    update: Any,
    user_id: str,
    description: str,
    attachments: Optional[list] = None,
) -> None:
    """Call the AI to suggest 5 app names, then present as an inline keyboard."""
    import json as _json
    await update.message.reply_text("Thinking of names for your app...")

    try:
        from factory.core.roles import call_ai
        from factory.core.state import AIRole, PipelineState as _PS
        import uuid

        # Build a minimal throwaway state for the AI call
        _tmp_state = _PS(
            project_id=f"naming_{uuid.uuid4().hex[:6]}",
            operator_id=user_id,
        )
        _tmp_state.project_metadata = {"raw_input": description}

        prompt = (
            f"Suggest 5 unique, catchy app names for this idea:\n\n"
            f"{description[:400]}\n\n"
            f"Requirements:\n"
            f"- Short (1-2 words, max 12 characters each word)\n"
            f"- Memorable and brandable\n"
            f"- Avoid generic words like 'App' or 'Pro'\n"
            f"- Consider the target market (Saudi Arabia / MENA)\n\n"
            f"Return ONLY a JSON array of 5 strings: [\"Name1\", \"Name2\", \"Name3\", \"Name4\", \"Name5\"]"
        )

        result = await call_ai(
            role=AIRole.QUICK_FIX,
            prompt=prompt,
            state=_tmp_state,
            action="general",
        )
        names = _json.loads(result)
        if not isinstance(names, list) or len(names) < 2:
            raise ValueError("Invalid names response")
        names = [str(n).strip() for n in names[:5] if str(n).strip()]
    except Exception as e:
        logger.warning(f"Name suggestion failed: {e}")
        # Fallback: derive simple names from description
        words = description.replace(",", " ").replace(".", " ").split()
        names = [w.capitalize() for w in words if len(w) > 3][:5]
        if not names:
            names = ["MyApp", "QuickApp", "FlowApp", "SwiftApp", "LaunchApp"]

    # Build inline keyboard — each button sets the name
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        # Encode: select_name:{name}||{description}
        # Truncate description to keep callback_data under 64 bytes total
        desc_short = description[:40].replace("||", " ")
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"select_name:{name}||{desc_short}")]
            for name in names
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "Here are 5 name suggestions — tap one to use it, "
            "or reply with your own name:",
            reply_markup=reply_markup,
        )
        # Also keep listening for a typed reply
        await set_operator_state(
            user_id,
            "awaiting_app_name",
            {"description": description, "attachments": attachments or []},
        )
    except ImportError:
        # Dry-run mode without telegram library
        name_list = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
        await update.message.reply_text(
            f"Suggested names:\n{name_list}\n\nReply with your chosen name."
        )
        await set_operator_state(
            user_id,
            "awaiting_app_name",
            {"description": description, "attachments": attachments or []},
        )


@require_auth
async def cmd_rename(update: Any, context: Any):
    """/rename <new name> — rename the active project's app name."""
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text("No active project. Start one with /new.")
        return

    new_name = " ".join(context.args).strip() if context.args else ""
    if not new_name:
        await update.message.reply_text(
            "Usage: /rename <new app name>\n\nExample: /rename Pulsey"
        )
        return

    state = PipelineState.model_validate(active["state_json"])
    old_name = state.idea_name or state.project_metadata.get("app_name", state.project_id)
    state.idea_name = new_name
    if state.s0_output:
        state.s0_output["app_name"] = new_name
    state.project_metadata["app_name"] = new_name
    await update_project_state(state)

    await update.message.reply_text(
        f"✅ App name updated: *{old_name}* → *{new_name}*\n\n"
        f"Future files and references will use '{new_name}'.\n"
        f"Previously generated files keep their old name until the next build.",
        parse_mode="Markdown",
    )
    logger.info(f"[{state.project_id}] App renamed: {old_name!r} → {new_name!r}")


@require_auth
async def cmd_update_logo(update: Any, context: Any):
    """/update_logo — Update the app logo for the active project.

    Shows 3 options: auto-generate, upload image, describe.
    """
    user_id = str(update.effective_user.id)
    active = await get_active_project(user_id)
    if not active:
        await update.message.reply_text(
            "No active project. Start one with /new."
        )
        return

    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = [
            [
                InlineKeyboardButton(
                    "🤖 Auto-Generate", callback_data="logo_update:auto"
                ),
                InlineKeyboardButton(
                    "📤 Upload Image",  callback_data="logo_update:upload"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 Cancel",        callback_data="logo_update:cancel"
                ),
            ],
        ]
        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "📸 *Update App Logo*\n\n"
            "Choose how to set your logo:",
            reply_markup=markup,
            parse_mode="Markdown",
        )
    except ImportError:
        # Dry-run / no Telegram library — fall back to text flow
        await set_operator_state(
            user_id, "awaiting_logo",
            {"project_id": active["project_id"]},
        )
        await update.message.reply_text(
            "📸 *Update Logo*\n\n"
            "• Send an image (PNG/JPG) to upload your logo\n"
            "• Type `auto` to let AI generate one\n"
            "• Type a description for a custom-themed icon\n"
            "• Type `cancel` to abort",
            parse_mode="Markdown",
        )


# ═══════════════════════════════════════════════════════════════════
# Project Launcher
# ═══════════════════════════════════════════════════════════════════


async def _start_project(
    update: Any,
    user_id: str,
    description: str,
    attachments: Optional[list] = None,
    app_name: Optional[str] = None,
) -> None:
    """Create and launch a new pipeline project.

    Spec: §5.2 (/new → _start_project)
    """
    import asyncio
    import uuid

    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    prefs = get_operator_preferences(user_id)

    state = PipelineState(
        project_id=project_id,
        operator_id=user_id,
        idea_name=app_name or None,
        autonomy_mode=AutonomyMode(
            prefs.get("autonomy_mode", "autopilot"),
        ),
        execution_mode=ExecutionMode(
            prefs.get("execution_mode", "cloud"),
        ),
        project_metadata={
            "raw_input": description,
            "attachments": attachments or [],
            **({"app_name": app_name} if app_name else {}),
        },
    )

    await update_project_state(state)
    name_display = f" ({app_name})" if app_name else ""
    await update.message.reply_text(
        format_project_started(project_id, state) + name_display
    )

    logger.info(
        f"[{project_id}] Project started by {user_id}: "
        f"{description[:100]}..."
    )

    # Run pipeline stages in background — sends Telegram updates as each stage completes
    async def _run_and_notify():
        try:
            from factory.orchestrator import run_pipeline
            from factory.telegram.notifications import send_telegram_message, notify_operator
            from factory.telegram.messages import format_halt_message
            from factory.core.state import NotificationType
            final = await run_pipeline(state)
            if final.current_stage == Stage.HALTED:
                await send_telegram_message(
                    user_id,
                    format_halt_message(
                        final,
                        reason=final.project_metadata.get("halt_reason", "")
                        or final.legal_halt_reason
                        or final.project_metadata.get("last_error", "")
                        or "no diagnostic detail captured",
                    ),
                )
            else:
                app_name = final.project_metadata.get("app_name", project_id)
                github = final.project_metadata.get("github_repo", "")
                deploy_url = (final.s7_output or {}).get("deployment_url", "")
                summary_lines = [
                    f"🎉 {app_name} is ready!",
                    f"Cost: ${final.total_cost_usd:.2f}",
                ]
                if github:
                    summary_lines.append(f"Repo: github.com/{github}")
                if deploy_url:
                    summary_lines.append(f"URL: {deploy_url}")
                summary_lines.append("Use /status for full details.")
                await send_telegram_message(user_id, "\n".join(summary_lines))
        except Exception as e:
            logger.error(f"[{project_id}] Pipeline error: {e}", exc_info=True)
            try:
                from factory.telegram.notifications import send_telegram_message
                stage_val = state.current_stage.value if state.current_stage else "unknown"
                await send_telegram_message(
                    user_id,
                    f"⚠️ Pipeline error in {stage_val}\n\n"
                    f"{type(e).__name__}: {str(e)[:300]}\n\n"
                    f"Options:\n"
                    f"  /status — check current state\n"
                    f"  /continue — retry from last stage\n"
                    f"  /restore State_#{state.snapshot_id or 0} — rollback\n"
                    f"  /cancel — abandon project",
                )
            except Exception:
                pass

    task = _bg(_run_and_notify())
    register_project_task(project_id, task)


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

        # ── Initialize Mother Memory chain (all 4 backends) in background ──
        async def _init_memory_chain():
            try:
                from factory.memory.mother_memory import _get_chain
                await _get_chain()
                logger.info("[bot] Mother Memory chain initialized")
            except Exception as e:
                logger.warning(f"[bot] Memory chain init failed (will retry on demand): {e}")
        _bg(_init_memory_chain())

        from telegram.ext import MessageHandler as MH
        from telegram.error import TelegramError

        # ── Global error handler — surfaces all handler exceptions ──
        async def _error_handler(update: object, context: Any) -> None:
            err = context.error
            logger.error(f"[bot] Unhandled exception: {err}", exc_info=err)
            if isinstance(update, object) and hasattr(update, "effective_message"):
                try:
                    await update.effective_message.reply_text(
                        f"⚠️ Internal error: {type(err).__name__}: {str(err)[:200]}\n"
                        "Check logs. Try again or /status."
                    )
                except Exception:
                    pass

        app.add_error_handler(_error_handler)

        # ── Project lifecycle ──
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("new", cmd_new_project))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("cost", cmd_cost))

        # ── Execution control ──
        app.add_handler(CommandHandler("mode", cmd_mode))
        app.add_handler(CommandHandler("switch_mode", cmd_switch_mode))   # v5.8 alias
        app.add_handler(CommandHandler("quota", cmd_quota))               # v5.8 quota
        app.add_handler(CommandHandler("autonomy", cmd_autonomy))

        # ── Time travel ──
        app.add_handler(CommandHandler("restore", cmd_restore))
        app.add_handler(CommandHandler("snapshots", cmd_snapshots))

        # ── Pipeline flow ──
        app.add_handler(CommandHandler("continue", cmd_continue))
        app.add_handler(CommandHandler("cancel", cmd_cancel))
        app.add_handler(CommandHandler("modify", cmd_modify))
        app.add_handler(CommandHandler("rename", cmd_rename))
        app.add_handler(CommandHandler("update_logo", cmd_update_logo))

        # ── Deploy gate (FIX-08) ──
        app.add_handler(CommandHandler("deploy_confirm", cmd_deploy_confirm))
        app.add_handler(CommandHandler("deploy_cancel", cmd_deploy_cancel))

        # ── Admin / overrides ──
        app.add_handler(CommandHandler("admin", cmd_admin))
        app.add_handler(CommandHandler("force_continue", cmd_force_continue))
        app.add_handler(CommandHandler("budget", cmd_budget))

        # ── Diagnostics ──
        app.add_handler(CommandHandler("warroom", cmd_warroom))
        app.add_handler(CommandHandler("legal", cmd_legal))
        app.add_handler(CommandHandler("providers", cmd_providers))
        app.add_handler(CommandHandler("setup", cmd_setup))
        app.add_handler(CommandHandler("help", cmd_help))

        # ── Mode switching ──
        app.add_handler(CommandHandler("online", cmd_online))
        app.add_handler(CommandHandler("local", cmd_local))

        # ── Evaluation ──
        try:
            from factory.telegram.handlers.evaluate_handler import cmd_evaluate
            app.add_handler(CommandHandler("evaluate", require_auth(cmd_evaluate)))
        except Exception as e:
            logger.warning(f"evaluate_handler unavailable: {e}")

        # ── Revenue & clients ──
        try:
            from factory.telegram.handlers.revenue_handler import (
                cmd_invoice, cmd_revenue, cmd_clients,
            )
            app.add_handler(CommandHandler("invoice", require_auth(cmd_invoice)))
            app.add_handler(CommandHandler("revenue", require_auth(cmd_revenue)))
            app.add_handler(CommandHandler("clients", require_auth(cmd_clients)))
        except Exception as e:
            logger.warning(f"revenue_handler unavailable: {e}")

        # ── Analytics ──
        try:
            from factory.telegram.handlers.analytics_handler import cmd_analytics
            app.add_handler(CommandHandler("analytics", require_auth(cmd_analytics)))
        except Exception as e:
            logger.warning(f"analytics_handler unavailable: {e}")

        # ── Inline callbacks ──
        app.add_handler(CallbackQueryHandler(handle_callback))

        # ── Free-text + media (must be last — catches everything not matched above) ──
        app.add_handler(MessageHandler(
            filters.TEXT | filters.PHOTO
            | filters.Document.ALL | filters.VOICE,
            handle_message,
        ))

        set_bot_instance(app.bot)
        logger.info("Telegram bot configured with 30 command handlers + error handler")
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
    logger.info("Starting Telegram bot in polling mode (Ctrl+C or cancel task to stop)…")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    # Block until cancelled (asyncio.CancelledError) or Ctrl+C
    import asyncio
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    finally:
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            pass
        logger.info("Bot polling stopped.")


# ═══════════════════════════════════════════════════════════════════
# §5.1 Webhook Entry Point
# ═══════════════════════════════════════════════════════════════════

# Cached Application instance (built once on first webhook call)
_webhook_app = None
_webhook_app_lock = None


async def handle_telegram_update(body: dict) -> None:
    """Process a single Telegram update received via webhook.

    Spec: §5.1 — called by factory/main.py POST /webhook.

    Builds (or reuses) the python-telegram-bot Application, deserialises the
    raw JSON body into an Update object, and feeds it through the registered
    command/message handlers exactly as polling would.
    """
    global _webhook_app, _webhook_app_lock

    try:
        from telegram import Update
    except ImportError:
        logger.warning("python-telegram-bot not installed — webhook ignored")
        return

    # Lazy-initialise the Application (once per process lifetime)
    import asyncio
    if _webhook_app_lock is None:
        _webhook_app_lock = asyncio.Lock()

    async with _webhook_app_lock:
        if _webhook_app is None:
            _webhook_app = await setup_bot()
            if _webhook_app is None:
                logger.error("Bot setup failed — cannot process webhook update")
                return
            await _webhook_app.initialize()
            # Don't call start() — that would begin polling; webhook mode
            # only needs the handlers wired and the bot token active.

    if _webhook_app is None:
        return

    try:
        update = Update.de_json(body, _webhook_app.bot)
        await _webhook_app.process_update(update)
    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}", exc_info=True)