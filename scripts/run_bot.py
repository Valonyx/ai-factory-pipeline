"""
AI Factory Pipeline v5.8 — Telegram Bot Runner

Default mode: LOCAL POLLING (no hosting needed, works immediately).
Online mode:  Render webhook — activated via /online Telegram command,
              auto-reverts after 12 hours or on /local command.

Usage:
    python scripts/run_bot.py          # start local polling (default)
    python scripts/run_bot.py online   # immediately switch to online mode

Modes:
    LOCAL  — bot polls Telegram directly from this machine
    ONLINE — Render webhook handles updates; this process manages the
             12-hour countdown and reverts automatically
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_bot")

RENDER_WEBHOOK_URL = "https://ai-factory-pipeline.onrender.com/webhook"
ONLINE_MAX_HOURS = 12


# ── Telegram webhook helpers ──────────────────────────────────────

def _bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")
    return token


async def _set_webhook(url: str) -> bool:
    import urllib.request, json
    token = _bot_token()
    payload = f"url={url}&drop_pending_updates=true&allowed_updates=%5B%22message%22%2C%22callback_query%22%5D"
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/setWebhook",
        data=payload.encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("ok", False)
    except Exception as e:
        log.error(f"setWebhook failed: {e}")
        return False


async def _delete_webhook() -> bool:
    import urllib.request, json
    token = _bot_token()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/deleteWebhook",
        data=b"drop_pending_updates=true",
        method="POST",
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("ok", False)
    except Exception as e:
        log.error(f"deleteWebhook failed: {e}")
        return False


async def _get_webhook_url() -> str:
    import urllib.request, json
    token = _bot_token()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10
        ) as r:
            return json.loads(r.read()).get("result", {}).get("url", "")
    except Exception:
        return ""


# ── Mode state (shared with bot commands) ────────────────────────
# bot.py imports these to signal mode changes via Telegram commands.

_switch_to_online: asyncio.Event | None = None   # set by /online command
_switch_to_local: asyncio.Event | None = None    # set by /local command


def get_mode_events() -> tuple[asyncio.Event, asyncio.Event]:
    """Return the (go_online, go_local) events, creating them if needed."""
    global _switch_to_online, _switch_to_local
    if _switch_to_online is None:
        _switch_to_online = asyncio.Event()
    if _switch_to_local is None:
        _switch_to_local = asyncio.Event()
    return _switch_to_online, _switch_to_local


# ── Polling loop ──────────────────────────────────────────────────

async def _run_polling_until_online() -> None:
    """Run polling mode; returns when /online is triggered."""
    from factory.telegram.bot import run_bot_polling as _orig_polling

    go_online, _ = get_mode_events()
    go_online.clear()

    # Ensure no webhook is active
    current = await _get_webhook_url()
    if current:
        log.info("Removing existing webhook before starting local polling...")
        await _delete_webhook()

    log.info("▶  LOCAL POLLING — bot is active. Send /online to switch to Render.")

    # Run polling in a task so we can cancel it when /online fires
    polling_task = asyncio.create_task(_orig_polling())

    await go_online.wait()          # blocks until /online command
    polling_task.cancel()
    try:
        await polling_task
    except (asyncio.CancelledError, Exception):
        pass
    log.info("Polling stopped — switching to online mode.")


# ── Online mode timer ─────────────────────────────────────────────

async def _run_online_mode(hours: float = ONLINE_MAX_HOURS) -> None:
    """Set Render webhook, wait up to `hours`, then revert."""
    _, go_local = get_mode_events()
    go_local.clear()

    ok = await _set_webhook(RENDER_WEBHOOK_URL)
    if not ok:
        log.error("Failed to set Render webhook — staying in local mode.")
        go_local.set()
        return

    expires_at = time.time() + hours * 3600
    log.info(
        f"🌐 ONLINE MODE — Render webhook active for up to {hours}h. "
        f"Send /local to revert early."
    )

    # Wait for /local command OR timer expiry
    deadline = hours * 3600
    try:
        await asyncio.wait_for(go_local.wait(), timeout=deadline)
        log.info("/local received — reverting to local polling.")
    except asyncio.TimeoutError:
        remaining = max(0, expires_at - time.time())
        log.info(f"12-hour limit reached — reverting to local polling.")

    await _delete_webhook()
    log.info("Webhook removed. Resuming local polling.")


# ── Main loop ─────────────────────────────────────────────────────

async def main(start_online: bool = False) -> None:
    # Make mode events available to bot commands
    get_mode_events()

    # Register this module with bot.py so commands can signal us
    try:
        import factory.telegram.bot as _bot
        _bot._runner_module = sys.modules[__name__]
    except Exception:
        pass

    if start_online:
        # Force-start in online mode (e.g. `python run_bot.py online`)
        go_online, _ = get_mode_events()
        go_online.set()

    while True:
        go_online, _ = get_mode_events()
        if not go_online.is_set():
            await _run_polling_until_online()

        await _run_online_mode(hours=ONLINE_MAX_HOURS)
        go_online.clear()


if __name__ == "__main__":
    start_online = len(sys.argv) > 1 and sys.argv[1] == "online"
    try:
        asyncio.run(main(start_online=start_online))
    except KeyboardInterrupt:
        log.info("Bot stopped.")
