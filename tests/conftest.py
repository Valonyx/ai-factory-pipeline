"""
AI Factory Pipeline v5.8.15 — Shared Test Fixtures (Three-Tier Aware)

Tiering rules (Issue 49):

  @pytest.mark.unit         fast isolated tests; autouse mocks apply
                            (AI/Telegram/Supabase/Neo4j/build_chain all stubbed)

  @pytest.mark.integration  NO autouse mocks; exercises real free-tier providers
                            and real filesystem. Skipped unless
                            INTEGRATION_TEST_MODE=1. Static scan rejects any
                            patch() of factory.integrations.* / factory.pipeline.*

  @pytest.mark.e2e          full pipeline via real CLI/Telegram harness.
                            Skipped unless E2E_TEST_MODE=1. Same mock restriction.

Legacy behavior: tests with no marker are treated as @pytest.mark.unit (for
backwards compatibility with the ~56 existing test files). A migration banner
is printed during collection listing how many legacy files still need tagging.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.state import PipelineState, Stage, AutonomyMode


# ═══════════════════════════════════════════════════════════════════
# Marker helpers
# ═══════════════════════════════════════════════════════════════════


def _has_marker(item: pytest.Item, name: str) -> bool:
    return any(m.name == name for m in item.iter_markers())


def _is_unit(item: pytest.Item) -> bool:
    # Default legacy behavior: no marker == unit
    if _has_marker(item, "integration") or _has_marker(item, "e2e"):
        return False
    return True


# ═══════════════════════════════════════════════════════════════════
# Mock-restriction enforcement for integration / e2e tests
# ═══════════════════════════════════════════════════════════════════


_FORBIDDEN_PATCH_TARGETS = (
    "factory.integrations.",
    "factory.pipeline.",
    "factory.core.roles.call_ai",
    "factory.orchestrator",
)

_PATCH_CALL_RE = re.compile(
    r"""(?:unittest\.mock\.)?patch(?:\.object|\.dict|\.multiple)?\s*\(\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)


def _scan_file_for_forbidden_patches(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, patched_target) entries that violate integration rules."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    violations: list[tuple[int, str]] = []
    for m in _PATCH_CALL_RE.finditer(text):
        target = m.group(1)
        if any(target.startswith(p) or target == p.rstrip(".") for p in _FORBIDDEN_PATCH_TARGETS):
            line_no = text[: m.start()].count("\n") + 1
            violations.append((line_no, target))
    return violations


# ═══════════════════════════════════════════════════════════════════
# Collection hooks: tier gating + mock-restriction enforcement
# ═══════════════════════════════════════════════════════════════════


def pytest_collection_modifyitems(config, items):
    integration_allowed = os.getenv("INTEGRATION_TEST_MODE", "0") == "1"
    e2e_allowed = os.getenv("E2E_TEST_MODE", "0") == "1"

    # Per-file cache so we only scan each source file once
    file_violations: dict[Path, list[tuple[int, str]]] = {}

    legacy_untagged = 0
    integration_count = 0
    e2e_count = 0

    skip_integration = pytest.mark.skip(
        reason="integration tier gated by INTEGRATION_TEST_MODE=1 (free-tier keys required)"
    )
    skip_e2e = pytest.mark.skip(
        reason="e2e tier gated by E2E_TEST_MODE=1 (full pipeline harness required)"
    )

    for item in items:
        has_unit = _has_marker(item, "unit")
        has_int = _has_marker(item, "integration")
        has_e2e = _has_marker(item, "e2e")

        # Legacy default: no marker → treat as unit
        if not (has_unit or has_int or has_e2e):
            item.add_marker(pytest.mark.unit)
            legacy_untagged += 1
            continue

        if has_int:
            integration_count += 1
            if not integration_allowed:
                item.add_marker(skip_integration)
                continue
            path = Path(str(item.fspath))
            violations = file_violations.setdefault(
                path, _scan_file_for_forbidden_patches(path)
            )
            if violations:
                item.add_marker(
                    pytest.mark.skip(
                        reason=(
                            f"integration test has forbidden patch() targets: "
                            f"{violations[:3]} — rewrite without mocks or mark as @pytest.mark.unit"
                        )
                    )
                )

        if has_e2e:
            e2e_count += 1
            if not e2e_allowed:
                item.add_marker(skip_e2e)
                continue
            path = Path(str(item.fspath))
            violations = file_violations.setdefault(
                path, _scan_file_for_forbidden_patches(path)
            )
            if violations:
                item.add_marker(
                    pytest.mark.skip(
                        reason=(
                            f"e2e test has forbidden patch() targets: "
                            f"{violations[:3]} — rewrite without mocks or mark as @pytest.mark.unit"
                        )
                    )
                )

    # Surface one-line migration banner to terminal
    if legacy_untagged:
        config._v5815_legacy_untagged = legacy_untagged  # type: ignore[attr-defined]
    config._v5815_integration_count = integration_count  # type: ignore[attr-defined]
    config._v5815_e2e_count = e2e_count  # type: ignore[attr-defined]


def pytest_report_header(config):
    lines = [
        "v5.8.15 test-tier gates: "
        f"INTEGRATION_TEST_MODE={os.getenv('INTEGRATION_TEST_MODE', '0')}, "
        f"E2E_TEST_MODE={os.getenv('E2E_TEST_MODE', '0')}"
    ]
    legacy = getattr(config, "_v5815_legacy_untagged", 0)
    if legacy:
        lines.append(
            f"  ⚠ {legacy} legacy tests without explicit marker — defaulted to @pytest.mark.unit"
        )
    return lines


# ═══════════════════════════════════════════════════════════════════
# State Fixtures (shared across all tiers)
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def fresh_state():
    """Clean PipelineState with test defaults."""
    state = PipelineState(
        project_id="test-proj-001",
        operator_id="test-operator",
    )
    state.autonomy_mode = AutonomyMode.AUTOPILOT
    state.project_metadata["raw_input"] = 'app name: "Test App" — build a test app'
    state.project_metadata["app_name"] = "Test App"
    state.project_metadata["tests_passed"] = True
    state.project_metadata["verify_passed"] = True
    return state


@pytest.fixture
def halted_state(fresh_state):
    """PipelineState in HALTED stage."""
    fresh_state.current_stage = Stage.HALTED
    fresh_state.legal_halt = True
    fresh_state.legal_halt_reason = "Test halt"
    return fresh_state


@pytest.fixture
def copilot_state(fresh_state):
    """PipelineState in COPILOT mode."""
    fresh_state.autonomy_mode = AutonomyMode.COPILOT
    return fresh_state


# ═══════════════════════════════════════════════════════════════════
# Unit-only autouse mocks
#
# Each fixture below is autouse but guards on the test's marker set:
# if the test is marked `integration` or `e2e`, the fixture yields
# without installing the mock, so the real integration path runs.
# ═══════════════════════════════════════════════════════════════════


def _skip_for_integration(request: pytest.FixtureRequest) -> bool:
    node = request.node
    for name in ("integration", "e2e"):
        if node.get_closest_marker(name):
            return True
    return False


@pytest.fixture(autouse=True)
def force_mock_ai_provider(request):
    """Unit tier: set AI_PROVIDER=mock. Integration/e2e: no-op."""
    if _skip_for_integration(request):
        yield
        return
    with patch.dict(os.environ, {
        "AI_PROVIDER": "mock",
        "SCOUT_PROVIDER": "mock",
        "DRY_RUN": "true",
        "SKIP_CREDENTIAL_PREFLIGHT": "true",
    }):
        yield


@pytest.fixture(autouse=True)
def isolate_factory_workspace(request, tmp_path_factory):
    """v5.8.16 Issue 60: redirect FACTORY_WORKSPACE_DIR to a tmp dir so
    tests can never overwrite real user projects under ~/factory-projects/.

    Before this fixture, tests like test_prod_07/08/09 wrote
    `foodapp/`, `riyadh_eats/`, `quicktask/` etc. straight into the
    user's home directory. Any real project a user created with a
    colliding name would have been clobbered on the next test run.

    Scope: unit tier. Integration/e2e opt out (they may legitimately
    need to inspect a real workspace).
    """
    if _skip_for_integration(request):
        yield
        return
    # One tmp dir per session keeps file writes fast but isolated from $HOME.
    ws = tmp_path_factory.mktemp("factory-workspace")
    with patch.dict(os.environ, {"FACTORY_WORKSPACE_DIR": str(ws)}):
        yield


@pytest.fixture(autouse=True)
def mock_store_pipeline_decision(request):
    """Unit tier: patch Mother Memory writes. Integration/e2e: no-op."""
    if _skip_for_integration(request):
        yield None
        return
    with patch(
        "factory.memory.mother_memory.store_pipeline_decision",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "mock-decision-id"
        yield mock


@pytest.fixture(autouse=True)
def mock_telegram(request):
    """Unit tier: patch Telegram sends. Integration/e2e: no-op."""
    if _skip_for_integration(request):
        yield None
        return
    with patch(
        "factory.telegram.notifications.send_telegram_message",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture(autouse=True)
def mock_persist_state(request):
    """Unit tier: patch Supabase persist. Integration/e2e: no-op."""
    if _skip_for_integration(request):
        yield None
        return
    with patch(
        "factory.pipeline.graph.persist_state",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = 1
        yield mock


@pytest.fixture(autouse=True)
def mock_build_chain(request):
    """Unit tier: patch build_with_chain. Integration/e2e: no-op."""
    if _skip_for_integration(request):
        yield None
        return
    try:
        import factory.infra.build_chain  # noqa: F401
        with patch(
            "factory.infra.build_chain.build_with_chain",
            new_callable=AsyncMock,
        ) as mock:
            result = MagicMock()
            result.success = False
            result.error = "mocked in tests"
            result.artifacts = {}
            result.provider = "mock"
            mock.return_value = result
            yield mock
    except ModuleNotFoundError:
        yield None


@pytest.fixture
def mock_ai():
    """Explicit opt-in AI mock (legacy)."""
    with patch(
        "factory.core.roles.call_ai",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = '{"stub": true}'
        yield mock


@pytest.fixture
def mock_deploy_window():
    """Patch is_within_deploy_window to always return True."""
    with patch(
        "factory.legal.checks.is_within_deploy_window",
        return_value=True,
    ):
        yield


class MockNeo4j:
    """In-memory Neo4j mock with async-compatible methods."""

    def __init__(self):
        self._nodes = []
        self._id_counter = 0

    async def create_node(self, label, props):
        self._id_counter += 1
        node = {"_id": self._id_counter, "_label": label, **props}
        self._nodes.append(node)
        return self._id_counter

    async def find_nodes(self, label, filters=None):
        results = [n for n in self._nodes if n["_label"] == label]
        if filters:
            for k, v in filters.items():
                results = [n for n in results if n.get(k) == v]
        return results

    async def query(self, cypher, params=None):
        return []


@pytest.fixture(autouse=True)
def mock_neo4j(request):
    """Unit tier: in-memory Neo4j. Integration/e2e: no-op (real Neo4j or skip)."""
    if _skip_for_integration(request):
        yield None
        return
    neo4j = MockNeo4j()
    with patch(
        "factory.integrations.neo4j.get_neo4j",
        return_value=neo4j,
    ):
        yield neo4j


# ═══════════════════════════════════════════════════════════════════
# File Fixtures (shared)
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_binary():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin", mode="wb") as f:
        f.write(b"fake binary content " * 100)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def tmp_ipa():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ipa", mode="wb") as f:
        f.write(b"fake ipa binary " * 50)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def tmp_aab():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".aab", mode="wb") as f:
        f.write(b"fake aab binary " * 50)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)
