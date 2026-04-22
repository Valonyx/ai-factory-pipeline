"""v5.8.16 Issue 59 — Telegram bot must enable concurrent update dispatch.

Without `.concurrent_updates(True)` on the Application builder, any handler
that awaits a pending reply (the setup wizard, platform selection, logo
approval, any /rename-style confirmation) deadlocks the entire bot:

  t0: user sends /setup
  t1: cmd_setup → run_setup_wizard → wait_for_operator_reply creates a
      future and `await`s it.
  t2: dispatcher is still waiting for cmd_setup to return, so the user's
      next message ("SKIP" or the API key) is queued but NEVER delivered
      to handle_message — which is what would resolve the future.
  → Bot appears to hang. Only restart recovers it.

This test pins the fix by asserting the builder call includes
concurrent_updates(True).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_bot_builder_enables_concurrent_updates():
    """factory/telegram/bot.py must call Application.builder() with
    concurrent_updates(True) — otherwise every wizard deadlocks."""
    bot_src = Path(__file__).resolve().parents[1] / "factory/telegram/bot.py"
    text = bot_src.read_text()

    # Find the builder call — tolerate arbitrary whitespace.
    # Must contain .concurrent_updates(True) somewhere in the builder chain.
    builder_calls = re.findall(
        r"Application\.builder\(\)[^\n]*?\.build\(\)",
        text,
    )
    assert builder_calls, "No Application.builder()...build() call found"

    assert any("concurrent_updates(True)" in call for call in builder_calls), (
        "Application.builder() chain must include .concurrent_updates(True). "
        "Without it, await-based wizards deadlock the dispatcher. "
        f"Found chains: {builder_calls}"
    )
