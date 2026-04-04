# AI Factory Pipeline v5.6

Automated AI application factory — builds production-grade mobile and web apps from natural language descriptions, targeting the KSA market.

## Overview

The AI Factory Pipeline takes a Telegram message describing an app idea and produces a deployed, store-ready application. Four AI roles collaborate through a 9-stage pipeline with legal compliance, budget governance, and cross-project learning.

**AI Roles:**
- **Scout** (Perplexity Sonar) — Research, market intel, bug investigation
- **Strategist** (Claude Opus 4.6) — Architecture, decisions, War Room management
- **Engineer** (Claude Sonnet 4.5) — Code generation, file creation, fixes
- **Quick Fix** (Claude Haiku 4.5) — Syntax fixes, intake parsing, GUI supervision

**Pipeline Stages:** S0 Intake → S1 Legal Gate → S2 Blueprint → S3 CodeGen → S4 Build → S5 Test → S6 Deploy → S7 Verify → S8 Handoff

**Supported Stacks:** FlutterFlow, Swift, Kotlin, React Native, Python Backend, Unity

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url> && cd ai-factory-pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Run migrations
python -m scripts.migrate_supabase
python -m scripts.migrate_neo4j

# 4. Start
python -m factory.main
# Or use CLI: python -m factory.cli "Build an e-commerce app for KSA"


Project Structure
ai-factory-pipeline/
├── factory/
│   ├── core/           # State, roles, stages, secrets, execution
│   ├── telegram/       # Bot, commands, notifications, decisions
│   ├── pipeline/       # S0-S8 stage implementations
│   ├── integrations/   # Supabase, GitHub, Neo4j, Anthropic
│   ├── design/         # Contrast, grid, vibe check, visual mocks
│   ├── monitoring/     # Budget Governor, circuit breaker, health
│   ├── war_room/       # L1/L2/L3 escalation, pattern storage
│   ├── legal/          # Regulatory, checks, DocuGen, compliance
│   ├── delivery/       # File delivery, Airlock, app store, handoff
│   ├── orchestrator.py # DAG construction, run_pipeline()
│   ├── main.py         # FastAPI entry point
│   ├── cli.py          # CLI for local testing
│   └── config.py       # Consolidated configuration
├── scripts/
│   ├── migrate_supabase.py  # 11-table schema
│   ├── migrate_neo4j.py     # 18 indexes + constraints
│   ├── janitor.py           # Cleanup agent (§6.5)
│   └── setup_secrets.py     # GCP Secret Manager bootstrap
├── tests/                   # pytest suite (~90 tests)
├── Dockerfile               # Cloud Run container
├── cloudbuild.yaml          # GCP Cloud Build
├── requirements.txt
├── pyproject.toml
└── .env.example


Architecture
See docs/ARCHITECTURE.md for the full layer-by-layer reference.

The pipeline runs as a LangGraph DAG with conditional routing:

S5→S3 retry loop: When tests fail, War Room attempts fixes (max 3 cycles)
S7→S6 redeploy loop: When verification fails (max 2 retries)
Legal hooks: Pre/post checks at every stage via @pipeline_node decorator
Budget Governor: 4-tier degradation (GREEN→AMBER→RED→BLACK)
Key Features
KSA Compliance: PDPL data residency (me-central1), CST/SAMA/NCA regulatory checks
Budget Control: $300/month default, 4-tier governor, per-phase circuit breakers
War Room: L1 Quick Fix → L2 Researched → L3 Full War Room escalation
Mother Memory: Neo4j knowledge graph learns from every project
Handoff Intelligence Pack: 4 per-project + 3 per-program operator documents (FIX-27)
App Store Delivery: Automated upload with Airlock fallback for manual submission
Operator Guide
See docs/OPERATOR_GUIDE.md for the non-technical operator manual.

Specification
The authoritative source for all technical decisions is the v5.6 AI Factory Pipeline Specifications Document (11,845 lines). All code references specific sections (e.g., §2.7.1, §7.5 [C3]).

Development
# Run tests
python -m pytest tests/ -v

# Health check
python -m factory.cli --health

# Budget status
python -m factory.cli --status

# Janitor (dry-run)
python -m scripts.janitor all
License
Proprietary
