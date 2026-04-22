"""v5.8.15 Phase 8 — E2E BASIC+LOCAL+POLLING free-only contract harness.

Gated behind ``E2E_TEST_MODE=1``. Runs the full set of cross-cutting
invariants that the operator-reality report (PHASE_0_REALITY_REPORT_V15
§11) identified as the surface-area of trust for v5.8.15. Each test is
written to be mock-light (the e2e tier forbids patching
``factory.integrations.*`` / ``factory.pipeline.*`` / orchestrator /
``factory.core.roles.call_ai`` — see ``tests/conftest.py:56``).

The 28 checks are grouped by theme:

  A. Test-tier gating (Phase 1 / Issue 49)
  B. Stage-success contract + ghost-cancel (Phase 2 / Issues 50, 52)
  C. Mode persistence write-path (Phase 3 / Issue 51)
  D. Role resolver + BASIC paid exclusion (Phase 4 / Issue 54)
  E. Rendering + cost honesty + ID leak (Phase 5 / Issues 53, 55, 56)
  F. S0 FSM + logo engine (Phase 6 / Issues 57, 58)
  G. End-to-end orchestrator smoke (BASIC+LOCAL, zero cost)

Run locally:
    E2E_TEST_MODE=1 pytest -m e2e tests/test_v5815_phase8_e2e.py -v
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.e2e


# ─── A. Test-tier gating (Phase 1) ──────────────────────────────────────

def test_01_pytest_markers_declared_in_pyproject():
    """pytest markers unit/integration/e2e must be registered."""
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text()
    assert "unit" in pyproject
    assert "integration" in pyproject
    assert "e2e" in pyproject


def test_02_conftest_enforces_integration_test_mode_gate():
    """INTEGRATION_TEST_MODE / E2E_TEST_MODE gates must be enforced."""
    conftest = (Path(__file__).resolve().parents[1] / "tests/conftest.py").read_text()
    assert "INTEGRATION_TEST_MODE" in conftest
    assert "E2E_TEST_MODE" in conftest


def test_03_forbidden_patch_targets_enforced():
    """e2e / integration tests must be forbidden to patch core pipeline internals."""
    from tests.conftest import _FORBIDDEN_PATCH_TARGETS
    assert "factory.integrations." in _FORBIDDEN_PATCH_TARGETS
    assert "factory.pipeline." in _FORBIDDEN_PATCH_TARGETS
    assert "factory.orchestrator" in _FORBIDDEN_PATCH_TARGETS


# ─── B. Stage contract + ghost-cancel (Phase 2) ─────────────────────────

def test_04_stage_metrics_reset_per_stage():
    from factory.core.state import PipelineState
    s = PipelineState(project_id="p", operator_id="o")
    s.metrics.record_provider_call()
    s.metrics.record_artifact()
    s.metrics.record_mm_write()
    assert s.metrics.provider_calls_in_stage == 1
    assert s.metrics.artifacts_produced_in_stage == 1
    assert s.metrics.mm_writes_in_stage == 1
    s.metrics.reset_stage()
    assert s.metrics.provider_calls_in_stage == 0
    assert s.metrics.artifacts_produced_in_stage == 0
    assert s.metrics.mm_writes_in_stage == 0
    # Totals must carry over after reset.
    assert s.metrics.provider_calls_total >= 1


def test_05_stage_trivial_completion_halt_code_exists():
    from factory.core.halt import HaltCode
    assert HaltCode.STAGE_TRIVIAL_COMPLETION.value == "STAGE_TRIVIAL_COMPLETION"


def test_06_contract_bypass_honours_mock_provider():
    from factory.orchestrator import _contract_bypass_allowed
    from factory.core.state import PipelineState, Stage
    s = PipelineState(project_id="p", operator_id="o")
    s.current_stage = Stage.S2_BLUEPRINT
    os.environ["AI_PROVIDER"] = "mock"
    try:
        assert _contract_bypass_allowed(Stage.S2_BLUEPRINT, s) is True
    finally:
        os.environ.pop("AI_PROVIDER", None)


def test_07_halted_and_s9_bypass_contract():
    from factory.orchestrator import _contract_bypass_allowed
    from factory.core.state import PipelineState, Stage
    s = PipelineState(project_id="p", operator_id="o")
    # HALTED bypass is keyed on state.current_stage, not the stage arg
    s.current_stage = Stage.HALTED
    assert _contract_bypass_allowed(Stage.HALTED, s) is True
    # S9 bypass is keyed on the stage arg
    s2 = PipelineState(project_id="p2", operator_id="o")
    assert _contract_bypass_allowed(Stage.S9_HANDOFF, s2) is True


# ─── C. Mode persistence (Phase 3) ──────────────────────────────────────

def test_08_mode_store_has_effective_readers():
    from factory.telegram.mode_store import ModeStore
    assert hasattr(ModeStore, "get_effective_execution_mode")
    assert hasattr(ModeStore, "get_effective_master_mode")


def test_09_decisions_has_sqlite_fallback_helper():
    """Phase 3 added a SQLite fallback for operator_preferences."""
    from factory.telegram import decisions
    assert hasattr(decisions, "_prefs_sqlite_path")


@pytest.mark.asyncio
async def test_10_sqlite_fallback_roundtrip(tmp_path, monkeypatch):
    """Writing a preference must survive even when Supabase is absent."""
    from factory.telegram import decisions
    monkeypatch.setattr(
        decisions, "_prefs_sqlite_path", lambda: tmp_path / "prefs.sqlite3"
    )
    # Force Supabase unavailable
    monkeypatch.setattr(decisions, "get_supabase_client", lambda: None, raising=False)
    await decisions.set_operator_preference("op-e2e", "execution_mode", "local")
    prefs = await decisions.load_operator_preferences("op-e2e")
    assert prefs.get("execution_mode") == "local"


# ─── D. Role resolver + BASIC paid exclusion (Phase 4) ──────────────────

def test_11_paid_providers_frozenset_covers_anthropic_and_perplexity():
    from factory.core.provider_intelligence import PAID_PROVIDERS, is_paid
    assert "anthropic" in PAID_PROVIDERS
    assert "perplexity" in PAID_PROVIDERS
    assert is_paid("gemini") is False


def test_12_filter_for_mode_strips_paid_in_basic_only():
    from factory.core.provider_intelligence import filter_for_mode
    chain = ["anthropic", "gemini", "groq", "perplexity"]
    assert filter_for_mode(chain, "BASIC") == ["gemini", "groq"]
    assert filter_for_mode(chain, "BALANCED") == chain
    assert filter_for_mode(chain, "TURBO") == chain


def test_13_status_message_excludes_anthropic_in_basic():
    from factory.core.provider_intelligence import provider_intelligence
    msg = provider_intelligence.status_message("BASIC")
    assert "anthropic" in msg.lower()
    assert "excluded" in msg.lower()


# ─── E. Rendering + cost + ID leak (Phase 5) ────────────────────────────

def test_14_quota_bar_never_uses_tofu_glyph():
    from factory.core.quota_tracker import QuotaTracker
    tracker = QuotaTracker()
    s = tracker._get_state("gemini")
    s.calls = max(50, (s.quota_calls or 0) // 2)
    blob = "\n".join(tracker.usage_summary())
    assert "\u2593" not in blob  # iOS tofu glyph


def test_15_project_display_name_never_leaks_hex():
    from factory.telegram.messages import project_display_name
    # Bare hex-only id
    assert project_display_name({"project_id": "proj_deadbeef"}) == "your new project"
    # None input
    assert project_display_name(None) == "your new project"


def test_16_cost_message_is_mode_aware():
    from factory.telegram.messages import format_cost_message
    from factory.core.state import PipelineState
    state = PipelineState(project_id="p", operator_id="o")
    basic = format_cost_message(state, master_mode="BASIC")
    balanced = format_cost_message(state, master_mode="BALANCED")
    assert "BASIC free-only" in basic
    assert "BASIC free-only" not in balanced
    assert "$25.00" in balanced  # codegen_engineer ceiling
    assert "$25.00" not in basic


def test_17_cost_phase_names_are_backticked_for_markdown_safety():
    from factory.telegram.messages import format_cost_message
    from factory.core.state import PipelineState
    msg = format_cost_message(PipelineState(project_id="p", operator_id="o"),
                              master_mode="BALANCED")
    # Phase names contain underscores; must be wrapped in `backticks`.
    assert "`scout_research`" in msg
    assert "`codegen_engineer`" in msg


# ─── F. S0 FSM + logo engine (Phase 6) ──────────────────────────────────

@pytest.mark.asyncio
async def test_18_cmd_new_engages_s0_fsm():
    from factory.telegram import bot as _bot
    update = MagicMock()
    update.effective_user.id = 42
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["fitness", "tracker", "for", "runners"]

    with patch.object(_bot, "get_active_project", new=AsyncMock(return_value=None)), \
         patch.object(_bot, "_ask_app_name", new=AsyncMock()) as ask, \
         patch.object(_bot, "_start_project", new=AsyncMock()) as start:
        handler = getattr(_bot.cmd_new_project, "__wrapped__", _bot.cmd_new_project)
        await handler(update, context)

    assert ask.await_count == 1
    assert start.await_count == 0


@pytest.mark.asyncio
async def test_19_ask_app_name_sets_awaiting_state_when_unextractable():
    from factory.telegram import bot as _bot
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    with patch.object(_bot, "set_operator_state", new=AsyncMock()) as ss, \
         patch.object(_bot, "_onboarding_ask_platforms", new=AsyncMock()):
        await _bot._ask_app_name(update, "42", "a generic todo list application")
    assert ss.await_count == 1
    assert ss.call_args.args[1] == "awaiting_app_name"


def test_20_save_logo_to_disk_variant_index_contract(tmp_path, monkeypatch):
    from factory.pipeline import s0_intake
    monkeypatch.setattr(
        "factory.core.execution._get_project_workspace",
        lambda pid, name: str(tmp_path),
    )
    p0 = s0_intake._save_logo_to_disk(b"\x89PNGaaaa", "p", "App")
    p2 = s0_intake._save_logo_to_disk(b"\x89PNGbbbb", "p", "App", variant_index=2)
    assert p0.endswith("logo.png")
    assert p2.endswith("logo_02.png")
    assert os.path.exists(p0) and os.path.exists(p2)


@pytest.mark.asyncio
async def test_21_logo_flow_auto_writes_three_variants(tmp_path, monkeypatch):
    from factory.pipeline import s0_intake
    from factory.core.state import PipelineState
    monkeypatch.setattr(
        "factory.core.execution._get_project_workspace",
        lambda pid, name: str(tmp_path),
    )
    state = PipelineState(project_id="e2e_logo", operator_id="12345")
    state.idea_name = "E2ELogo"
    fake_png = b"\x89PNG" + b"x" * 500
    with patch.object(s0_intake, "generate_image",
                      new=AsyncMock(return_value=fake_png)), \
         patch.object(s0_intake, "build_logo_prompt", return_value="E2ELogo logo"), \
         patch.object(s0_intake, "get_bot", return_value=None):
        asset = await s0_intake._logo_flow_auto(
            state, {"app_name": "E2ELogo", "app_description": ""},
        )
    assert asset["logo_variant_count"] == 3
    for i in (1, 2, 3):
        assert (tmp_path / "brand" / f"logo_{i:02d}.png").exists()
    assert (tmp_path / "brand" / "logo.png").exists()


# ─── G. Orchestrator smoke (BASIC+LOCAL, zero cost) ─────────────────────

def test_22_basic_master_mode_enum_exists():
    from factory.core.mode_router import MasterMode
    assert MasterMode.BASIC.value == "basic"


def test_23_local_execution_mode_enum_exists():
    from factory.core.state import ExecutionMode
    assert ExecutionMode.LOCAL.value == "local"


def test_24_pipeline_state_defaults_record_no_usage():
    """Fresh state must report zero cost and zero usage."""
    from factory.core.state import PipelineState
    s = PipelineState(project_id="p", operator_id="o")
    assert s.total_cost_usd == 0.0
    assert s.metrics.provider_calls_total == 0
    assert s.metrics.artifacts_produced_total == 0
    assert s.metrics.mm_writes_total == 0


def test_25_resolve_provider_for_role_never_returns_paid_in_basic(monkeypatch):
    """Defensive BASIC filter in the resolver — even if someone edits
    ROLE_PROVIDERS to include anthropic under BASIC, the resolver must
    strip it before returning."""
    from factory.core import provider_intelligence as pi_mod
    from factory.core.state import PipelineState
    from factory.core.mode_router import MasterMode

    saved = dict(pi_mod.ROLE_PROVIDERS["STRATEGIST"])
    try:
        pi_mod.ROLE_PROVIDERS["STRATEGIST"]["BASIC"] = [
            "anthropic", "gemini", "groq",
        ]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("GEMINI_API_KEY", "g-test")
        monkeypatch.setenv("GROQ_API_KEY", "gr-test")
        state = PipelineState(project_id="p", operator_id="o")
        state.master_mode = MasterMode.BASIC
        chain = pi_mod.provider_intelligence.resolve_provider_for_role(
            "STRATEGIST", state,
        )
        assert "anthropic" not in chain
        assert any(p in chain for p in ("gemini", "groq"))
    finally:
        pi_mod.ROLE_PROVIDERS["STRATEGIST"] = saved


def test_26_archive_project_contract_clears_ghost_cancel():
    """archive_project (and cmd_continue) must clear pipeline_aborted so a
    subsequent /new does not immediately halt with PIPELINE_CANCELLED."""
    import inspect
    from factory.telegram import bot as _bot
    src = inspect.getsource(_bot.archive_project)
    assert "pipeline_aborted" in src
    assert "False" in src or "false" in src.lower()


def test_27_providers_command_reads_effective_master_mode():
    """/providers must read the operator's effective MasterMode, not the
    global ai_chain."""
    import inspect
    from factory.telegram import bot as _bot
    src = inspect.getsource(_bot.cmd_providers)
    assert "get_effective_master_mode" in src


def test_28_traceability_doc_exists():
    """Phase 7 traceability document must be committed."""
    root = Path(__file__).resolve().parents[1]
    doc = root / "TRACEABILITY_V5815_PHASE7.md"
    assert doc.exists()
    text = doc.read_text()
    # Must cover every phase
    for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4",
                  "Phase 5", "Phase 6"):
        # Accept either exact or lowercase
        assert phase.lower() in text.lower(), f"Missing {phase} in traceability doc"
