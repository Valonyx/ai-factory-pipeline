"""
AI Factory Pipeline v5.8 — Shared Test Fixtures

Provides:
  - fresh_state: Clean PipelineState for each test
  - mock_telegram: Patches send_telegram_message to no-op
  - mock_ai: Patches call_ai to return stub responses
  - mock_neo4j: Patches Neo4j client with in-memory store
  - tmp_binary: Temporary binary file for delivery tests
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.core.state import PipelineState, Stage, AutonomyMode


# ═══════════════════════════════════════════════════════════════════
# State Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def fresh_state():
    """Clean PipelineState with test defaults."""
    state = PipelineState(
        project_id="test-proj-001",
        operator_id="test-operator",
    )
    state.autonomy_mode = AutonomyMode.AUTOPILOT
    # Issue 14: S0 now halts without an explicit app name. Include one in
    # the raw_input so the default fixture still runs a full pipeline.
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
# Mock Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def force_mock_ai_provider():
    """Set AI_PROVIDER=mock for all tests (autouse).

    Stages do `from factory.core.roles import call_ai` — a bound local
    reference that bypasses the mock_ai fixture which patches the root
    factory.core.roles.call_ai. Setting AI_PROVIDER=mock triggers the
    fast shortcut inside call_ai() regardless of which reference is used.

    Tests that explicitly test real AI (test_prod_01_anthropic.py etc.)
    can override with patch.dict(os.environ, {"AI_PROVIDER": "anthropic"}).
    """
    with patch.dict(os.environ, {
        "AI_PROVIDER": "mock",
        "SCOUT_PROVIDER": "mock",
        "DRY_RUN": "true",   # bypasses pre_deploy_gate 15-min Telegram polling loop
        "SKIP_CREDENTIAL_PREFLIGHT": "true",  # bypasses credential pre-flight in tests
    }):
        yield


@pytest.fixture(autouse=True)
def mock_store_pipeline_decision():
    """Patch store_pipeline_decision to no-op (autouse).

    call_ai() always schedules asyncio.create_task(store_pipeline_decision(...))
    for STRATEGIST calls — even when AI_PROVIDER=mock produces a mock response.
    Without this, the background task tries to connect to the full MemoryChain
    (Neo4j + Supabase + Upstash + Turso), causing hangs at test teardown.
    """
    with patch(
        "factory.memory.mother_memory.store_pipeline_decision",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = "mock-decision-id"
        yield mock


@pytest.fixture(autouse=True)
def mock_telegram():
    """Patch all Telegram sends to no-op (autouse)."""
    with patch(
        "factory.telegram.notifications.send_telegram_message",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture(autouse=True)
def mock_persist_state():
    """Patch persist_state to no-op (autouse).

    Prevents E2E tests from making 27+ live Supabase calls per pipeline run.
    Without this, full-pipeline tests take minutes instead of milliseconds.
    """
    with patch(
        "factory.pipeline.graph.persist_state",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = 1
        yield mock


@pytest.fixture(autouse=True)
def mock_build_chain():
    """Patch build_with_chain to no-op (autouse).

    build_with_chain makes real GitHub Actions API calls with up to 20s
    timeouts. Without this, any test that exercises S4 takes 20+ seconds.
    Only patches when factory.infra.build_chain is importable (requires aiohttp).
    """
    try:
        import factory.infra.build_chain  # only patchable when aiohttp installed
        from unittest.mock import MagicMock
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
        yield None  # aiohttp not installed; S4 already degrades gracefully


@pytest.fixture
def mock_ai():
    """Patch call_ai to return stub responses."""
    with patch(
        "factory.core.roles.call_ai",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = '{"stub": true}'
        yield mock


@pytest.fixture
def mock_deploy_window():
    """Patch is_within_deploy_window to always return True.

    Used by full-pipeline integration tests so they pass regardless
    of the wall-clock time (the real check blocks at 23:00 AST).
    """
    with patch(
        "factory.legal.checks.is_within_deploy_window",
        return_value=True,
    ):
        yield


class MockNeo4j:
    """In-memory Neo4j mock with async-compatible methods.

    patterns.py calls `await neo4j_client.find_nodes(...)` and
    `await neo4j_client.create_node(...)` — these must be coroutines.
    """

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
def mock_neo4j():
    """In-memory Neo4j mock (autouse).

    S8 handoff calls get_neo4j() to store patterns/docs in Mother Memory.
    Without this, any test that exercises S8 makes live Neo4j Aura calls,
    which can timeout or hit connection limits when tests run concurrently.
    """
    neo4j = MockNeo4j()
    with patch(
        "factory.integrations.neo4j.get_neo4j",
        return_value=neo4j,
    ):
        yield neo4j


# ═══════════════════════════════════════════════════════════════════
# File Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_binary():
    """Temporary binary file for delivery tests."""
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".bin", mode="wb",
    ) as f:
        f.write(b"fake binary content " * 100)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def tmp_ipa():
    """Temporary .ipa file."""
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".ipa", mode="wb",
    ) as f:
        f.write(b"fake ipa binary " * 50)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def tmp_aab():
    """Temporary .aab file."""
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".aab", mode="wb",
    ) as f:
        f.write(b"fake aab binary " * 50)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)