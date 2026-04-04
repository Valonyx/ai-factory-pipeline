"""
AI Factory Pipeline v5.6 — Shared Test Fixtures

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
    state.project_metadata["raw_input"] = "Build a test app"
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
def mock_telegram():
    """Patch all Telegram sends to no-op (autouse)."""
    with patch(
        "factory.telegram.notifications.send_telegram_message",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_ai():
    """Patch call_ai to return stub responses."""
    with patch(
        "factory.core.roles.call_ai",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = '{"stub": true}'
        yield mock


class MockNeo4j:
    """In-memory Neo4j mock."""

    def __init__(self):
        self._nodes = []
        self._id_counter = 0

    def create_node(self, label, props):
        self._id_counter += 1
        node = {"_id": self._id_counter, "_label": label, **props}
        self._nodes.append(node)
        return self._id_counter

    def find_nodes(self, label, filters=None):
        results = [n for n in self._nodes if n["_label"] == label]
        if filters:
            for k, v in filters.items():
                results = [n for n in results if n.get(k) == v]
        return results

    def query(self, cypher, params=None):
        return []


@pytest.fixture
def mock_neo4j():
    """In-memory Neo4j mock."""
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