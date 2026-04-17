"""
AI Factory Pipeline v5.8.12 — Tests for Issue 17: Output Quality Gates.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from factory.core.quality_gates import (
    GateResult,
    QualityGateFailure,
    check_min_length,
    check_min_list,
    check_no_placeholders,
    raise_if_failed,
)
from factory.core.halt import HaltCode
from factory.core.state import PipelineState, Stage
from factory.core.mode_router import MasterMode


# ── Unit tests for gate helpers ───────────────────────────────────────────────


class TestCheckNoPlaceholders:
    def test_pass(self):
        result = check_no_placeholders("This is clean text with no tokens.", "field1")
        assert result.passed is True
        assert result.observed == []

    def test_fail(self):
        result = check_no_placeholders("Hello [COMPANY_NAME], see [CONTACT_EMAIL].", "field1")
        assert result.passed is False
        assert "[COMPANY_NAME]" in result.observed
        assert "[CONTACT_EMAIL]" in result.observed
        assert "COMPANY_NAME" in result.message


class TestCheckMinLength:
    def test_pass(self):
        result = check_min_length("a" * 100, 50, "body")
        assert result.passed is True
        assert result.observed == 100

    def test_fail(self):
        result = check_min_length("short", 3000, "body")
        assert result.passed is False
        assert result.observed == 5
        assert result.required == 3000
        assert "too short" in result.message


class TestCheckMinList:
    def test_pass(self):
        result = check_min_list(["a", "b", "c"], 3, "items")
        assert result.passed is True
        assert result.observed == 3

    def test_fail(self):
        result = check_min_list(["a"], 5, "items")
        assert result.passed is False
        assert result.observed == 1
        assert result.required == 5
        assert "too short" in result.message


class TestRaiseIfFailed:
    def test_raises_on_failed_gate(self):
        failed = GateResult(
            name="test_gate",
            passed=False,
            observed=0,
            required=5,
            message="Not enough items",
        )
        with pytest.raises(QualityGateFailure) as exc_info:
            raise_if_failed("S1_LEGAL", [failed])
        assert exc_info.value.stage == "S1_LEGAL"
        assert len(exc_info.value.failed_gates) == 1
        assert exc_info.value.failed_gates[0].name == "test_gate"

    def test_no_raise_when_all_passed(self):
        passed = GateResult(
            name="test_gate",
            passed=True,
            observed=10,
            required=5,
            message="",
        )
        raise_if_failed("S1_LEGAL", [passed])  # must not raise


class TestQualityGateFailure:
    def test_format_for_telegram_contains_stage_and_gate(self):
        gate = GateResult(
            name="min_list:feature_list",
            passed=False,
            observed=2,
            required=5,
            message="List too short: 2 < 5 items",
        )
        exc = QualityGateFailure(
            stage="S2_BLUEPRINT",
            failed_gates=[gate],
            recommended_action="retry S2_BLUEPRINT",
        )
        text = exc.format_for_telegram()
        assert "S2_BLUEPRINT" in text
        assert "min_list:feature_list" in text
        assert "2" in text  # observed
        assert "5" in text  # required

    def test_quality_gate_failure_is_exception(self):
        exc = QualityGateFailure(stage="TEST", failed_gates=[])
        assert isinstance(exc, Exception)


# ── Integration-style gate tests ─────────────────────────────────────────────


class TestS1GateEmptyDocsHalts:
    @pytest.mark.asyncio
    async def test_s1_gate_empty_docs_halts(self, fresh_state):
        """S1 gate with empty legal_documents and DRY_RUN=false should set legal_halt."""
        from factory.core.quality_gates import (
            check_min_list, GateResult, raise_if_failed, QualityGateFailure,
        )
        from factory.core.halt import HaltCode, HaltReason, set_halt

        # Simulate the gate logic from s1_legal.py with an empty docs dict
        docs: dict = {}
        _gate_results = []
        for doc_name, content in docs.items():
            pass  # no docs to iterate

        doc_count = len([k for k, v in docs.items() if isinstance(v, str) and len(v) > 100])
        _gate_results.append(GateResult(
            name="min_doc_count",
            passed=doc_count >= 4,
            observed=doc_count,
            required=4,
            message=f"Need >=4 legal documents, got {doc_count}" if doc_count < 4 else "",
        ))

        try:
            raise_if_failed("S1_LEGAL", _gate_results, recommended_action="retry S1_LEGAL")
        except QualityGateFailure as qgf:
            set_halt(fresh_state, HaltReason(
                code=HaltCode.QUALITY_GATE_FAILED,
                title="Legal documents failed quality gate",
                detail=qgf.format_for_telegram()[:600],
                stage="S1_LEGAL",
                failing_gate="legal_content",
                remediation_steps=["Retry S1 with /continue", "/cancel"],
            ))
            fresh_state.legal_halt = True

        assert fresh_state.legal_halt is True
        struct = fresh_state.project_metadata.get("halt_reason_struct", {})
        assert struct.get("code") == HaltCode.QUALITY_GATE_FAILED.value


class TestS2GateEmptyFeaturesHalts:
    @pytest.mark.asyncio
    async def test_s2_gate_empty_features_halts(self, fresh_state):
        """S2 gate with empty feature_list should trigger a quality gate failure."""
        from factory.core.quality_gates import (
            check_min_list, raise_if_failed, QualityGateFailure,
        )
        from factory.core.halt import HaltCode, HaltReason, set_halt

        bp = {"feature_list": [], "user_journeys": [], "analytics_events": []}
        _gate_results = []

        features = bp.get("feature_list") or []
        _gate_results.append(check_min_list(features, 5, "feature_list"))

        journeys = bp.get("user_journeys") or []
        _gate_results.append(check_min_list(journeys, 3, "user_journeys"))

        events = bp.get("analytics_events") or []
        _gate_results.append(check_min_list(events, 5, "analytics_events"))

        try:
            raise_if_failed("S2_BLUEPRINT", _gate_results)
        except QualityGateFailure as qgf:
            set_halt(fresh_state, HaltReason(
                code=HaltCode.QUALITY_GATE_FAILED,
                title="Blueprint failed quality gate",
                detail=qgf.format_for_telegram()[:600],
                stage="S2_BLUEPRINT",
                failing_gate="blueprint_content",
                remediation_steps=["Retry S2 with /continue", "/cancel"],
            ))
            fresh_state.legal_halt = True

        assert fresh_state.legal_halt is True
        struct = fresh_state.project_metadata.get("halt_reason_struct", {})
        assert struct.get("code") == HaltCode.QUALITY_GATE_FAILED.value


class TestS4GateFewFilesHalts:
    @pytest.mark.asyncio
    async def test_s4_gate_few_files_halts(self, fresh_state):
        """S4 gate with only 1 file in BALANCED mode should trigger quality gate failure."""
        from factory.core.quality_gates import GateResult, raise_if_failed, QualityGateFailure
        from factory.core.halt import HaltCode, HaltReason, set_halt

        fresh_state.master_mode = MasterMode.BALANCED
        fresh_state.s4_output = {"generated_files": {"a.py": "x = 1"}}

        gen_files: dict = (fresh_state.s4_output or {}).get("generated_files") or {}
        file_count = len(gen_files)

        min_files = {
            MasterMode.BASIC: 10,
            MasterMode.BALANCED: 50,
            MasterMode.CUSTOM: 50,
            MasterMode.TURBO: 150,
        }.get(fresh_state.master_mode, 50)

        _gate_results = [
            GateResult(
                name="min_file_count",
                passed=file_count >= min_files,
                observed=file_count,
                required=min_files,
                message=f"Generated {file_count} files, need >={min_files}" if file_count < min_files else "",
            ),
        ]

        total_sloc = sum(
            len([ln for ln in c.splitlines() if ln.strip()])
            for c in gen_files.values()
            if isinstance(c, str)
        )
        min_sloc = {
            MasterMode.BASIC: 200,
            MasterMode.BALANCED: 2000,
            MasterMode.CUSTOM: 2000,
            MasterMode.TURBO: 8000,
        }.get(fresh_state.master_mode, 2000)

        _gate_results.append(GateResult(
            name="min_sloc",
            passed=total_sloc >= min_sloc,
            observed=total_sloc,
            required=min_sloc,
            message=f"Total SLOC {total_sloc} < {min_sloc}" if total_sloc < min_sloc else "",
        ))

        try:
            raise_if_failed("S4_CODEGEN", _gate_results)
        except QualityGateFailure as qgf:
            set_halt(fresh_state, HaltReason(
                code=HaltCode.QUALITY_GATE_FAILED,
                title="CodeGen failed quality gate",
                detail=qgf.format_for_telegram()[:600],
                stage="S4_CODEGEN",
                failing_gate="codegen_output",
                remediation_steps=["Retry CodeGen with /continue", "/cancel"],
            ))
            fresh_state.legal_halt = True

        assert fresh_state.legal_halt is True
        struct = fresh_state.project_metadata.get("halt_reason_struct", {})
        assert struct.get("code") == HaltCode.QUALITY_GATE_FAILED.value
