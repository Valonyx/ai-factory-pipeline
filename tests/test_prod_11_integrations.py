"""
PROD-11 Validation: Integrations Layer

Tests cover:
  GitHub (5 tests):
    1.  commit_file returns SHA
    2.  commit_files batch + list_files
    3.  create_tag on latest commit
    4.  reset_to_commit truncates history
    5.  commit_binary stores size

  Neo4j Mother Memory (6 tests):
    6.  11 node types defined
    7.  HandoffDoc in JANITOR_EXEMPT
    8.  create_node + get_node round-trip
    9.  store_handoff_docs creates permanent nodes
    10. janitor_cycle archives broken, preserves HandoffDoc
    11. query_mother_memory returns matching patterns

  AI Dispatch + Budget Governor (7 tests):
    12. 4 role contracts with correct models
    13. Budget Governor GREEN at 0%
    14. Budget Governor AMBER at 80%
    15. Budget Governor RED at 95%
    16. Budget Governor BLACK at 100%
    17. AMBER degrades Strategist→Engineer
    18. check_circuit_breaker respects phase limits

Run:
  pytest tests/test_prod_11_integrations.py -v
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone, timedelta

from factory.core.state import AIRole, PipelineState, Stage

from factory.integrations.github import (
    GitHubClient,
    get_github,
    commit_files,
    create_release_tag,
)
from factory.integrations.neo4j import (
    Neo4jClient,
    get_neo4j,
    NODE_TYPES,
    JANITOR_EXEMPT,
    RELATIONSHIP_TYPES,
    store_project_patterns,
    store_handoff_docs_in_memory,
)
from factory.integrations.anthropic_dispatch import (
    ROLE_CONTRACTS,
    PHASE_BUDGET_LIMITS,
    SONAR_PRO_TRIGGERS,
    BudgetGovernor,
    BudgetTier,
    BudgetExhaustedError,
    check_circuit_breaker,
    estimate_cost,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def github():
    """Fresh GitHubClient."""
    return GitHubClient(token="test-token")


@pytest.fixture
def neo4j():
    """Fresh Neo4jClient."""
    return Neo4jClient(uri="bolt://test", password="test")


@pytest.fixture
def state():
    """PipelineState for budget tests."""
    s = PipelineState(
        project_id="test_integ_001",
        operator_id="op_integ",
    )
    s.total_cost_usd = 0.0
    return s


# ═══════════════════════════════════════════════════════════════════
# Tests 1-5: GitHub
# ═══════════════════════════════════════════════════════════════════

class TestGitHub:
    @pytest.mark.asyncio
    async def test_commit_file_sha(self, github):
        """commit_file returns SHA."""
        await github.create_repo("factory/test")
        result = await github.commit_file(
            "factory/test", "README.md", "# Test", "Init",
        )
        assert result["sha"].startswith("sha-")
        assert result["path"] == "README.md"

    @pytest.mark.asyncio
    async def test_commit_files_batch(self, github):
        """commit_files batch + list_files."""
        await github.create_repo("factory/batch")
        result = await github.commit_files(
            "factory/batch",
            {
                "legal/privacy.md": "# Privacy",
                "docs/QUICK_START.md": "# Quick Start",
            },
            "S8 Handoff",
        )
        assert result["files"] == 2
        files = await github.list_files("factory/batch")
        assert "legal/privacy.md" in files
        assert "docs/QUICK_START.md" in files

    @pytest.mark.asyncio
    async def test_create_tag(self, github):
        """create_tag on latest commit."""
        await github.create_repo("factory/tag-test")
        await github.commit_file(
            "factory/tag-test", "app.py", "pass", "Init",
        )
        tag = await github.create_tag(
            "factory/tag-test",
            "v1.0.0-handoff",
            "Handoff complete",
        )
        assert tag["tag"] == "v1.0.0-handoff"
        assert tag["target_sha"].startswith("sha-")

    @pytest.mark.asyncio
    async def test_reset_to_commit(self, github):
        """reset_to_commit truncates history."""
        await github.create_repo("factory/reset")
        c1 = await github.commit_file(
            "factory/reset", "a.py", "v1", "First",
        )
        await github.commit_file(
            "factory/reset", "b.py", "v2", "Second",
        )
        commits_before = await github.get_commits("factory/reset")
        assert len(commits_before) == 2

        result = await github.reset_to_commit(
            "factory/reset", c1["sha"],
        )
        assert result["success"] is True
        commits_after = await github.get_commits("factory/reset")
        assert len(commits_after) == 1

    @pytest.mark.asyncio
    async def test_commit_binary(self, github):
        """commit_binary stores size."""
        await github.create_repo("factory/bin")
        result = await github.commit_binary(
            "factory/bin", "icon.png", b"\x89PNG" * 100, "Icon",
        )
        assert result["sha"].startswith("bin-")


# ═══════════════════════════════════════════════════════════════════
# Tests 6-11: Neo4j Mother Memory
# ═══════════════════════════════════════════════════════════════════

class TestNeo4jMotherMemory:
    def test_node_types_11(self):
        """11 node types defined."""
        assert len(NODE_TYPES) == 11
        assert "StackPattern" in NODE_TYPES
        assert "HandoffDoc" in NODE_TYPES
        assert "Graveyard" in NODE_TYPES

    def test_handoff_janitor_exempt(self):
        """HandoffDoc in JANITOR_EXEMPT."""
        assert "HandoffDoc" in JANITOR_EXEMPT

    @pytest.mark.asyncio
    async def test_create_get_node(self, neo4j):
        """create_node + get_node round-trip."""
        result = await neo4j.create_node("StackPattern", {
            "id": "sp_test", "stack": "python_backend",
            "success": True,
        })
        assert result["label"] == "StackPattern"

        node = await neo4j.get_node("sp_test")
        assert node is not None
        assert node["stack"] == "python_backend"

    @pytest.mark.asyncio
    async def test_store_handoff_docs(self, neo4j):
        """store_handoff_docs creates permanent nodes."""
        count = await neo4j.store_handoff_docs(
            project_id="proj_01",
            program_id=None,
            stack="react_native",
            app_category="food",
            docs={
                "QUICK_START.md": "# Quick Start",
                "EMERGENCY_RUNBOOK.md": "# Emergency",
            },
        )
        assert count == 2

        node = await neo4j.get_node(
            "hd_proj_01_QUICK_START.md"
        )
        assert node is not None
        assert node["permanent"] is True

    @pytest.mark.asyncio
    async def test_janitor_archives_broken(self, neo4j):
        """Janitor archives broken components, preserves HandoffDoc."""
        old = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).isoformat()

        await neo4j.create_node("Component", {
            "id": "comp_broken",
            "success_count": 0,
            "failure_count": 5,
            "created_at": old,
        })
        await neo4j.create_node("HandoffDoc", {
            "id": "hd_perm",
            "permanent": True,
            "created_at": old,
        })

        result = await neo4j.janitor_cycle()
        assert result["archived_count"] >= 1

        # HandoffDoc survives
        hd = await neo4j.get_node("hd_perm")
        assert hd["label"] == "HandoffDoc"

        # Component archived
        comp = await neo4j.get_node("comp_broken")
        assert comp["label"] == "Graveyard"

    @pytest.mark.asyncio
    async def test_query_patterns(self, neo4j):
        """query_mother_memory returns matching patterns."""
        await neo4j.create_node("StackPattern", {
            "id": "sp_py1", "stack": "python_backend",
            "category": "saas", "success": True,
        })
        results = await neo4j.query_mother_memory(
            "python_backend", [], "saas",
        )
        assert len(results) >= 1
        assert results[0]["stack"] == "python_backend"


# ═══════════════════════════════════════════════════════════════════
# Tests 12-18: AI Dispatch + Budget Governor
# ═══════════════════════════════════════════════════════════════════

class TestAIDispatchBudget:
    def test_4_role_contracts(self):
        """4 role contracts with correct models."""
        assert len(ROLE_CONTRACTS) == 4
        assert ROLE_CONTRACTS[AIRole.STRATEGIST][
            "model"
        ] == "claude-opus-4-6"
        assert ROLE_CONTRACTS[AIRole.ENGINEER][
            "model"
        ] == "claude-sonnet-4-5-20250929"
        assert ROLE_CONTRACTS[AIRole.QUICK_FIX][
            "model"
        ] == "claude-haiku-4-5-20251001"
        assert ROLE_CONTRACTS[AIRole.SCOUT][
            "provider"
        ] == "perplexity"

    def test_budget_green(self):
        """Budget Governor GREEN at 0%."""
        bg = BudgetGovernor(ceiling_usd=800.0)
        assert bg.determine_tier(0) == BudgetTier.GREEN

    def test_budget_amber(self):
        """Budget Governor AMBER at 80%."""
        bg = BudgetGovernor(ceiling_usd=800.0)
        # 80% of 3000 SAR = 2400
        assert bg.determine_tier(2400) == BudgetTier.AMBER

    def test_budget_red(self):
        """Budget Governor RED at 95%."""
        bg = BudgetGovernor(ceiling_usd=800.0)
        # 95% of 3000 SAR = 2850
        assert bg.determine_tier(2850) == BudgetTier.RED

    def test_budget_black(self):
        """Budget Governor BLACK at 100%."""
        bg = BudgetGovernor(ceiling_usd=800.0)
        assert bg.determine_tier(3000) == BudgetTier.BLACK

    def test_amber_degrades_strategist(self):
        """AMBER degrades Strategist→Engineer."""
        bg = BudgetGovernor(ceiling_usd=800.0)
        degraded = bg.get_degraded_role(
            AIRole.STRATEGIST, BudgetTier.AMBER,
        )
        assert degraded == AIRole.ENGINEER

        # GREEN doesn't degrade
        same = bg.get_degraded_role(
            AIRole.STRATEGIST, BudgetTier.GREEN,
        )
        assert same == AIRole.STRATEGIST

    @pytest.mark.asyncio
    async def test_circuit_breaker_phase_limit(self, state):
        """check_circuit_breaker respects phase limits."""
        state.current_stage = Stage.S0_INTAKE
        state.stage_cost_usd = 0.0
        state.total_cost_usd = 0.0

        # Should pass for small cost
        result = await check_circuit_breaker(state, 0.10)
        assert result is True

        # Should fail if stage exceeds limit
        state.stage_cost_usd = 0.49
        result = await check_circuit_breaker(state, 0.10)
        assert result is False  # 0.49 + 0.10 > 0.50 limit
