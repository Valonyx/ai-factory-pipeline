"""
AI Factory Pipeline v5.8.12 — Tests for Mother Memory Retrieval Layer
Issue 21: Verifies structured-node store helpers and retrieval functions.
"""
from __future__ import annotations

import pytest
import asyncio
import factory.memory.mother_memory as _mm
from factory.memory.mother_memory import (
    store_requirement, store_screen, store_api_endpoint,
    store_data_model, store_legal_clause, store_source_file,
)
from factory.memory.retrieval import (
    get_requirements, get_screens, get_api_spec,
    get_data_models, get_legal_clauses_for, get_related_files,
    similar_patterns_across_projects, check_consistency,
)
from factory.core.context_bridge import pack_context
from factory.core.state import PipelineState, Stage


# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_fallback_insights():
    """Clear the in-process insight cache before each test."""
    _mm._fallback_insights.clear()
    yield
    _mm._fallback_insights.clear()


def _make_state(project_id: str = "test-retr-proj") -> PipelineState:
    state = PipelineState(project_id=project_id, operator_id="op-test")
    return state


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_and_retrieve_requirement():
    pid = "proj-req-01"
    await store_requirement(
        project_id=pid, operator_id="op1",
        req_id="REQ-001", description="User can log in",
        priority="high", acceptance_criteria="Given valid credentials, user sees dashboard",
        source_stage="S2_BLUEPRINT",
    )
    results = await get_requirements(pid)
    assert len(results) == 1
    assert "REQ-001" in results[0]["content"]
    assert "User can log in" in results[0]["content"]


@pytest.mark.asyncio
async def test_store_and_retrieve_screen():
    pid = "proj-scr-01"
    await store_screen(
        project_id=pid, operator_id="op1",
        screen_id="SCR-001", name="LoginScreen",
        purpose="Authenticate the user",
        components=["EmailField", "PasswordField", "LoginButton"],
        api_bindings=["/auth/login"],
    )
    results = await get_screens(pid)
    assert len(results) == 1
    assert "LoginScreen" in results[0]["content"]
    assert "EmailField" in results[0]["content"]


@pytest.mark.asyncio
async def test_store_and_retrieve_api_endpoint():
    pid = "proj-api-01"
    await store_api_endpoint(
        project_id=pid, operator_id="op1",
        path="/auth/login", method="POST",
        request_schema='{"email": "string", "password": "string"}',
        response_schema='{"token": "string"}',
        auth="none",
    )
    results = await get_api_spec(pid)
    assert len(results) == 1
    assert "/auth/login" in results[0]["content"]
    assert "POST" in results[0]["content"]


@pytest.mark.asyncio
async def test_store_and_retrieve_data_model():
    pid = "proj-dm-01"
    await store_data_model(
        project_id=pid, operator_id="op1",
        name="User",
        fields='[{"name": "email", "type": "string"}, {"name": "created_at", "type": "timestamp"}]',
        relations='[{"ref": "Order", "type": "has_many"}]',
    )
    results = await get_data_models(pid)
    assert len(results) == 1
    assert "MODEL:User" in results[0]["content"]
    assert "email" in results[0]["content"]


@pytest.mark.asyncio
async def test_store_and_retrieve_legal_clause():
    pid = "proj-legal-01"
    await store_legal_clause(
        project_id=pid, operator_id="op1",
        doc="privacy_policy", section="Data Retention",
        body="User data is retained for 90 days after account deletion.",
        jurisdiction="KSA", citation="PDPL Article 18",
    )
    results = await get_legal_clauses_for(pid)
    assert len(results) == 1
    assert "privacy_policy" in results[0]["content"]
    assert "PDPL" in results[0]["content"]


@pytest.mark.asyncio
async def test_store_and_retrieve_source_file():
    pid = "proj-file-01"
    await store_source_file(
        project_id=pid, operator_id="op1",
        path="lib/screens/login_screen.dart",
        purpose="Login screen implementation",
        exported_symbols=["LoginScreen", "LoginForm"],
        sloc=142,
    )
    results = await get_related_files(pid)
    assert len(results) == 1
    assert "login_screen.dart" in results[0]["content"]
    assert "sloc:142" in results[0]["content"]


@pytest.mark.asyncio
async def test_similar_patterns_across_projects():
    # Store two insights with keyword "authentication"
    await store_requirement(
        project_id="proj-A", operator_id="op1",
        req_id="R1", description="authentication via OAuth2",
        priority="high", acceptance_criteria="OAuth flow completes",
        source_stage="S2",
    )
    await store_api_endpoint(
        project_id="proj-B", operator_id="op2",
        path="/auth/oauth", method="GET",
        request_schema="", response_schema="",
        auth="authentication required",
    )
    results = await similar_patterns_across_projects("authentication")
    assert len(results) >= 2
    contents = [r["content"] for r in results]
    assert any("authentication" in c.lower() for c in contents)


@pytest.mark.asyncio
async def test_check_consistency_missing_file():
    pid = "proj-cons-01"
    # Store a screen named "login" but no matching source file
    await store_screen(
        project_id=pid, operator_id="op1",
        screen_id="SCR-001", name="login",
        purpose="Login screen",
        components=["EmailField"],
        api_bindings=[],
    )
    issues = await check_consistency(pid)
    assert len(issues) > 0
    assert any("login" in issue for issue in issues)


@pytest.mark.asyncio
async def test_check_consistency_present_file():
    pid = "proj-cons-02"
    # Store a screen named "login" AND a matching source file
    await store_screen(
        project_id=pid, operator_id="op1",
        screen_id="SCR-001", name="login",
        purpose="Login screen",
        components=["EmailField"],
        api_bindings=[],
    )
    await store_source_file(
        project_id=pid, operator_id="op1",
        path="lib/screens/login_screen.dart",
        purpose="Login screen implementation",
        exported_symbols=["LoginScreen"],
        sloc=100,
    )
    issues = await check_consistency(pid)
    assert issues == []


@pytest.mark.asyncio
async def test_pack_context_s4_includes_requirements():
    pid = "proj-pc-01"
    state = _make_state(pid)
    # Seed requirements and screens
    await store_requirement(
        project_id=pid, operator_id="op1",
        req_id="R1", description="User authentication feature",
        priority="high", acceptance_criteria="Login works",
        source_stage="S2",
    )
    await store_screen(
        project_id=pid, operator_id="op1",
        screen_id="SCR-001", name="HomeScreen",
        purpose="Main home screen",
        components=["NavBar"],
        api_bindings=[],
    )
    result = await pack_context(state, "S4_CODEGEN", budget_tokens=1000)
    assert "[Requirements]" in result
    assert "[Screens]" in result


@pytest.mark.asyncio
async def test_pack_context_respects_budget():
    pid = "proj-pc-02"
    state = _make_state(pid)
    # Seed many requirements so context would exceed a tiny budget
    for i in range(20):
        await store_requirement(
            project_id=pid, operator_id="op1",
            req_id=f"R{i}", description=f"Feature {i} " + "x" * 200,
            priority="medium", acceptance_criteria="AC",
            source_stage="S2",
        )
    result = await pack_context(state, "S4_CODEGEN", budget_tokens=50)
    # budget_chars = 50 * 4 = 200; allow some overhead for base context block
    # The key assertion is that result is not massive
    assert len(result) <= 50 * 4 * 4  # generous overhead for base context
