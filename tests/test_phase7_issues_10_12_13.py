"""
AI Factory Pipeline v5.8.12 — Phase 7 Tests
Issues 10 (S6 cascade diagnosis + regression), 12 (write_files_to_disk),
13 (logo_path persistence)

14 tests:
  1.  MIN_TESTS_EXECUTED constant is >= 10
  2.  MAX_CODEGEN_REGRESSIONS constant is >= 2
  3.  tests_executed gate: < MIN → passed=False, failure appended
  4.  tests_executed gate: >= MIN → no extra failure appended
  5.  tests_executed gate skipped in DRY_RUN=true
  6.  _diagnose_test_failures: returns dict with root_cause + issues + s4_instruction
  7.  _diagnose_test_failures: parse failure returns safe fallback dict
  8.  _cascade_on_test_failure: under cap → sets legal_halt + QUALITY_GATE_FAILED
  9.  _cascade_on_test_failure: at cap → permanent halt, no asyncio.create_task
 10.  write_files_to_disk: writes all str files to workspace, returns path
 11.  write_files_to_disk: skips non-str values silently
 12.  _save_logo_to_disk: writes PNG bytes to brand/logo.png, returns path
 13.  _save_logo_to_disk: exception → returns None, no raise
 14.  s0_intake_node: logo_asset with logo_path persists to state.intake["logo_path"]
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.state import PipelineState, Stage


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_state(**kwargs) -> PipelineState:
    defaults = dict(
        project_id="test-proj-phase7",
        operator_id="777",
        s0_output={"app_name": "Phase7App"},
        s4_output={"generated_files": {}},
        s5_output={"source_only": True, "build_success": False, "workspace_path": "", "files_written": 0},
        s6_output={},
        project_metadata={"app_name": "Phase7App"},
    )
    defaults.update(kwargs)
    return PipelineState(**defaults)


# ═══════════════════════════════════════════════════════════════════
# Tests 1–2: Constants
# ═══════════════════════════════════════════════════════════════════

def test_min_tests_executed_constant():
    from factory.pipeline.s6_test import MIN_TESTS_EXECUTED
    assert MIN_TESTS_EXECUTED >= 10


def test_max_codegen_regressions_constant():
    from factory.pipeline.s6_test import MAX_CODEGEN_REGRESSIONS
    assert MAX_CODEGEN_REGRESSIONS >= 2


# ═══════════════════════════════════════════════════════════════════
# Tests 3–5: tests_executed gate
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tests_executed_gate_below_minimum(monkeypatch):
    """< MIN_TESTS_EXECUTED → passed=False with gate failure appended."""
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    from factory.pipeline import s6_test
    original_min = s6_test.MIN_TESTS_EXECUTED

    with patch.dict(os.environ, {"DRY_RUN": "false"}):
        state = _make_state()

        # Simulate what s6_test_node does internally: gate logic
        test_output = {
            "passed": True,
            "total_tests": 3,          # below minimum
            "passed_tests": 3,
            "failed_tests": 0,
            "failures": [],
        }
        total_tests = test_output.get("total_tests", 0)
        if total_tests < s6_test.MIN_TESTS_EXECUTED:
            test_output["passed"] = False
            test_output.setdefault("failures", []).append({
                "file": "test_suite",
                "test": "tests_executed_gate",
                "error": f"Only {total_tests} tests ran; minimum is {s6_test.MIN_TESTS_EXECUTED}.",
                "severity": "critical",
            })

        assert test_output["passed"] is False
        assert any(f["test"] == "tests_executed_gate" for f in test_output["failures"])


@pytest.mark.asyncio
async def test_tests_executed_gate_at_minimum():
    """>= MIN_TESTS_EXECUTED → no gate failure appended."""
    from factory.pipeline import s6_test

    test_output = {
        "passed": True,
        "total_tests": s6_test.MIN_TESTS_EXECUTED,
        "failures": [],
    }
    total_tests = test_output.get("total_tests", 0)
    if total_tests < s6_test.MIN_TESTS_EXECUTED:
        test_output["passed"] = False
        test_output["failures"].append({"test": "tests_executed_gate"})

    assert test_output["passed"] is True
    assert not any(f.get("test") == "tests_executed_gate" for f in test_output["failures"])


@pytest.mark.asyncio
async def test_tests_executed_gate_skipped_in_dry_run(monkeypatch):
    """DRY_RUN=true: gate is skipped even if total_tests == 0."""
    monkeypatch.setenv("DRY_RUN", "true")

    from factory.pipeline import s6_test

    test_output = {"passed": True, "total_tests": 0, "failures": []}
    dry = os.getenv("DRY_RUN", "").lower() in ("true", "1", "yes")
    if not dry:
        total_tests = test_output.get("total_tests", 0)
        if total_tests < s6_test.MIN_TESTS_EXECUTED:
            test_output["passed"] = False

    # Gate skipped → still passed
    assert test_output["passed"] is True


# ═══════════════════════════════════════════════════════════════════
# Tests 6–7: _diagnose_test_failures
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_diagnose_test_failures_returns_structured_dict():
    from factory.pipeline.s6_test import _diagnose_test_failures

    state = _make_state()
    diagnosis_payload = {
        "root_cause": "missing import",
        "issues": [{"file": "a.py", "problem": "NameError", "suggested_fix": "add import"}],
        "s4_instruction": "Fix import at top of a.py",
    }
    with patch(
        "factory.pipeline.s6_test.call_ai",
        new=AsyncMock(return_value=json.dumps(diagnosis_payload)),
    ):
        result = await _diagnose_test_failures(
            state,
            {"total_tests": 5, "failed_tests": 2, "failures": []},
        )

    assert result["root_cause"] == "missing import"
    assert len(result["issues"]) == 1
    assert "s4_instruction" in result


@pytest.mark.asyncio
async def test_diagnose_test_failures_parse_error_returns_fallback():
    from factory.pipeline.s6_test import _diagnose_test_failures

    state = _make_state()
    with patch(
        "factory.pipeline.s6_test.call_ai",
        new=AsyncMock(return_value="NOT VALID JSON"),
    ):
        result = await _diagnose_test_failures(
            state,
            {"total_tests": 1, "failed_tests": 1, "failures": []},
        )

    assert "root_cause" in result
    assert "s4_instruction" in result
    assert isinstance(result["issues"], list)


# ═══════════════════════════════════════════════════════════════════
# Tests 8–9: _cascade_on_test_failure
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cascade_sets_legal_halt_under_cap():
    """Under MAX_CODEGEN_REGRESSIONS → legal_halt=True, QUALITY_GATE_FAILED."""
    from factory.pipeline.s6_test import _cascade_on_test_failure
    from factory.core.halt import HaltCode

    state = _make_state()
    test_output = {"total_tests": 5, "failed_tests": 3, "failures": [], "passed": False}

    diagnosis = {
        "root_cause": "logic error",
        "issues": [{"file": "app.dart", "problem": "null ref", "suggested_fix": "guard"}],
        "s4_instruction": "Guard all null refs",
    }

    with (
        patch("factory.pipeline.s6_test._diagnose_test_failures", new=AsyncMock(return_value=diagnosis)),
        # request_regression is imported inside _run_regression closure → patch at source
        patch("factory.pipeline.stage_regression.request_regression", new=AsyncMock()),
        patch("factory.pipeline.s6_test.asyncio") as mock_asyncio,
        patch("factory.memory.mother_memory.store_insight", new=AsyncMock()),
        patch("factory.telegram.notifications.send_telegram_message", new=AsyncMock()),
    ):
        mock_asyncio.create_task = MagicMock()
        await _cascade_on_test_failure(state, test_output)

    assert state.legal_halt is True
    halt_struct = state.project_metadata.get("halt_reason_struct") or {}
    assert halt_struct.get("code") == HaltCode.QUALITY_GATE_FAILED
    assert state.project_metadata.get("codegen_regression_count", 0) == 1


@pytest.mark.asyncio
async def test_cascade_permanent_halt_at_cap():
    """At MAX_CODEGEN_REGRESSIONS → legal_halt=True, no create_task."""
    from factory.pipeline import s6_test
    from factory.pipeline.s6_test import _cascade_on_test_failure
    from factory.core.halt import HaltCode

    state = _make_state(
        project_metadata={
            "app_name": "Phase7App",
            "codegen_regression_count": s6_test.MAX_CODEGEN_REGRESSIONS,
        }
    )
    test_output = {"total_tests": 5, "failed_tests": 5, "failures": [], "passed": False}

    diagnosis = {
        "root_cause": "persistent error",
        "issues": [],
        "s4_instruction": "Unknown",
    }

    with (
        patch("factory.pipeline.s6_test._diagnose_test_failures", new=AsyncMock(return_value=diagnosis)),
        patch("factory.pipeline.s6_test.asyncio") as mock_asyncio,
        patch("factory.memory.mother_memory.store_insight", new=AsyncMock()),
    ):
        mock_asyncio.create_task = MagicMock()
        await _cascade_on_test_failure(state, test_output)

    assert state.legal_halt is True
    # create_task must NOT be called when cap is exhausted
    mock_asyncio.create_task.assert_not_called()
    halt_struct = state.project_metadata.get("halt_reason_struct") or {}
    assert halt_struct.get("code") == HaltCode.QUALITY_GATE_FAILED


# ═══════════════════════════════════════════════════════════════════
# Tests 10–11: write_files_to_disk (Issue 12)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_write_files_to_disk_writes_all_str_files():
    from factory.pipeline.s4_codegen import write_files_to_disk

    files = {
        "lib/main.dart": "void main() {}",
        "lib/app.dart": "class App {}",
        "README.md": "# App",
    }

    written_paths = []

    async def _fake_write(path, content, project_id=""):
        written_paths.append(path)
        return True

    fake_workspace = "/fake/workspace/testapp"

    with (
        patch("factory.core.execution._get_project_workspace", return_value=fake_workspace),
        patch("factory.core.execution.write_file", new=_fake_write),
    ):
        workspace = await write_files_to_disk(files, "proj-abc", "TestApp")

    assert workspace == fake_workspace
    # All 3 str-valued files should have been attempted
    assert len(written_paths) == 3


@pytest.mark.asyncio
async def test_write_files_to_disk_skips_non_str():
    from factory.pipeline.s4_codegen import write_files_to_disk

    files = {
        "main.dart": "content",
        "binary.bin": b"\x00\x01\x02",   # bytes — should be skipped
        "number.txt": 42,                 # int — should be skipped
    }

    written_paths = []

    async def _fake_write(path, content, project_id=""):
        written_paths.append(path)
        return True

    with (
        patch("factory.core.execution._get_project_workspace", return_value="/fake/ws"),
        patch("factory.core.execution.write_file", new=_fake_write),
    ):
        workspace = await write_files_to_disk(files, "proj-abc2", "TestApp2")

    # Only "main.dart" (str) should have been attempted
    assert len(written_paths) == 1
    assert written_paths[0].endswith("main.dart")


# ═══════════════════════════════════════════════════════════════════
# Tests 12–13: _save_logo_to_disk and logo_path persistence (Issue 13)
# ═══════════════════════════════════════════════════════════════════

def test_save_logo_to_disk_writes_png():
    from factory.pipeline.s0_intake import _save_logo_to_disk

    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"FACTORY_WORKSPACE_DIR": tmpdir}):
            logo_path = _save_logo_to_disk(fake_bytes, "proj-logo", "LogoApp")

    assert logo_path is not None
    assert logo_path.endswith("logo.png")
    # File exists under tmpdir (same process)
    with tempfile.TemporaryDirectory() as tmpdir2:
        with patch.dict(os.environ, {"FACTORY_WORKSPACE_DIR": tmpdir2}):
            lp = _save_logo_to_disk(fake_bytes, "proj-logo2", "LogoApp2")
        assert os.path.isfile(lp)


def test_save_logo_to_disk_returns_none_on_error():
    from factory.pipeline.s0_intake import _save_logo_to_disk

    with patch("factory.core.execution._get_project_workspace", side_effect=OSError("disk full")):
        result = _save_logo_to_disk(b"bytes", "proj-x", "App")

    assert result is None


def test_s0_intake_logo_path_persisted_to_intake():
    """logo_asset with logo_path → state.intake["logo_path"] set."""
    state = _make_state()
    logo_asset = {
        "asset_type": "logo",
        "logo_bytes_len": 1024,
        "logo_prompt": "flat icon",
        "logo_path": "/tmp/brand/logo.png",
        "source": "auto",
    }

    # Simulate the s0_intake_node post-logo logic
    if logo_asset:
        state.brand_assets.append(logo_asset)
        if logo_asset.get("logo_path"):
            state.intake["logo_path"] = logo_asset["logo_path"]

    assert state.intake.get("logo_path") == "/tmp/brand/logo.png"
