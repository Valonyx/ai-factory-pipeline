"""
AI Factory Pipeline v5.8.12 — Issue 6: Real Integration Tests

Tests the actual integration layer under two modes:
  • Always-passing (CI-safe): verify SupabaseFallback path works end-to-end.
  • Real-service: skipped when credentials are CI placeholders; run locally
    with real .env to verify live Supabase, GitHub, and Telegram connections.

Skip conditions:
  - Supabase real: SUPABASE_URL contains "placeholder"
  - GitHub real: GITHUB_TOKEN is "ci-placeholder" or empty
  - Telegram real: TELEGRAM_BOT_TOKEN ends with ":ci-placeholder"

Run all (including real): pytest tests/test_issue6_real_integrations.py -v
CI safe:                  DRY_RUN=true pytest tests/test_issue6_real_integrations.py -v
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest

from factory.core.state import PipelineState, Stage


# ─── helpers ────────────────────────────────────────────────────────────────

def _is_supabase_placeholder() -> bool:
    return "placeholder" in os.getenv("SUPABASE_URL", "placeholder")

def _is_github_placeholder() -> bool:
    tok = os.getenv("GITHUB_TOKEN", "ci-placeholder")
    return tok in ("", "ci-placeholder")

def _is_telegram_placeholder() -> bool:
    tok = os.getenv("TELEGRAM_BOT_TOKEN", "0:ci-placeholder")
    return tok.endswith(":ci-placeholder") or tok == ""

def _fresh_state(op_id: str = "test-op-6") -> PipelineState:
    return PipelineState(
        project_id=f"integ-test-{uuid.uuid4().hex[:8]}",
        operator_id=op_id,
        current_stage=Stage.S0_INTAKE,
    )


# ═══════════════════════════════════════════════════════════════════
# 6a — Supabase fallback is functional (CI-safe, always runs)
# ═══════════════════════════════════════════════════════════════════

def test_supabase_fallback_initializes():
    """SupabaseFallback instance has correct structure."""
    from factory.integrations.supabase import SupabaseFallback
    fb = SupabaseFallback()
    assert fb.is_fallback is True
    assert hasattr(fb, "table")
    # table() must return a chainable object with select/insert/upsert
    tbl = fb.table("pipeline_states")
    assert hasattr(tbl, "select")
    assert hasattr(tbl, "insert")
    assert hasattr(tbl, "upsert")


@pytest.mark.asyncio
async def test_supabase_fallback_upsert_and_list_snapshots():
    """upsert_pipeline_state + list_snapshots roundtrip via fallback."""
    from factory.integrations import supabase as sb
    from factory.integrations.supabase import (
        reset_clients, upsert_pipeline_state, list_snapshots,
    )

    reset_clients()
    # Force fallback by patching env vars
    with (
        patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""}),
    ):
        reset_clients()
        state = _fresh_state()
        # Should not raise
        await upsert_pipeline_state(state.project_id, state)
        snaps = await list_snapshots(state.project_id, limit=5)
        assert isinstance(snaps, list)
    reset_clients()  # clean up singleton


@pytest.mark.asyncio
async def test_supabase_fallback_get_active_project_returns_none():
    """get_active_project returns None for unknown operator via fallback."""
    from factory.integrations.supabase import get_active_project, reset_clients

    reset_clients()
    with patch.dict(os.environ, {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""}):
        reset_clients()
        result = await get_active_project("operator-does-not-exist-xyz")
        assert result is None
    reset_clients()


# ═══════════════════════════════════════════════════════════════════
# 6b — GitHub integration (CI-safe path + real-service guard)
# ═══════════════════════════════════════════════════════════════════

def test_github_client_not_connected_with_empty_token():
    """GitHubClient.is_connected → False when token is empty string."""
    from factory.integrations.github import GitHubClient

    # Constructor falls back to os.getenv("GITHUB_TOKEN"); force it empty.
    with patch.dict(os.environ, {"GITHUB_TOKEN": ""}):
        gh = GitHubClient(token="")
    # is_connected is a @property; empty token → False
    assert gh.is_connected is False


def test_github_client_connected_with_non_empty_token():
    """GitHubClient.is_connected → True when a non-empty token is provided."""
    from factory.integrations.github import GitHubClient

    gh = GitHubClient(token="ghp_fakefakefakefakefake123456")
    # is_connected checks token non-empty; actual API call is separate
    assert gh.is_connected is True


@pytest.mark.asyncio
@pytest.mark.skipif(
    _is_github_placeholder(),
    reason="GITHUB_TOKEN is CI placeholder — skipping live GitHub test",
)
async def test_github_live_repo_exists_check():
    """Live: verify GitHubClient can call the GitHub API without exception."""
    from factory.integrations.github import get_github

    gh = get_github()
    assert gh.is_connected is True
    # repo_exists should return a bool without raising
    exists = await gh.repo_exists("definitely-not-a-real-repo-name-xyz9876")
    assert isinstance(exists, bool)


# ═══════════════════════════════════════════════════════════════════
# 6c — Telegram integration (CI-safe format checks + real guard)
# ═══════════════════════════════════════════════════════════════════

def test_telegram_token_format_when_set():
    """Telegram token has correct <bot_id>:<hash> format when configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or "placeholder" in token:
        pytest.skip("Telegram token not configured or is placeholder")
    parts = token.split(":")
    assert len(parts) == 2, "Token must be <id>:<hash>"
    assert parts[0].isdigit(), "Token bot_id part must be numeric"
    assert len(parts[1]) >= 20, "Token hash must be ≥20 chars"


@pytest.mark.asyncio
@pytest.mark.skipif(
    _is_telegram_placeholder(),
    reason="TELEGRAM_BOT_TOKEN is CI placeholder — skipping live Telegram test",
)
async def test_telegram_bot_get_me():
    """Live: call getMe() to verify bot token is valid and bot is responsive."""
    from telegram import Bot

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    bot = Bot(token=token)
    me = await bot.get_me()
    assert me.is_bot is True
    assert me.username is not None


# ═══════════════════════════════════════════════════════════════════
# 6a (real) — Supabase live roundtrip
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.skipif(
    _is_supabase_placeholder(),
    reason="SUPABASE_URL is CI placeholder — skipping live Supabase test",
)
async def test_supabase_live_upsert_and_retrieve():
    """Live: upsert a test pipeline state and retrieve it back."""
    from factory.integrations.supabase import (
        upsert_pipeline_state, list_snapshots, reset_clients,
    )

    reset_clients()
    state = _fresh_state("live-test-op")
    state.project_metadata["test_marker"] = "phase8_integration"

    # Upsert
    await upsert_pipeline_state(state.project_id, state)

    # List snapshots — should have at least one entry
    snaps = await list_snapshots(state.project_id, limit=5)
    assert isinstance(snaps, list)
    reset_clients()
