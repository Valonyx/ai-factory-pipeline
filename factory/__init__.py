"""
AI Factory Pipeline v5.8

Automated AI application factory — builds production-grade
mobile and web apps from natural language descriptions.

Layers:
  core        — State, roles, stages, secrets, execution, user-space
  telegram    — Bot, commands, notifications, decisions, airlock, health
  pipeline    — S0-S8 stage implementations
  integrations — Supabase, GitHub, Neo4j, Anthropic
  design      — Contrast, grid, vibe check, visual mocks
  monitoring  — Budget Governor, circuit breaker, cost tracker, health
  war_room    — L1/L2/L3 escalation, patterns
  legal       — Regulatory, legal checks, DocuGen, compliance
  delivery    — File delivery, Airlock, app store, handoff docs

Entry points:
  factory.main          — FastAPI app (Cloud Run)
  factory.orchestrator   — Pipeline DAG + run_pipeline()
  factory.cli           — CLI for local testing
"""

__version__ = "5.8.0"
__pipeline_version__ = "5.8"
__build_tag__ = "F7"