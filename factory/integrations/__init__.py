"""
AI Factory Pipeline v5.6 — Integrations Module

External service integrations: Supabase, GitHub, Neo4j, Anthropic/Perplexity.
"""

from factory.integrations.supabase import (
    SupabaseClient,
    get_supabase,
    triple_write_persist,
    restore_state,
    SnapshotWriteError,
    ChecksumMismatchError,
)

from factory.integrations.github import (
    GitHubClient,
    get_github,
    github_commit_file,
    github_commit_binary,
    github_reset_to_commit,
)

from factory.integrations.neo4j import (
    Neo4jClient,
    get_neo4j,
    neo4j_run,
    NODE_TYPES,
    JANITOR_EXEMPT,
)

from factory.integrations.anthropic import (
    dispatch_ai_call,
    check_circuit_breaker,
    ROLE_CONTRACTS,
    PHASE_BUDGET_LIMITS,
    SONAR_PRO_TRIGGERS,
    STRATEGIST_USAGE_LIMITS,
    BudgetGovernor,
    budget_governor,
    BudgetTier,
    BudgetExhaustedError,
    BudgetIntakeBlockedError,
)

__all__ = [
    # Supabase
    "SupabaseClient", "get_supabase",
    "triple_write_persist", "restore_state",
    "SnapshotWriteError", "ChecksumMismatchError",
    # GitHub
    "GitHubClient", "get_github",
    "github_commit_file", "github_commit_binary", "github_reset_to_commit",
    # Neo4j
    "Neo4jClient", "get_neo4j", "neo4j_run",
    "NODE_TYPES", "JANITOR_EXEMPT",
    # Anthropic
    "dispatch_ai_call", "check_circuit_breaker",
    "ROLE_CONTRACTS", "PHASE_BUDGET_LIMITS",
    "BudgetGovernor", "budget_governor",
    "BudgetTier", "BudgetExhaustedError", "BudgetIntakeBlockedError",
]