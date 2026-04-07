-- AI Factory Pipeline v5.6 — Core Pipeline Schema for Supabase
-- Run once in Supabase SQL Editor (Database → SQL Editor → New query).
-- All statements are idempotent (IF NOT EXISTS / OR REPLACE).
--
-- Tables:
--   operator_whitelist   — authorized Telegram operators
--   active_projects      — one row per operator's currently running project
--   pipeline_states      — full serialized PipelineState per project
--   state_snapshots      — time-travel snapshots (S0–S8)
--   monthly_costs        — per-operator monthly AI spend tracking
--   audit_log            — immutable append-only action log
--   war_room_incidents   — War Room activations + resolutions
--   build_results        — S4 build outputs + artifact paths
--   compliance_results   — S1 legal check results

-- ─── operator_whitelist ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS operator_whitelist (
    telegram_id     TEXT PRIMARY KEY,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    label           TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- ─── active_projects ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS active_projects (
    operator_id     TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    current_stage   TEXT NOT NULL,
    state_json      JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_active_projects_project_id
    ON active_projects (project_id);

-- ─── pipeline_states ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pipeline_states (
    project_id      TEXT PRIMARY KEY,
    operator_id     TEXT NOT NULL,
    current_stage   TEXT NOT NULL,
    state_json      JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_states_operator
    ON pipeline_states (operator_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_states_stage
    ON pipeline_states (current_stage);

-- ─── state_snapshots (time-travel) ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS state_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    project_id      TEXT NOT NULL,
    operator_id     TEXT NOT NULL,
    stage           TEXT NOT NULL,
    snapshot_index  INT  NOT NULL,
    state_json      JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_project
    ON state_snapshots (project_id, snapshot_index DESC);

-- ─── monthly_costs ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS monthly_costs (
    id              BIGSERIAL PRIMARY KEY,
    operator_id     TEXT NOT NULL,
    month           TEXT NOT NULL,              -- YYYY-MM
    provider        TEXT NOT NULL,
    total_usd       NUMERIC(10, 4) NOT NULL DEFAULT 0,
    request_count   INT  NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (operator_id, month, provider)
);

-- ─── audit_log ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    operator_id     TEXT NOT NULL,
    project_id      TEXT,
    action          TEXT NOT NULL,
    details         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_operator
    ON audit_log (operator_id, created_at DESC);

-- ─── war_room_incidents ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS war_room_incidents (
    id              BIGSERIAL PRIMARY KEY,
    project_id      TEXT NOT NULL,
    operator_id     TEXT NOT NULL,
    level           INT  NOT NULL,              -- 1=QuickFix, 2=Strategist, 3=Operator
    stage           TEXT NOT NULL,
    error_summary   TEXT NOT NULL,
    resolution      TEXT,
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    duration_sec    INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_war_room_project
    ON war_room_incidents (project_id, created_at DESC);

-- ─── build_results ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS build_results (
    id              BIGSERIAL PRIMARY KEY,
    project_id      TEXT NOT NULL,
    operator_id     TEXT NOT NULL,
    stack           TEXT NOT NULL,
    provider        TEXT NOT NULL,              -- macincloud|github_actions|codemagic
    platforms       TEXT[] NOT NULL DEFAULT '{}',
    success         BOOLEAN NOT NULL,
    artifacts       JSONB NOT NULL DEFAULT '{}',
    duration_sec    INT,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_build_results_project
    ON build_results (project_id, created_at DESC);

-- ─── compliance_results ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS compliance_results (
    id              BIGSERIAL PRIMARY KEY,
    project_id      TEXT NOT NULL,
    operator_id     TEXT NOT NULL,
    region          TEXT NOT NULL,
    passed          BOOLEAN NOT NULL,
    halt_triggered  BOOLEAN NOT NULL DEFAULT FALSE,
    checks          JSONB NOT NULL DEFAULT '[]',
    documents       JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compliance_project
    ON compliance_results (project_id);

-- ─── archived_projects ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS archived_projects (
    project_id      TEXT PRIMARY KEY,
    operator_id     TEXT NOT NULL,
    final_stage     TEXT NOT NULL,
    state_json      JSONB NOT NULL DEFAULT '{}',
    archived_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_archived_projects_operator
    ON archived_projects (operator_id, archived_at DESC);
