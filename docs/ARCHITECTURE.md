```markdown

# Architecture Reference — AI Factory Pipeline v5.6

Layer-by-layer technical reference. All section references (§) point to the v5.6 specification document.

---

## Layer Overview

| Layer | Package | Files | Lines | Spec Sections |
|-------|---------|-------|-------|---------------|
| P0 Core | `factory.core` | 7 | ~1,980 | §2.1–§2.5 |
| P1 Telegram | `factory.telegram` | 7 | ~2,020 | §5.1–§5.6 |
| P2 Pipeline | `factory.pipeline` | 10 | ~3,150 | §4.0–§4.9 |
| P3 Integrations | `factory.integrations` | 5 | ~1,310 | §7.7–§7.8 |
| P4 Design | `factory.design` | 5 | ~900 | §3.5 |
| P5 Monitoring | `factory.monitoring` | 5 | ~1,090 | §2.14, §7.4.1 |
| P6 War Room | `factory.war_room` | 5 | ~970 | §2.2.4–§2.2.8 |
| P7 Legal | `factory.legal` | 5 | ~1,080 | §2.7.3, §4.1.1, §7.6 |
| P8 Delivery | `factory.delivery` | 5 | ~970 | §7.5, §7.6, FIX-21, FIX-27 |
| P9 Entry Points | root `factory/` | 4 | ~670 | §2.7.1, §7.4.1 |
| P10 Config | root | 6 | ~420 | §8.9 |
| P11 Tests | `tests/` | 10 | ~680 | — |
| P12 Ops | `scripts/` | 6 | ~870 | §6.5, §7.7.1, §8.3 |

**Total: ~16,110 lines across 80+ files**

---

## P0 Core Foundation (§2.1–§2.5)

The core layer defines all shared types, state management, and role contracts.

**`factory.core.state`** — PipelineState is the single mutable object carried through the entire DAG. Key fields: `project_id`, `operator_id`, `current_stage`, `autonomy_mode`, `execution_mode`, `selected_stack`, `total_cost_usd`, `retry_count`, `war_room_active`, `legal_halt`, `project_metadata` (flexible dict for stage outputs).

**`factory.core.roles`** — ROLE_CONTRACTS maps each AIRole to its model string, allowed actions, and cost ceiling. `call_ai()` is the single dispatch function — every AI call in the system goes through it, enabling centralized cost tracking and rate limiting.

**`factory.core.stages`** — Stage enum (IDLE, S0_INTAKE through S8_HANDOFF, HALTED) with linear sequence and transition validation.

**`factory.core.execution`** — ExecutionRouter handles Cloud/Local/Hybrid mode selection. Heartbeat monitor detects local machine availability (3 failures = 90s → auto-failover to Cloud).

**`factory.core.user_space`** — `enforce_user_space()` blocks sudo/su/chmod 777 and rewrites `pip install` → `pip install --user`, `npm install -g` → `npx`.

**`factory.core.secrets`** — GCP Secret Manager integration. REQUIRED_SECRETS (9 keys) validated at startup.

---

## P2 Pipeline Stages (§4.0–§4.9)

Each stage is an async function wrapped by `@pipeline_node` which adds legal hooks and snapshot persistence.

| Stage | Role | Purpose | Cost Target |
|-------|------|---------|-------------|
| S0 Intake | Haiku | Parse Telegram message → structured requirements | <$0.10 |
| S1 Legal | Scout+Strategist | Regulatory classification, PDPL check | <$0.50 |
| S2 Blueprint | Strategist+Engineer | Stack selection, architecture, design mocks | <$2.00 |
| S3 CodeGen | Engineer | Generate full codebase from blueprint | <$8.00 |
| S4 Build | Engineer | Compile/build, resolve dependencies | <$3.00 |
| S5 Test | Engineer+QF | Run tests, generate coverage | <$2.00 |
| S6 Deploy | Engineer | Deploy to cloud infrastructure | <$1.00 |
| S7 Verify | Scout | Post-deploy health checks, URL verification | <$0.50 |
| S8 Handoff | Engineer | Deliver binaries, generate handoff docs | <$1.50 |

**Conditional routing (§2.7.1):**
- S5 fail → S3 (War Room fix cycle, max 3 retries)
- S7 fail → S6 (redeploy, max 2 retries)
- Any legal halt → HALTED state

---

## P5 Monitoring (§2.14)

**Budget Governor** — 4-tier graduated degradation:

| Tier | Threshold | Behavior |
|------|-----------|----------|
| GREEN | 0–80% | Full capabilities |
| AMBER | 80–95% | Scout limited, cost alerts |
| RED | 95–100% | New intake blocked, existing projects continue |
| BLACK | 100%+ | Pipeline halted, operator notified |

**Circuit Breaker** — Per-phase $2.00 limit. Operator can authorize overages.

---

## P6 War Room (§2.2.4–§2.2.8)

Three-level escalation for build/test failures:

| Level | Role | Context | Cost |
|-------|------|---------|------|
| L1 Quick Fix | Haiku | Error + 4KB file context | ~$0.005 |
| L2 Researched | Scout+Strategist | Error + 8KB + research | ~$0.50 |
| L3 War Room | All roles | Full context + Mother Memory | ~$2.00 |

After 3 L3 failures in a row: GUI pivot (switch to alternative approach).

**Mother Memory** (§6.3) stores error patterns, successful fixes, and design DNA in Neo4j. Before each War Room activation, the system queries for known fixes — skipping L1 entirely if a high-confidence match exists.

---

## P7 Legal Engine (§2.7.3)

**14 regulatory aliases** map to canonical bodies (CITC→CST, Saudi Central Bank→SAMA, etc.).

**9 continuous checks** run at 5 stages via pre/post hooks:
1. data_residency_compliance
2. pdpl_consent_requirements
3. no_prohibited_sdks
4. payment_sandbox_default
5. regulatory_body_validation
6. store_age_rating
7. deploy_window_check
8. cross_border_data_check
9. encryption_at_rest

**5 DocuGen templates**: privacy_policy, terms_of_use, data_processing_agreement, cookie_policy, acceptable_use_policy.

---

## P8 Delivery (§7.5, §7.6)

**File routing by size:**
- ≤50MB: Direct Telegram Bot API sendDocument
- 50–200MB: Supabase Storage signed URL (72h TTL)
- >200MB: Same + soft limit warning

**App Store Airlock**: When API upload fails, delivers binary via Telegram with platform-specific manual upload instructions (Transporter for iOS, Play Console for Android) plus policy disclaimer.

**Handoff Intelligence Pack (FIX-27)**: 4 per-project docs always generated + 3 per-program docs when all sibling stacks complete. Stored permanently in Neo4j as HandoffDoc nodes.

---

## Data Layer

**Supabase (11 tables):** pipeline_states, state_snapshots, operator_whitelist, operator_state, active_projects, archived_projects, monthly_costs, audit_log, pipeline_metrics, memory_stats, temp_artifacts.

**Neo4j (12 node types):** Project, Component, ErrorPattern, StackPattern, DesignDNA, RegulatoryDecision, LegalDocTemplate, Graveyard, WarRoomEvent, Pattern, HandoffDoc, StorePolicyEvent.

**State persistence**: Triple-write (Supabase current → Supabase snapshot → GitHub commit). Snapshots enable time-travel restoration via `/restore` command.

---

## Deployment

**Production**: Cloud Run on GCP (me-central1 / Dammam) via `cloudbuild.yaml`.
**Local testing**: `python -m factory.cli "description"` or FastAPI dev server.
**Health**: `/health` (liveness) and `/health-deep` (readiness with dependency checks).
