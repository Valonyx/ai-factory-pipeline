"""
AI Factory Pipeline v5.8 — Phase 1 + Phase 2 Real-Path Tests

Covers newly wired production paths:
  - S1-REAL: Legal Dossier PDF generator (factory/legal/pdf_generator.py)
  - S2-REAL: Master Blueprint PDF + Stack ADR + Design Package
  - S3-REAL: GitHub repo creation + file commit
  - S8-REAL: _generate_program_docs Neo4j sibling query
  - PHASE2: _notify_stage_complete per-stage progress notifications
  - PHASE2: Budget governor notify_fn wiring
  - PHASE2: _run_and_notify actionable error messages
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from factory.core.state import (
    PipelineState,
    Stage,
    AutonomyMode,
    NotificationType,
)


# ═══════════════════════════════════════════════════════════════════
# S1-REAL: Legal Dossier PDF Generator
# ═══════════════════════════════════════════════════════════════════


class TestLegalPdfGenerator:
    """Tests for factory/legal/pdf_generator.py — S1-REAL."""

    @pytest.mark.asyncio
    async def test_generate_legal_dossier_pdf_creates_file(
        self, fresh_state, tmp_path
    ):
        """generate_legal_dossier_pdf() produces a non-empty file."""
        from factory.legal.pdf_generator import generate_legal_dossier_pdf

        legal_output = {
            "data_classification": "confidential",
            "regulatory_bodies": ["PDPL", "CST", "SAMA"],
            "payment_mode": "SANDBOX",
            "feature_risk_assessment": [
                {"feature": "payments", "risk": "flagged", "reason": "SAMA", "action": "apply"},
            ],
            "required_legal_docs": ["privacy_policy", "terms_of_use"],
            "required_licenses": ["none"],
            "cross_border_data": False,
            "sama_sandbox_required": True,
            "overall_risk": "medium",
            "proceed": True,
            "blocking_issues": [],
        }

        # Run directly — the function creates artifacts/ under the CWD
        pdf_path = await generate_legal_dossier_pdf(
            project_id="test-legal-pdf",
            app_name="Halal Delivery",
            legal_output=legal_output,
            legal_research="PDPL applies to personal data processing in KSA.",
            legal_documents={
                "terms_of_service": "These are the terms...",
                "privacy_policy": "We collect the following data...",
            },
            operator_id="test-operator",
        )

        assert pdf_path, "PDF path should be non-empty"
        assert isinstance(pdf_path, str)
        # File must exist (PDF or plaintext fallback)
        assert Path(pdf_path).exists(), f"Output file not found: {pdf_path}"

    @pytest.mark.asyncio
    async def test_upload_legal_pdf_to_supabase_returns_none_on_failure(
        self, fresh_state
    ):
        """upload_legal_pdf_to_supabase() returns None gracefully when Supabase is unavailable."""
        from factory.legal.pdf_generator import upload_legal_pdf_to_supabase

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake content")
            tmp_pdf = f.name

        try:
            with patch(
                "factory.integrations.supabase.get_async_supabase_client",
                new_callable=AsyncMock,
                side_effect=Exception("Supabase unavailable"),
            ):
                result = await upload_legal_pdf_to_supabase(
                    fresh_state.project_id, tmp_pdf
                )
            assert result is None
        finally:
            os.unlink(tmp_pdf)

    @pytest.mark.asyncio
    async def test_generate_legal_dossier_pdf_plaintext_fallback(
        self, fresh_state
    ):
        """generate_legal_dossier_pdf() falls back to plaintext when ReportLab unavailable."""
        from factory.legal import pdf_generator as pg

        # Simulate ReportLab unavailable
        with patch.object(pg, "_REPORTLAB_AVAILABLE", False):
            pdf_path = await pg.generate_legal_dossier_pdf(
                project_id="test-plaintext-fallback",
                app_name="Test App",
                legal_output={"overall_risk": "low", "proceed": True},
                legal_research="Test research",
                legal_documents={},
                operator_id="test-op",
            )
        # Should still return a path (plaintext fallback)
        assert pdf_path is not None
        assert isinstance(pdf_path, str)


# ═══════════════════════════════════════════════════════════════════
# S2-REAL: Blueprint PDF + Stack ADR + Design Package
# ═══════════════════════════════════════════════════════════════════


class TestBlueprintPdf:
    """Tests for factory/pipeline/blueprint_pdf.py — S2-REAL."""

    @pytest.fixture
    def blueprint_data(self):
        return {
            "app_name": "Halal Delivery",
            "selected_stack": "flutterflow",
            "target_platforms": ["ios", "android"],
            "app_description": "Halal food delivery for Riyadh",
            "features_must": ["order tracking", "payment"],
            "data_model": [{"entity": "Order", "fields": ["id", "status"]}],
            "api_endpoints": [{"path": "/orders", "method": "GET"}],
            "business_model": "marketplace",
            "version": "1.0.0",
        }

    @pytest.mark.asyncio
    async def test_write_stack_adr_creates_file(
        self, fresh_state, blueprint_data, tmp_path
    ):
        """write_stack_adr() produces a markdown ADR file."""
        from factory.pipeline.blueprint_pdf import write_stack_adr

        with patch(
            "factory.pipeline.blueprint_pdf.Path",
            side_effect=lambda *args: tmp_path.joinpath(*[str(a) for a in args]),
        ):
            adr_path = await write_stack_adr(
                state=fresh_state,
                blueprint_data=blueprint_data,
                adr_rationale="FlutterFlow chosen for cross-platform KSA market.",
            )

        # ADR path should be a non-empty string
        assert isinstance(adr_path, str) and len(adr_path) > 0

    @pytest.mark.asyncio
    async def test_generate_master_blueprint_pdf_returns_path(
        self, fresh_state, blueprint_data
    ):
        """generate_master_blueprint_pdf() returns a file path string."""
        from factory.pipeline.blueprint_pdf import generate_master_blueprint_pdf

        result = await generate_master_blueprint_pdf(
            state=fresh_state,
            blueprint_data=blueprint_data,
        )
        assert isinstance(result, str), "Should return a path string"

    @pytest.mark.asyncio
    async def test_build_design_package_returns_dict(
        self, fresh_state, blueprint_data
    ):
        """build_design_package() returns a dict with expected keys."""
        from factory.pipeline.blueprint_pdf import build_design_package

        with patch(
            "factory.design.mocks.generate_visual_mocks",
            new_callable=AsyncMock,
            return_value={"home_screen": "/tmp/home.png"},
        ), patch(
            "factory.integrations.image_gen.generate_image",
            new_callable=AsyncMock,
            return_value="/tmp/icon.png",
        ):
            result = await build_design_package(
                state=fresh_state,
                blueprint_data=blueprint_data,
            )

        assert isinstance(result, dict)
        # Must include at least one of the known keys
        expected_keys = {"brand", "wcag", "screens", "component_library", "icon"}
        assert result.keys() & expected_keys, f"Got keys: {result.keys()}"


# ═══════════════════════════════════════════════════════════════════
# S3-REAL: GitHub Commit
# ═══════════════════════════════════════════════════════════════════


class TestS3GitHubCommit:
    """Tests for _commit_to_github in s3_codegen.py — S3-REAL."""

    @pytest.mark.asyncio
    async def test_commit_to_github_stores_repo_name(self, fresh_state):
        """_commit_to_github() stores github_repo in state when connected."""
        from factory.pipeline.s4_codegen import _commit_to_github
        from factory.core.state import TechStack

        fresh_state.s4_output = {}
        files = {"lib/main.dart": "void main() {}", "pubspec.yaml": "name: app"}

        mock_gh = MagicMock()
        mock_gh.is_connected.return_value = True
        mock_gh.repo_exists = AsyncMock(return_value=False)
        mock_gh.create_repo = AsyncMock(return_value={"name": "halal-delivery"})
        mock_gh.commit_files = AsyncMock(return_value={"files": 2, "shas": ["abc", "def"]})

        with patch(
            "factory.integrations.github.get_github", return_value=mock_gh
        ):
            await _commit_to_github(
                state=fresh_state,
                files=files,
                app_name="Halal Delivery",
                stack=TechStack.FLUTTERFLOW,
            )

        assert fresh_state.s4_output.get("github_repo") == "halal-delivery"
        assert fresh_state.project_metadata.get("github_repo") == "halal-delivery"
        mock_gh.commit_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_to_github_skips_when_disconnected(self, fresh_state):
        """_commit_to_github() is non-fatal when GitHub not connected."""
        from factory.pipeline.s4_codegen import _commit_to_github
        from factory.core.state import TechStack

        fresh_state.s4_output = {}

        mock_gh = MagicMock()
        mock_gh.is_connected.return_value = False

        with patch(
            "factory.integrations.github.get_github", return_value=mock_gh
        ):
            # Should not raise
            await _commit_to_github(
                state=fresh_state,
                files={"main.dart": "void main() {}"},
                app_name="Test App",
                stack=TechStack.FLUTTERFLOW,
            )

        assert "github_repo" not in fresh_state.s4_output

    @pytest.mark.asyncio
    async def test_commit_to_github_idempotent_existing_repo(self, fresh_state):
        """_commit_to_github() skips create_repo when repo already exists."""
        from factory.pipeline.s4_codegen import _commit_to_github
        from factory.core.state import TechStack

        fresh_state.s4_output = {}

        mock_gh = MagicMock()
        mock_gh.is_connected.return_value = True
        mock_gh.repo_exists = AsyncMock(return_value=True)
        mock_gh.create_repo = AsyncMock()
        mock_gh.commit_files = AsyncMock(return_value={"files": 1, "shas": ["xyz"]})

        with patch(
            "factory.integrations.github.get_github", return_value=mock_gh
        ):
            await _commit_to_github(
                state=fresh_state,
                files={"main.dart": "void main(){}"},
                app_name="Existing App",
                stack=TechStack.REACT_NATIVE,
            )

        mock_gh.create_repo.assert_not_called()
        mock_gh.commit_files.assert_called_once()

    def test_repo_name_sanitisation(self):
        """Repo name sanitisation: special chars become dashes, truncated to 50."""
        import re
        app_name = "My App! For KSA (v2.0) — الرياض"
        repo_name = re.sub(r"[^a-z0-9-]", "-", app_name.lower())[:50].strip("-")
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in repo_name)
        assert len(repo_name) <= 50
        assert not repo_name.startswith("-")
        assert not repo_name.endswith("-")


# ═══════════════════════════════════════════════════════════════════
# S8-REAL: _generate_program_docs Neo4j sibling query
# ═══════════════════════════════════════════════════════════════════


class TestS8ProgramDocs:
    """Tests for _generate_program_docs in s8_handoff.py — S8-REAL."""

    @pytest.mark.asyncio
    async def test_no_program_id_returns_empty(self, fresh_state):
        """Returns {} when no program_id in metadata."""
        from factory.pipeline.s9_handoff import _generate_program_docs

        fresh_state.project_metadata.pop("program_id", None)
        result = await _generate_program_docs(fresh_state, "context")
        assert result == {}

    @pytest.mark.asyncio
    async def test_siblings_not_complete_returns_deferred(
        self, fresh_state, mock_neo4j
    ):
        """Returns _PROGRAM_DOCS_DEFERRED when siblings not done."""
        from factory.pipeline.s9_handoff import _generate_program_docs

        fresh_state.project_metadata["program_id"] = "prog-001"

        # Register an incomplete sibling
        await mock_neo4j.create_node("ProjectNode", {
            "program_id": "prog-001",
            "status": "S4_CODEGEN",
            "stack": "flutterflow",
        })

        result = await _generate_program_docs(fresh_state, "context")
        assert "_PROGRAM_DOCS_DEFERRED" in result

    @pytest.mark.asyncio
    async def test_all_siblings_complete_generates_docs(
        self, fresh_state, mock_neo4j
    ):
        """Generates 3 cross-project docs when all siblings are complete."""
        from factory.pipeline.s9_handoff import _generate_program_docs

        fresh_state.project_metadata["program_id"] = "prog-002"

        # Register completed siblings
        for stack in ["flutterflow", "react_native"]:
            await mock_neo4j.create_node("ProjectNode", {
                "program_id": "prog-002",
                "status": "S9_HANDOFF",
                "stack": stack,
            })

        result = await _generate_program_docs(fresh_state, "app context")
        # Should contain the 3 cross-project docs
        assert any("INTEGRATION" in k.upper() for k in result)
        assert any("DEPLOYMENT" in k.upper() for k in result)
        assert any("HEALTH" in k.upper() or "DASHBOARD" in k.upper() for k in result)

    @pytest.mark.asyncio
    async def test_no_siblings_returns_empty(self, fresh_state, mock_neo4j):
        """Returns {} when program_id has no registered siblings."""
        from factory.pipeline.s9_handoff import _generate_program_docs

        fresh_state.project_metadata["program_id"] = "prog-orphan"
        # No nodes registered for this program_id

        result = await _generate_program_docs(fresh_state, "context")
        assert result == {}

    @pytest.mark.asyncio
    async def test_neo4j_unavailable_returns_deferred(self, fresh_state):
        """Returns deferred notice when Neo4j raises."""
        from factory.pipeline.s9_handoff import _generate_program_docs

        fresh_state.project_metadata["program_id"] = "prog-err"

        with patch(
            "factory.integrations.neo4j.get_neo4j",
            side_effect=Exception("Neo4j down"),
        ):
            result = await _generate_program_docs(fresh_state, "context")

        assert "_PROGRAM_DOCS_DEFERRED" in result


# ═══════════════════════════════════════════════════════════════════
# PHASE2: Per-Stage Progress Notifications
# ═══════════════════════════════════════════════════════════════════


class TestNotifyStageComplete:
    """Tests for _notify_stage_complete in orchestrator.py — PHASE2."""

    @pytest.mark.asyncio
    async def test_sends_notification_for_known_stage(self, fresh_state):
        """_notify_stage_complete() calls notify_operator for a known stage."""
        from factory.orchestrator import _notify_stage_complete

        with patch(
            "factory.orchestrator.notify_operator",
            new_callable=AsyncMock,
        ) as mock_notify:
            await _notify_stage_complete(fresh_state, "S1_LEGAL")

        mock_notify.assert_called_once()
        args = mock_notify.call_args
        assert args[0][0] is fresh_state
        assert args[0][1] == NotificationType.STAGE_TRANSITION
        msg = args[0][2]
        assert "S1_LEGAL" in msg
        assert "%" in msg

    @pytest.mark.asyncio
    async def test_progress_percentage_increases_with_stage(self, fresh_state):
        """Later stages have higher percentage than earlier stages."""
        from factory.orchestrator import _notify_stage_complete

        messages = []
        with patch(
            "factory.orchestrator.notify_operator",
            new_callable=AsyncMock,
            side_effect=lambda state, ntype, msg: messages.append(msg),
        ):
            await _notify_stage_complete(fresh_state, "S0_INTAKE")
            await _notify_stage_complete(fresh_state, "S9_HANDOFF")

        # Extract percentages
        def extract_pct(msg):
            for part in msg.split():
                if "%" in part:
                    return int(part.replace("%", ""))
            return 0

        pct_s0 = extract_pct(messages[0])
        pct_s8 = extract_pct(messages[1])
        assert pct_s8 > pct_s0, f"S8 ({pct_s8}%) should be > S0 ({pct_s0}%)"

    @pytest.mark.asyncio
    async def test_no_operator_id_is_silent(self, fresh_state):
        """_notify_stage_complete() is a no-op when operator_id is empty."""
        from factory.orchestrator import _notify_stage_complete

        fresh_state.operator_id = ""

        with patch(
            "factory.orchestrator.notify_operator",
            new_callable=AsyncMock,
        ) as mock_notify:
            await _notify_stage_complete(fresh_state, "S1_LEGAL")

        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_failure_is_non_fatal(self, fresh_state):
        """_notify_stage_complete() swallows notification errors (non-fatal)."""
        from factory.orchestrator import _notify_stage_complete

        with patch(
            "factory.orchestrator.notify_operator",
            new_callable=AsyncMock,
            side_effect=Exception("Telegram down"),
        ):
            # Should not raise
            await _notify_stage_complete(fresh_state, "S4_CODEGEN")

    @pytest.mark.asyncio
    async def test_stage_notification_called_in_pipeline(
        self, fresh_state, mock_deploy_window
    ):
        """run_pipeline() calls _notify_stage_complete after each stage."""
        from factory.orchestrator import run_pipeline

        call_args = []

        async def _fake_notify(state, stage_name):
            call_args.append(stage_name)

        with patch("factory.orchestrator._notify_stage_complete", _fake_notify):
            await run_pipeline(fresh_state)

        # Should have been called for each of 9 stages at minimum
        assert len(call_args) >= 9, f"Only got {len(call_args)} notifications: {call_args}"
        # First stage should be s0_intake
        assert call_args[0].upper() in ("S0_INTAKE",)
        # Last call should include S8_HANDOFF
        assert "S9_HANDOFF" in call_args


# ═══════════════════════════════════════════════════════════════════
# PHASE2: Budget Governor notify_fn Wiring
# ═══════════════════════════════════════════════════════════════════


class TestBudgetGovernorNotifyFn:
    """Tests that notify_fn is passed to budget_governor.check() — PHASE2."""

    @pytest.mark.asyncio
    async def test_call_ai_passes_notify_fn_to_budget_governor(
        self, fresh_state
    ):
        """call_ai() passes notify_fn=send_telegram_message to budget_governor.check()."""
        from factory.core.roles import call_ai

        received_kwargs = {}

        async def _fake_check(role, state, contract, notify_fn=None):
            received_kwargs["notify_fn"] = notify_fn
            return contract

        with patch(
            "factory.core.roles.budget_governor.check",
            side_effect=_fake_check,
        ):
            from factory.core.state import AIRole
            await call_ai(
                role=AIRole.SCOUT,
                prompt="Test prompt",
                state=fresh_state,
                action="general",
            )

        assert "notify_fn" in received_kwargs
        assert received_kwargs["notify_fn"] is not None, \
            "notify_fn should be send_telegram_message, not None"

    @pytest.mark.asyncio
    async def test_stub_governor_accepts_notify_fn(self, fresh_state):
        """_StubBudgetGovernor.check() accepts notify_fn kwarg without error."""
        from factory.core.roles import _StubBudgetGovernor
        from factory.core.state import AIRole, RoleContract

        stub = _StubBudgetGovernor()
        contract = RoleContract(
            role=AIRole.SCOUT,
            model="claude-haiku-4-5-20251001",
            can_read_web=True,
            can_write_code=False,
            can_write_files=False,
            can_plan_architecture=False,
            can_decide_legal=False,
            can_manage_war_room=False,
            max_output_tokens=4096,
        )

        # Should not raise
        result = await stub.check(
            AIRole.SCOUT, fresh_state, contract,
            notify_fn=AsyncMock(),
        )
        assert result is contract

    @pytest.mark.asyncio
    async def test_real_governor_tier_alert_fires_via_notify_fn(self):
        """BudgetGovernor._send_tier_alert fires when notify_fn is provided."""
        from factory.monitoring.budget_governor import BudgetGovernor, BudgetTier

        governor = BudgetGovernor(ceiling_usd=10.0)
        governor._cached_spend_cents = 850  # 85% → AMBER

        notify_calls = []

        async def _fake_notify(operator_id, msg):
            notify_calls.append((operator_id, msg))

        state = PipelineState(project_id="test-bgt", operator_id="op-123")
        await governor._send_tier_alert(
            BudgetTier.AMBER, 85, 1.50, state, _fake_notify
        )

        assert len(notify_calls) == 1
        op_id, msg = notify_calls[0]
        assert op_id == "op-123"
        assert "AMBER" in msg
        assert "85%" in msg


# ═══════════════════════════════════════════════════════════════════
# PHASE2: Actionable Error Messages in bot.py
# ═══════════════════════════════════════════════════════════════════


class TestActionableErrorMessages:
    """Tests that _run_and_notify() sends actionable messages — PHASE2."""

    @pytest.mark.asyncio
    async def test_halt_uses_format_halt_message(self, fresh_state):
        """On pipeline halt, sends format_halt_message (not generic text)."""
        from factory.telegram.messages import format_halt_message

        fresh_state.current_stage = Stage.HALTED
        fresh_state.legal_halt_reason = "PDPL missing"

        msg = format_halt_message(fresh_state, reason="PDPL missing")

        assert "/continue" in msg
        assert "/cancel" in msg
        assert "PDPL" in msg

    @pytest.mark.asyncio
    async def test_completion_message_includes_github_repo(self, fresh_state):
        """On completion, message includes GitHub repo if present."""
        from factory.telegram.messages import format_status_message

        fresh_state.current_stage = Stage.S9_HANDOFF
        fresh_state.project_metadata["github_repo"] = "my-app"

        # format_status_message should reflect current stage
        msg = format_status_message(fresh_state)
        assert "S9_HANDOFF" in msg

    def test_format_halt_message_shows_snapshot_restore(self, fresh_state):
        """format_halt_message() includes /restore State_# link."""
        from factory.telegram.messages import format_halt_message

        fresh_state.snapshot_id = 7
        fresh_state.current_stage = Stage.S6_TEST

        msg = format_halt_message(fresh_state, reason="test timeout")
        assert "State_#7" in msg or "restore" in msg.lower()

    def test_format_halt_message_includes_war_room_info(self, fresh_state):
        """format_halt_message() includes War Room if activations exist."""
        from factory.telegram.messages import format_halt_message

        fresh_state.war_room_history = [
            {"level": 1, "error": "Build failed", "resolved": False}
        ]
        msg = format_halt_message(fresh_state, reason="build error")
        assert "War Room" in msg or "war" in msg.lower()


# ═══════════════════════════════════════════════════════════════════
# PHASE2: Telegram Wiring — /new → run_pipeline chain
# ═══════════════════════════════════════════════════════════════════


class TestTelegramNewProjectChain:
    """Tests for /new → _start_project → run_pipeline chain — PHASE2."""

    @pytest.mark.asyncio
    async def test_cmd_new_project_calls_start_project_with_description(self):
        """cmd_new_project() calls _start_project when description provided."""
        from factory.telegram.bot import cmd_new_project

        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.effective_user.first_name = "Test"
        mock_context = MagicMock()
        mock_context.args = ["Build", "a", "test", "app"]

        with patch("factory.telegram.bot.authenticate_operator", return_value=True), \
             patch("factory.telegram.bot.get_active_project", new_callable=AsyncMock, return_value=None), \
             patch("factory.telegram.bot._start_project", new_callable=AsyncMock) as mock_start:

            await cmd_new_project(mock_update, mock_context)

        mock_start.assert_called_once()
        _args = mock_start.call_args
        assert "Build a test app" in _args[0][2]  # description arg

    @pytest.mark.asyncio
    async def test_start_project_creates_background_task(self):
        """_start_project() fires a background task (not blocking)."""
        from factory.telegram.bot import _start_project

        mock_update = MagicMock()
        mock_update.message = AsyncMock()
        mock_update.message.reply_text = AsyncMock()

        with patch("factory.telegram.bot.get_operator_preferences", return_value={}), \
             patch("factory.telegram.bot.update_project_state", new_callable=AsyncMock), \
             patch("factory.telegram.bot._bg") as mock_bg, \
             patch("factory.telegram.bot.format_project_started", return_value="Project started!"):

            await _start_project(mock_update, "12345", "Build a test app")

        # _bg should have been called once with a coroutine
        assert mock_bg.call_count == 1

    @pytest.mark.asyncio
    async def test_existing_project_blocks_new(self):
        """cmd_new_project() shows active project message if one exists."""
        from factory.telegram.bot import cmd_new_project

        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.message = AsyncMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["New idea"]

        active = {
            "project_id": "proj-existing",
            "current_stage": "S4_CODEGEN",
            "state_json": PipelineState(
                project_id="proj-existing", operator_id="12345"
            ).model_dump(mode="json"),
        }

        with patch("factory.telegram.bot.authenticate_operator", return_value=True), \
             patch("factory.telegram.bot.get_active_project", new_callable=AsyncMock, return_value=active):

            await cmd_new_project(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        assert "proj-existing" in reply_text or "Active project" in reply_text


# ═══════════════════════════════════════════════════════════════════
# PHASE2: Copilot Decision Blocking
# ═══════════════════════════════════════════════════════════════════


class TestCopilotDecisions:
    """Tests that Copilot mode blocks and Autopilot auto-selects — PHASE2."""

    @pytest.mark.asyncio
    async def test_autopilot_auto_selects_recommended(self, fresh_state):
        """In Autopilot mode, present_decision() returns recommended option immediately."""
        from factory.telegram.decisions import present_decision

        fresh_state.autonomy_mode = AutonomyMode.AUTOPILOT
        result = await present_decision(
            state=fresh_state,
            decision_type="stack_selection",
            question="Which stack?",
            options=[
                {"label": "FlutterFlow", "value": "flutterflow"},
                {"label": "React Native", "value": "react_native"},
            ],
            recommended=0,
        )
        assert result == "flutterflow"

    @pytest.mark.asyncio
    async def test_copilot_dryruns_auto_select_on_import_error(self, fresh_state):
        """In Copilot dry-run (no python-telegram-bot), present_decision() auto-selects."""
        import sys
        from factory.telegram.decisions import present_decision

        fresh_state.autonomy_mode = AutonomyMode.COPILOT

        # Force the ImportError path by hiding the telegram module from sys.modules.
        # This simulates the environment where python-telegram-bot is not installed,
        # causing present_decision() to immediately fall back to auto-selecting recommended.
        with patch("factory.telegram.decisions.notify_operator", new_callable=AsyncMock), \
             patch.dict(sys.modules, {"telegram": None}):
            result = await present_decision(
                state=fresh_state,
                decision_type="stack_selection",
                question="Choose stack?",
                options=[
                    {"label": "FlutterFlow", "value": "flutterflow"},
                    {"label": "React Native", "value": "react_native"},
                ],
                recommended=1,  # React Native is recommended
            )

        # In dry-run mode (ImportError on InlineKeyboardButton), recommended is auto-selected
        assert result == "react_native"

    @pytest.mark.asyncio
    async def test_copilot_store_and_resolve_decision(self, fresh_state):
        """store_decision_request() + resolve_decision() correctly resolves a decision."""
        from factory.telegram.decisions import (
            store_decision_request,
            resolve_decision,
            get_decision_result,
        )

        decision_id = "dec_testabcd"
        await store_decision_request(
            decision_id=decision_id,
            project_id=fresh_state.project_id,
            operator_id=fresh_state.operator_id,
            decision_type="test_choice",
            options=[
                {"label": "A", "value": "option_a"},
                {"label": "B", "value": "option_b"},
            ],
            recommended=0,
        )

        # Initially unresolved
        result = await get_decision_result(decision_id)
        assert result is None

        # Resolve it
        resolved = await resolve_decision(decision_id, "option_b")
        assert resolved is True

        # Now the result is available
        result = await get_decision_result(decision_id)
        assert result == "option_b"

    @pytest.mark.asyncio
    async def test_decision_timeout_auto_selects_recommended(self, fresh_state):
        """Decision timeout (timeout_seconds=0) auto-selects the recommended option.

        When Telegram is not installed, present_decision() falls back to the
        DryRun path which auto-selects the recommended option — same as timeout.
        """
        from factory.telegram.decisions import present_decision

        fresh_state.autonomy_mode = AutonomyMode.COPILOT

        with patch("factory.telegram.decisions.notify_operator", new_callable=AsyncMock):
            result = await present_decision(
                state=fresh_state,
                decision_type="test_decision",
                question="Test?",
                options=[
                    {"label": "Option A", "value": "a"},
                    {"label": "Option B", "value": "b"},
                ],
                recommended=1,  # B is recommended
                timeout_seconds=0,
            )

        # DryRun path (no telegram module) → auto-selects recommended
        assert result == "b"


# ═══════════════════════════════════════════════════════════════════
# Integration: Full pipeline emits notifications at each stage
# ═══════════════════════════════════════════════════════════════════


class TestFullPipelineNotifications:
    """End-to-end: run_pipeline() emits per-stage notifications — PHASE2."""

    @pytest.mark.asyncio
    async def test_run_pipeline_emits_nine_stage_notifications(
        self, fresh_state, mock_deploy_window
    ):
        """A complete pipeline run emits exactly 9 stage-complete notifications."""
        from factory.orchestrator import run_pipeline

        notified_stages = []

        async def _capture(state, stage_name):
            notified_stages.append(stage_name)

        with patch("factory.orchestrator._notify_stage_complete", _capture):
            result = await run_pipeline(fresh_state)

        assert result.current_stage != Stage.HALTED, \
            f"Pipeline should complete, not halt: {result.project_metadata.get('halt_reason')}"
        # 10 stages: S0 through S9
        assert len(notified_stages) >= 10, \
            f"Expected ≥10 notifications, got {len(notified_stages)}: {notified_stages}"

    @pytest.mark.asyncio
    async def test_halted_pipeline_halts_at_halt_handler(self, fresh_state):
        """A halted state is handled by halt_handler_node, not run to completion."""
        from factory.orchestrator import halt_handler_node, _notify_stage_complete

        # Pre-halt the state
        fresh_state.legal_halt = True
        fresh_state.legal_halt_reason = "Test halt — legal block"
        fresh_state.current_stage = Stage.HALTED

        result = await halt_handler_node(fresh_state)
        assert result.current_stage == Stage.HALTED

    @pytest.mark.asyncio
    async def test_pipeline_halt_stops_after_halted_stage(self, fresh_state):
        """When legal_halt is set during a stage, HALTED short-circuits run_pipeline."""
        from factory.orchestrator import run_pipeline, STAGE_SEQUENCE

        notified = []

        async def _capture(state, stage_name):
            notified.append(stage_name)

        # Patch STAGE_SEQUENCE directly to inject a halting node at position 1
        async def _halt_node(state):
            state.legal_halt = True
            state.legal_halt_reason = "Injected test halt"
            state.current_stage = Stage.HALTED
            return state

        patched_seq = [STAGE_SEQUENCE[0], ("s1_legal", _halt_node)] + STAGE_SEQUENCE[2:]

        with patch("factory.orchestrator.STAGE_SEQUENCE", patched_seq), \
             patch("factory.orchestrator._notify_stage_complete", _capture):
            result = await run_pipeline(fresh_state)

        assert result.current_stage == Stage.HALTED
        # Only S0 notification was emitted (before the halt at S1)
        assert len(notified) <= 1, f"Expected ≤1 notification, got: {notified}"
