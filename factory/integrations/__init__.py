"""
AI Factory Pipeline v5.6 — Integrations Module

External service integrations: Supabase, GitHub, Neo4j, Anthropic, Perplexity.

NB2 split: anthropic.py is Anthropic-only transport; roles.py owns dispatch.
"""

from factory.integrations.supabase import (
    get_supabase_client,
    compute_state_checksum,
    upsert_pipeline_state,
    get_pipeline_state,
    list_snapshots,
    restore_state,
    upsert_active_project,
    get_active_project,
    archive_project,
    check_operator_whitelist,
    add_operator_to_whitelist,
    set_operator_state_db,
    get_operator_state_db,
    track_monthly_cost,
    get_monthly_costs,
    audit_log,
    SupabaseFallback,
    reset_clients,
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
    call_anthropic,
    call_anthropic_json,
    parse_json_response,
    calculate_cost,
    get_anthropic_client,
)

from factory.integrations.perplexity import (
    call_perplexity,
    PerplexityUnavailableError,
    SONAR_PRO_TRIGGERS,
)

__all__ = [
    # Supabase
    "get_supabase_client", "compute_state_checksum",
    "upsert_pipeline_state", "get_pipeline_state",
    "list_snapshots", "restore_state",
    "upsert_active_project", "get_active_project",
    "archive_project", "check_operator_whitelist",
    "add_operator_to_whitelist", "set_operator_state_db",
    "get_operator_state_db", "track_monthly_cost",
    "get_monthly_costs", "audit_log",
    "SupabaseFallback", "reset_clients",
    # GitHub
    "GitHubClient", "get_github",
    "github_commit_file", "github_commit_binary", "github_reset_to_commit",
    # Neo4j
    "Neo4jClient", "get_neo4j", "neo4j_run",
    "NODE_TYPES", "JANITOR_EXEMPT",
    # Anthropic
    "call_anthropic", "call_anthropic_json",
    "parse_json_response", "calculate_cost", "get_anthropic_client",
    # Perplexity
    "call_perplexity", "PerplexityUnavailableError", "SONAR_PRO_TRIGGERS",
]