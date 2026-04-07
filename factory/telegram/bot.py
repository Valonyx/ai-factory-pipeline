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
        await update.message.reply_text(
            f"Active project {active['project_id']} in progress.\n"
            "Use /cancel first, then /modify."
        )
        return

    import uuid
    project_id = f"mod_{uuid.uuid4().hex[:8]}"
    prefs = await get_operator_preferences(user_id)

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
    await update.message.reply_text(
        f"MODIFY mode started — [{project_id}]\n\n"
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
                reason = final.project_metadata.get("halt_reason", "unknown")
                await send_telegram_message(user_id, f"MODIFY halted [{project_id}]: {reason}")
            else:
                await send_telegram_message(
                    user_id,
                    f"MODIFY complete for [{project_id}]! Use /status to see the diff."
                )
        except Exception as e:
            logger.error(f"[{project_id}] MODIFY error: {e}")
            try:
                from factory.telegram.notifications import send_telegram_message
                await send_telegram_message(user_id, f"MODIFY error [{project_id}]: {e}")
            except Exception:
                pass

    asyncio.create_task(_run_modify())


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
    op_state = await get_operator_state(user_id)
    if op_state == "awaiting_project_description":
        await clear_operator_state(user_id)
        await _handle_start_project_intent(update, user_id, text)
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
            await update.message.reply_text(
                f"You're about to cancel project {active.get('project_id', '?')} "
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

    await update.message.reply_text(
        f"Got it — building: \"{description[:120]}\"\n\n"
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
        await _start_project(update, user_id, description)

    elif action == "cancel_project":
        active = await get_active_project(user_id)
        if active:
            project_id = active.get("project_id", "")
            await archive_project(project_id)
            await update.message.reply_text(
                f"Project {project_id} has been cancelled and archived."
            )
        else:
            await update.message.reply_text("No active project found.")


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
    import asyncio
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

    # Run pipeline stages in background — sends Telegram updates as each stage completes
    async def _run_and_notify():
        try:
            from factory.orchestrator import run_pipeline
            from factory.telegram.notifications import send_telegram_message
            final = await run_pipeline(state)
            if final.current_stage.value == "halted":
                reason = final.project_metadata.get("halt_reason", "unknown")
                await send_telegram_message(
                    user_id,
                    f"Pipeline halted for [{project_id}]: {reason}"
                )
            else:
                await send_telegram_message(
                    user_id,
                    f"Pipeline complete for [{project_id}]! Use /status to see results."
                )
        except Exception as e:
            logger.error(f"[{project_id}] Pipeline error: {e}")
            try:
                from factory.telegram.notifications import send_telegram_message
                await send_telegram_message(
                    user_id,
                    f"Error running pipeline [{project_id}]: {e}"
                )
            except Exception:
                pass

    asyncio.create_task(_run_and_notify())


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
        import asyncio as _asyncio
        _asyncio.create_task(_init_memory_chain())

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

        # ── Evaluation ──
        from factory.telegram.handlers.evaluate_handler import cmd_evaluate
        app.add_handler(CommandHandler("evaluate", require_auth(cmd_evaluate)))

        # ── Revenue & clients ──
        from factory.telegram.handlers.revenue_handler import (
            cmd_invoice, cmd_revenue, cmd_clients,
        )
        app.add_handler(CommandHandler("invoice", require_auth(cmd_invoice)))
        app.add_handler(CommandHandler("revenue", require_auth(cmd_revenue)))
        app.add_handler(CommandHandler("clients", require_auth(cmd_clients)))

        # ── Analytics ──
        from factory.telegram.handlers.analytics_handler import cmd_analytics
        app.add_handler(CommandHandler("analytics", require_auth(cmd_analytics)))

        # ── Diagnostics ──
        app.add_handler(CommandHandler("warroom", cmd_warroom))
        app.add_handler(CommandHandler("legal", cmd_legal))
        app.add_handler(CommandHandler("setup", cmd_setup))
        app.add_handler(CommandHandler("providers", cmd_providers))
        app.add_handler(CommandHandler("help", cmd_help))

        # ── Mode switching ──
        app.add_handler(CommandHandler("online", cmd_online))
        app.add_handler(CommandHandler("local", cmd_local))

        # ── Inline callbacks ──
        app.add_handler(CallbackQueryHandler(handle_callback))

        # ── Free-text + media ──
        app.add_handler(MessageHandler(
            filters.TEXT | filters.PHOTO
            | filters.Document.ALL | filters.VOICE,
            handle_message,
        ))

        # ── MODIFY mode ──
        app.add_handler(CommandHandler("modify", require_auth(cmd_modify)))

        set_bot_instance(app.bot)
        logger.info("Telegram bot configured with 22 command handlers")
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