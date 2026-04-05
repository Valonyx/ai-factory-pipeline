"""
PROD-17 Validation: Final Validation + Release

Tests cover:
  Phase 1 — Imports (2 tests):
    1.  phase_1_imports passes with 0 failures
    2.  At least 30 modules verified

  Phase 2 — Config (2 tests):
    3.  phase_2_config passes with 0 failures
    4.  7 config checks passed

  Phase 3 — Pipeline (2 tests):
    5.  phase_3_pipeline passes with 0 failures
    6.  5 DAG checks passed

  Phase 4 — Schemas (2 tests):
    7.  phase_4_schemas passes with 0 failures
    8.  4 schema checks passed

  Phase 5 — Docs (2 tests):
    9.  phase_5_docs structure is valid
    10. Checks 4 documentation files

  Phase 6 — Integration (2 tests):
    11. phase_6_integration passes with 0 failures
    12. 5 cross-module checks passed

  Full Run (2 tests):
    13. run_validation returns valid structure
    14. Total checks >= 30

Run:
  pytest tests/test_prod_17_final.py -v
"""

from __future__ import annotations

import pytest

from scripts.validate_project import (
    phase_1_imports,
    phase_2_config,
    phase_3_pipeline,
    phase_4_schemas,
    phase_5_docs,
    phase_6_integration,
    run_validation,
)


# ═══════════════════════════════════════════════════════════════════
# Tests 1-2: Phase 1 — Imports
# ═══════════════════════════════════════════════════════════════════

class TestPhase1:
    def test_no_failures(self):
        """phase_1_imports has 0 failures."""
        result = phase_1_imports()
        assert result["failed"] == 0, (
            f"Import failures: {result['errors']}"
        )

    def test_module_count(self):
        """At least 30 modules verified."""
        result = phase_1_imports()
        assert result["passed"] >= 30


# ═══════════════════════════════════════════════════════════════════
# Tests 3-4: Phase 2 — Config
# ═══════════════════════════════════════════════════════════════════

class TestPhase2:
    def test_no_failures(self):
        """phase_2_config has 0 failures."""
        result = phase_2_config()
        assert result["failed"] == 0, (
            f"Config failures: {result['errors']}"
        )

    def test_check_count(self):
        """7 config checks passed."""
        result = phase_2_config()
        assert result["passed"] == 7


# ═══════════════════════════════════════════════════════════════════
# Tests 5-6: Phase 3 — Pipeline
# ═══════════════════════════════════════════════════════════════════

class TestPhase3:
    def test_no_failures(self):
        """phase_3_pipeline has 0 failures."""
        result = phase_3_pipeline()
        assert result["failed"] == 0, (
            f"Pipeline failures: {result['errors']}"
        )

    def test_check_count(self):
        """5 DAG checks passed."""
        result = phase_3_pipeline()
        assert result["passed"] == 5


# ═══════════════════════════════════════════════════════════════════
# Tests 7-8: Phase 4 — Schemas
# ═══════════════════════════════════════════════════════════════════

class TestPhase4:
    def test_no_failures(self):
        """phase_4_schemas has 0 failures."""
        result = phase_4_schemas()
        assert result["failed"] == 0, (
            f"Schema failures: {result['errors']}"
        )

    def test_check_count(self):
        """4 schema checks passed."""
        result = phase_4_schemas()
        assert result["passed"] == 4


# ═══════════════════════════════════════════════════════════════════
# Tests 9-10: Phase 5 — Docs
# ═══════════════════════════════════════════════════════════════════

class TestPhase5:
    def test_valid_structure(self):
        """phase_5_docs returns valid structure."""
        result = phase_5_docs()
        assert "passed" in result
        assert "failed" in result
        assert "errors" in result

    def test_4_docs_checked(self):
        """Checks 4 documentation files."""
        result = phase_5_docs()
        total = result["passed"] + result["failed"]
        assert total == 4


# ═══════════════════════════════════════════════════════════════════
# Tests 11-12: Phase 6 — Integration
# ═══════════════════════════════════════════════════════════════════

class TestPhase6:
    def test_no_failures(self):
        """phase_6_integration has 0 failures."""
        result = phase_6_integration()
        assert result["failed"] == 0, (
            f"Integration failures: {result['errors']}"
        )

    def test_check_count(self):
        """5 cross-module checks passed."""
        result = phase_6_integration()
        assert result["passed"] == 5


# ═══════════════════════════════════════════════════════════════════
# Tests 13-14: Full Run
# ═══════════════════════════════════════════════════════════════════

class TestFullValidation:
    def test_valid_structure(self):
        """run_validation returns valid structure."""
        result = run_validation()
        assert "phases" in result
        assert "total_passed" in result
        assert "total_failed" in result
        assert "all_passed" in result
        assert len(result["phases"]) == 6

    def test_total_checks(self):
        """Total checks >= 30."""
        result = run_validation()
        total = (
            result["total_passed"]
            + result["total_failed"]
        )
        assert total >= 30
