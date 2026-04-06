"""
AI Factory Pipeline v5.6 — Telegram Bot Polling Entry Point

Local development: runs the bot in polling mode (no webhook, no Cloud Run).
Stop with Ctrl+C.

Usage:
    source .venv/bin/activate
    python scripts/run_bot.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env for local dev
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from factory.telegram.bot import run_bot_polling

if __name__ == "__main__":
    asyncio.run(run_bot_polling())
