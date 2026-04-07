-- AI Factory Pipeline v5.6 — Revenue, Analytics & Client Tables
-- Run once in Supabase SQL Editor after 003_pipeline_schema.sql.
-- All statements are idempotent (IF NOT EXISTS / OR REPLACE).
--
-- Tables:
--   revenue_invoices   — logged invoices (/invoice command)
--   revenue_clients    — operator's customer records (/clients command)
--   pipeline_metrics   — pipeline run statistics (/analytics command)

-- ─── revenue_invoices ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS revenue_invoices (
    id              TEXT PRIMARY KEY,           -- 8-char UUID prefix
    operator_id     TEXT NOT NULL,
    client_name     TEXT NOT NULL,
    amount          NUMERIC(14, 2) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    description     TEXT NOT NULL,
    project_id      TEXT,
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_operator
    ON revenue_invoices (operator_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_invoices_client
    ON revenue_invoices (operator_id, client_name);

-- ─── revenue_clients ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS revenue_clients (
    id              TEXT PRIMARY KEY,           -- 8-char UUID prefix
    operator_id     TEXT NOT NULL,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    company         TEXT NOT NULL DEFAULT '',
    project_ids     TEXT[] NOT NULL DEFAULT '{}',
    total_invoiced  NUMERIC(14, 2) NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (operator_id, name)
);

CREATE INDEX IF NOT EXISTS idx_clients_operator
    ON revenue_clients (operator_id, total_invoiced DESC);

-- ─── pipeline_metrics ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pipeline_metrics (
    project_id          TEXT PRIMARY KEY,
    operator_id         TEXT NOT NULL,
    stack               TEXT NOT NULL,
    pipeline_mode       TEXT NOT NULL DEFAULT 'create',
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    success             BOOLEAN NOT NULL,
    total_cost_usd      NUMERIC(10, 4) NOT NULL DEFAULT 0,
    duration_seconds    NUMERIC(10, 2) NOT NULL DEFAULT 0,
    stages_completed    INT  NOT NULL DEFAULT 0,
    error_stage         TEXT,
    deployment_targets  TEXT[] NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_metrics_operator
    ON pipeline_metrics (operator_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_metrics_stack
    ON pipeline_metrics (operator_id, stack);
