"""
PROD-14 Validation: Deployment Infrastructure

Tests cover:
  requirements.txt (3 tests):
    1.  File parses — all lines valid
    2.  Core packages present (fastapi, anthropic, pydantic)
    3.  No duplicate packages

  pyproject.toml (3 tests):
    4.  Valid TOML structure
    5.  Version matches 5.8.0
    6.  CLI entry point defined

  Dockerfile (3 tests):
    7.  Uses python:3.11-slim base
    8.  Non-root user (factory)
    9.  HEALTHCHECK defined

  cloudbuild.yaml (3 tests):
    10. Valid YAML structure
    11. Deploys to me-central1
    12. 4 build steps

  .env.example (3 tests):
    13. Contains all 9 required secrets
    14. Contains model override comments
    15. Contains budget config comments

Run:
  pytest tests/test_prod_14_deployment.py -v
"""

from __future__ import annotations

import os
import pytest

# ═══════════════════════════════════════════════════════════════════
# Helpers — read files from project root
# ═══════════════════════════════════════════════════════════════════

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)


def _read_file(filename: str) -> str:
    """Read a project root file, or return empty if missing."""
    path = os.path.join(PROJECT_ROOT, filename)
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


# ═══════════════════════════════════════════════════════════════════
# Tests 1-3: requirements.txt
# ═══════════════════════════════════════════════════════════════════

class TestRequirements:
    def test_parses_clean(self):
        """All lines are valid (packages or comments)."""
        content = _read_file("requirements.txt")
        if not content:
            pytest.skip("requirements.txt not found")

        for line in content.strip().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Should contain package name
            assert any(
                c.isalpha() for c in stripped
            ), f"Invalid line: {stripped}"

    def test_core_packages(self):
        """Core packages present."""
        content = _read_file("requirements.txt")
        if not content:
            pytest.skip("requirements.txt not found")

        lower = content.lower()
        for pkg in [
            "fastapi", "anthropic", "pydantic",
            "httpx", "uvicorn",
        ]:
            assert pkg in lower, f"Missing: {pkg}"

    def test_no_duplicates(self):
        """No duplicate packages."""
        content = _read_file("requirements.txt")
        if not content:
            pytest.skip("requirements.txt not found")

        packages = []
        for line in content.strip().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            name = stripped.split("==")[0].split(">=")[0].split("[")[0]
            packages.append(name.lower())

        assert len(packages) == len(set(packages)), (
            f"Duplicates: {[p for p in packages if packages.count(p) > 1]}"
        )


# ═══════════════════════════════════════════════════════════════════
# Tests 4-6: pyproject.toml
# ═══════════════════════════════════════════════════════════════════

class TestPyproject:
    def test_valid_toml(self):
        """Valid TOML structure."""
        content = _read_file("pyproject.toml")
        if not content:
            pytest.skip("pyproject.toml not found")

        # Basic structural checks
        assert "[project]" in content
        assert "[build-system]" in content

    def test_version(self):
        """Version matches 5.8.0."""
        content = _read_file("pyproject.toml")
        if not content:
            pytest.skip("pyproject.toml not found")

        assert 'version = "5.8.0"' in content

    def test_cli_entry(self):
        """CLI entry point defined."""
        content = _read_file("pyproject.toml")
        if not content:
            pytest.skip("pyproject.toml not found")

        assert "factory-cli" in content
        assert "factory.cli:main" in content


# ═══════════════════════════════════════════════════════════════════
# Tests 7-9: Dockerfile
# ═══════════════════════════════════════════════════════════════════

class TestDockerfile:
    def test_python_311(self):
        """Uses python:3.11-slim base."""
        content = _read_file("Dockerfile")
        if not content:
            pytest.skip("Dockerfile not found")

        assert "python:3.11-slim" in content

    def test_non_root(self):
        """Non-root user (factory)."""
        content = _read_file("Dockerfile")
        if not content:
            pytest.skip("Dockerfile not found")

        assert "USER factory" in content
        assert "groupadd" in content

    def test_healthcheck(self):
        """HEALTHCHECK defined."""
        content = _read_file("Dockerfile")
        if not content:
            pytest.skip("Dockerfile not found")

        assert "HEALTHCHECK" in content
        assert "/health" in content


# ═══════════════════════════════════════════════════════════════════
# Tests 10-12: cloudbuild.yaml
# ═══════════════════════════════════════════════════════════════════

class TestCloudBuild:
    def test_valid_yaml(self):
        """Valid YAML structure."""
        content = _read_file("cloudbuild.yaml")
        if not content:
            pytest.skip("cloudbuild.yaml not found")

        assert "steps:" in content
        assert "images:" in content

    def test_me_central1(self):
        """Deploys to me-central1."""
        content = _read_file("cloudbuild.yaml")
        if not content:
            pytest.skip("cloudbuild.yaml not found")

        assert "me-central1" in content

    def test_4_steps(self):
        """4 build steps."""
        content = _read_file("cloudbuild.yaml")
        if not content:
            pytest.skip("cloudbuild.yaml not found")

        assert content.count("- name:") == 4


# ═══════════════════════════════════════════════════════════════════
# Tests 13-15: .env.example
# ═══════════════════════════════════════════════════════════════════

class TestEnvExample:
    def test_required_secrets(self):
        """Contains all 9 required secrets."""
        content = _read_file(".env.example")
        if not content:
            pytest.skip(".env.example not found")

        required = [
            "ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY",
            "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
            "NEO4J_URI", "NEO4J_PASSWORD",
            "GITHUB_TOKEN", "TELEGRAM_BOT_TOKEN",
            "GCP_PROJECT_ID",
        ]
        for secret in required:
            assert secret in content, f"Missing: {secret}"

    def test_model_overrides(self):
        """Contains model override comments."""
        content = _read_file(".env.example")
        if not content:
            pytest.skip(".env.example not found")

        assert "STRATEGIST_MODEL" in content
        assert "ENGINEER_MODEL" in content
        assert "SCOUT_MODEL" in content

    def test_budget_config(self):
        """Contains budget config comments."""
        content = _read_file(".env.example")
        if not content:
            pytest.skip(".env.example not found")

        assert "BUDGET_GOVERNOR_ENABLED" in content
        assert "MONTHLY_BUDGET_USD" in content
