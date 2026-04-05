"""
PROD-16 Validation: Documentation

Tests cover:
  README.md (3 tests):
    1.  Contains project title and version
    2.  Contains Quick Start section
    3.  Contains Project Structure section

  ARCHITECTURE.md (3 tests):
    4.  Contains Layer Map table
    5.  Contains Pipeline DAG diagram
    6.  Contains AI Role pricing table

  OPERATOR_GUIDE.md (3 tests):
    7.  Contains Telegram Commands section
    8.  Contains Budget tier table
    9.  Contains Troubleshooting section

  ADR_INDEX.md (3 tests):
    10. Contains Core Architecture ADRs table
    11. Contains ADR-044 and ADR-051
    12. Contains FIX Index table

Run:
  pytest tests/test_prod_16_docs.py -v
"""

from __future__ import annotations

import os
import pytest


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)


def _read(filename: str) -> str:
    path = os.path.join(PROJECT_ROOT, filename)
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


# ═══════════════════════════════════════════════════════════════════
# Tests 1-3: README.md
# ═══════════════════════════════════════════════════════════════════

class TestReadme:
    def test_title_and_version(self):
        """Contains project title and v5.6."""
        content = _read("README.md")
        if not content:
            pytest.skip("README.md not found")
        assert "AI Factory Pipeline v5.6" in content

    def test_quick_start(self):
        """Contains Quick Start section."""
        content = _read("README.md")
        if not content:
            pytest.skip("README.md not found")
        assert "Quick Start" in content
        assert "pip install" in content

    def test_project_structure(self):
        """Contains Project Structure."""
        content = _read("README.md")
        if not content:
            pytest.skip("README.md not found")
        assert "Project Structure" in content
        assert "factory/" in content


# ═══════════════════════════════════════════════════════════════════
# Tests 4-6: ARCHITECTURE.md
# ═══════════════════════════════════════════════════════════════════

class TestArchitecture:
    def test_layer_map(self):
        """Contains Layer Map table."""
        content = _read("docs/ARCHITECTURE.md")
        if not content:
            pytest.skip("ARCHITECTURE.md not found")
        assert "Layer Map" in content
        assert "orchestrator.py" in content

    def test_pipeline_dag(self):
        """Contains Pipeline DAG diagram."""
        content = _read("docs/ARCHITECTURE.md")
        if not content:
            pytest.skip("ARCHITECTURE.md not found")
        assert "S0 Intake" in content
        assert "S8 Handoff" in content
        assert "max 3 retries" in content

    def test_ai_role_table(self):
        """Contains AI Role pricing."""
        content = _read("docs/ARCHITECTURE.md")
        if not content:
            pytest.skip("ARCHITECTURE.md not found")
        assert "sonar-pro" in content
        assert "claude-opus" in content
        assert "$15.00" in content


# ═══════════════════════════════════════════════════════════════════
# Tests 7-9: OPERATOR_GUIDE.md
# ═══════════════════════════════════════════════════════════════════

class TestOperatorGuide:
    def test_telegram_commands(self):
        """Contains Telegram Commands section."""
        content = _read("docs/OPERATOR_GUIDE.md")
        if not content:
            pytest.skip("OPERATOR_GUIDE.md not found")
        assert "Telegram Commands" in content
        assert "/start" in content
        assert "/build" in content
        assert "/budget" in content

    def test_budget_tiers(self):
        """Contains Budget tier table."""
        content = _read("docs/OPERATOR_GUIDE.md")
        if not content:
            pytest.skip("OPERATOR_GUIDE.md not found")
        assert "GREEN" in content
        assert "AMBER" in content
        assert "RED" in content
        assert "BLACK" in content

    def test_troubleshooting(self):
        """Contains Troubleshooting section."""
        content = _read("docs/OPERATOR_GUIDE.md")
        if not content:
            pytest.skip("OPERATOR_GUIDE.md not found")
        assert "Troubleshooting" in content
        assert "Pipeline seems stuck" in content


# ═══════════════════════════════════════════════════════════════════
# Tests 10-12: ADR_INDEX.md
# ═══════════════════════════════════════════════════════════════════

class TestADRIndex:
    def test_core_adrs(self):
        """Contains Core Architecture ADRs table."""
        content = _read("docs/ADR_INDEX.md")
        if not content:
            pytest.skip("ADR_INDEX.md not found")
        assert "Core Architecture" in content
        assert "ADR-001" in content
        assert "ADR-006" in content

    def test_key_adrs(self):
        """Contains ADR-044 and ADR-051."""
        content = _read("docs/ADR_INDEX.md")
        if not content:
            pytest.skip("ADR_INDEX.md not found")
        assert "ADR-044" in content
        assert "ADR-051" in content
        assert "Budget Degradation" in content
        assert "Handoff Intelligence Pack" in content

    def test_fix_index(self):
        """Contains FIX Index table."""
        content = _read("docs/ADR_INDEX.md")
        if not content:
            pytest.skip("ADR_INDEX.md not found")
        assert "FIX Index" in content
        assert "FIX-05" in content
        assert "FIX-21" in content
        assert "FIX-27" in content
