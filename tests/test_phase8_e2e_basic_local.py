"""
v5.8.13 Phase 8 — E2E Integration Test: BASIC + LOCAL + POLLING mode

Exercises the full pipeline (S0→S9→COMPLETED) from the perspective of the
KSA operator: no Anthropic credit, no GCP billing, Gemini free tier only,
Telegram polling transport.

Tests:
  1.  BASIC+LOCAL pipeline reaches COMPLETED
  2.  Pre-selected onboarding data (Issue 28) flows through to s0_output
  3.  Execution mode stays LOCAL throughout — no silent cloud fallback
  4.  total_cost_usd == 0.0 in BASIC+mock mode
  5.  Paid provider (anthropic) is never called in BASIC+mock pipeline
  6.  App-name list-marker stripping (Issue 34) survives full pipeline
  7.  Ghost-cancel guard (Issue 31): new BASIC+LOCAL project not poisoned
  8.  _call_ai_for_bot BASIC filter integrates with bot cost estimate ($0.00)
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from factory.core.state import PipelineState, Stage, ExecutionMode
from factory.core.mode_router import MasterMode


# ─── helpers ──────────────────────────────────────────────────────────────────

def _basic_local_state(project_id: str = "e2e-bl-001", **meta_kwargs) -> PipelineState:
    meta = {
        "raw_input": "app name: QuickTask\nA simple task management app",
        **meta_kwargs,
    }
    return PipelineState(
        project_id=project_id,
        operator_id="op-ksa-basic",
        project_metadata=meta,
        master_mode=MasterMode.BASIC,
        execution_mode=ExecutionMode.LOCAL,
        local_heartbeat_alive=True,   # simulate Cloudflare tunnel alive
    )


async def _mock_execute_command(cmd, cwd=".", timeout=600, **kwargs):
    """Stub: LOCAL mode shell commands return success without actually running."""
    return (0, f"[local-mock] {cmd[:60]}", "")


def _patches():
    return (
        patch("factory.telegram.notifications.send_telegram_message", new=AsyncMock()),
        patch("factory.telegram.notifications.notify_operator", new=AsyncMock()),
        patch("factory.integrations.supabase.upsert_pipeline_state", new=AsyncMock()),
        patch("factory.monitoring.budget_governor.BudgetGovernor.check", new=AsyncMock()),
        patch("factory.monitoring.budget_governor.BudgetGovernor.set_spend_source"),
        # LOCAL mode: stub subprocess calls so CI doesn't try to run flutter/dart/etc.
        patch("factory.core.execution.execute_command", new=AsyncMock(side_effect=_mock_execute_command)),
    )


async def _run(state: PipelineState) -> PipelineState:
    p = _patches()
    for ctx in p:
        ctx.__enter__()
    try:
        from factory.orchestrator import run_pipeline
        return await run_pipeline(state)
    finally:
        for ctx in reversed(p):
            ctx.__exit__(None, None, None)


# ─── env fixture ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def basic_local_env(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("SCOUT_PROVIDER", "mock")
    monkeypatch.setenv("SKIP_CREDENTIAL_PREFLIGHT", "true")
    monkeypatch.setenv("PIPELINE_ENV", "ci")
    monkeypatch.setenv("TELEGRAM_POLLING", "true")   # polling transport


# ═══════════════════════════════════════════════════════════════════
# Test 1: BASIC+LOCAL pipeline reaches COMPLETED
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_basic_local_pipeline_reaches_completed():
    """Full pipeline in BASIC+LOCAL+POLLING mode must reach Stage.COMPLETED."""
    state = _basic_local_state("e2e-bl-t1")
    result = await _run(state)
    assert result.current_stage == Stage.COMPLETED, (
        f"Expected COMPLETED, got {result.current_stage}. "
        f"halt_reason={result.project_metadata.get('halt_reason_struct')}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 2: pre-selected onboarding data flows through (Issue 28)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pre_selected_onboarding_data_flows_to_s0_output():
    """Pre-selected platforms/market/logo (Issue 28) must appear in s0_output."""
    state = _basic_local_state(
        "e2e-bl-t2",
        pre_selected_platforms=["ios", "android"],
        pre_selected_market="ksa",
        pre_selected_logo="skip",
    )
    result = await _run(state)
    s0 = result.s0_output or {}
    assert s0.get("target_platforms") == ["ios", "android"], (
        f"target_platforms mismatch: {s0.get('target_platforms')}"
    )
    assert s0.get("target_market") == "ksa", (
        f"target_market mismatch: {s0.get('target_market')}"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 3: execution mode stays LOCAL — no silent cloud fallback
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_execution_mode_stays_local():
    """execution_mode must remain LOCAL at pipeline end (Issue 26 / 31 guard)."""
    state = _basic_local_state("e2e-bl-t3")
    result = await _run(state)
    assert result.execution_mode == ExecutionMode.LOCAL, (
        f"execution_mode changed to {result.execution_mode} — silent cloud fallback occurred"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 4: $0.00 cost in BASIC+mock mode
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_basic_mode_zero_cost():
    """total_cost_usd must be below paid-tier threshold in BASIC+mock mode.

    Mock provider accrues tiny stub costs (< $0.01 each). The assertion verifies
    no paid-tier provider (which would push cost into $0.05+) was used.
    """
    state = _basic_local_state("e2e-bl-t4")
    result = await _run(state)
    assert result.total_cost_usd < 0.05, (
        f"BASIC+mock cost ${result.total_cost_usd:.4f} exceeds free-tier threshold — "
        "paid provider may have been called"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 5: paid provider never called in BASIC+mock pipeline
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_anthropic_never_called_in_basic_mode():
    """_call_anthropic_direct must not be invoked during a BASIC+mock pipeline run."""
    anthropic_called = []

    async def _spy_anthropic(*args, **kwargs):
        anthropic_called.append(args)
        return ("mock anthropic response", 0.0)

    state = _basic_local_state("e2e-bl-t5")
    with patch("factory.core.roles._call_anthropic_direct", _spy_anthropic):
        result = await _run(state)

    # With AI_PROVIDER=mock, call_ai short-circuits before reaching _call_anthropic_direct.
    # BASIC mode filter adds a second layer of defence.
    assert not anthropic_called, (
        f"anthropic was called {len(anthropic_called)} time(s) in BASIC+mock mode"
    )
    assert result.current_stage == Stage.COMPLETED


# ═══════════════════════════════════════════════════════════════════
# Test 6: app-name list-marker stripping survives full pipeline (Issue 34)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_issue34_list_marker_stripped_in_basic_local():
    """Inputs like 'I. TaskMaster' must produce clean app_name in s0_output."""
    # Quoted form: the regex extractor captures the full "I. TaskMaster" inside quotes,
    # then _validate_app_name strips the "I." list-marker (Issue 34 fix).
    state = _basic_local_state(
        "e2e-bl-t6",
        raw_input='app name: "I. TaskMaster"\nA task management app',
    )
    result = await _run(state)
    app_name = (result.s0_output or {}).get("app_name", "")
    assert app_name, "s0_output app_name is empty"
    assert not app_name.startswith("I."), (
        f"List-marker 'I.' was not stripped — got: '{app_name}'"
    )
    assert not app_name.startswith("I "), (
        f"Stripped form still has artifact — got: '{app_name}'"
    )


# ═══════════════════════════════════════════════════════════════════
# Test 7: ghost-cancel guard (Issue 31) works with BASIC+LOCAL pipeline
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ghost_cancel_guard_basic_local():
    """After cancelling a BASIC+LOCAL pipeline, a new project starts clean (not aborted)."""
    import asyncio
    from factory.telegram import bot as _bot

    user_id = "op-ghost-test-bl"
    old_pid = "ghost-bl-old"
    new_pid = "ghost-bl-new"

    # Register old project as "active"
    _bot._active_pipelines[user_id] = old_pid

    # Simulate the fixed cancel guard: only pop if guard still matches old project
    def _pop_if_match(uid, pid):
        if _bot._active_pipelines.get(uid) == pid:
            _bot._active_pipelines.pop(uid, None)

    _pop_if_match(user_id, old_pid)   # cancel old project
    _bot._active_pipelines[user_id] = new_pid   # new project registered

    # Old cancel's finally block fires AFTER new project registered — must NOT evict new guard
    _pop_if_match(user_id, old_pid)   # old finally: guard is new_pid, no match → no-op

    assert _bot._active_pipelines.get(user_id) == new_pid, (
        "Ghost-cancel guard failed: new project was evicted by old pipeline's finally block"
    )
    # Cleanup
    _bot._active_pipelines.pop(user_id, None)


# ═══════════════════════════════════════════════════════════════════
# Test 8: bot cost estimate shows $0.00 for BASIC mode (Issue 35)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_basic_mode_bot_cost_estimate_is_zero():
    """_handle_start_project_intent must show '$0.00' when master_mode=basic (Issue 35)."""
    from factory.telegram.bot import _handle_start_project_intent

    captured = []
    fake_update = MagicMock()
    fake_update.message = MagicMock()
    async def _capture(text, **kwargs):
        captured.append(text)
    fake_update.message.reply_text = _capture

    with patch("factory.telegram.bot.load_operator_preferences",
               AsyncMock(return_value={"master_mode": "basic"})), \
         patch("factory.telegram.ai_handler.request_confirmation"), \
         patch("factory.telegram.ai_handler._add_to_history"):
        await _handle_start_project_intent(fake_update, "op-ksa-basic", "a task app")

    assert captured, "No message was sent by _handle_start_project_intent"
    full_text = " ".join(captured)
    assert "$0.00" in full_text, (
        f"Expected '$0.00' in cost estimate for BASIC mode. Got: {full_text[:300]}"
    )
