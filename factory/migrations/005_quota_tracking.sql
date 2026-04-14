-- AI Factory Pipeline v5.8 — Provider Quota Usage Tracking
-- Run once in Supabase SQL Editor (Database → SQL Editor → New query).
-- All statements are idempotent (IF NOT EXISTS / OR REPLACE).
--
-- Table: provider_quota_usage
--   Tracks monthly call/token/cost usage per AI provider.
--   Consumed by factory.core.quota_tracker.QuotaTracker (v5.8).
--   Upserted on every AI call via QuotaTracker._persist_provider().
--
-- Spec Authority: v5.8 §Phase 1.5 — ModeRouter + QuotaTracker

-- ─── provider_quota_usage ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS provider_quota_usage (
    id              BIGSERIAL PRIMARY KEY,
    provider_name   TEXT        NOT NULL,
    month_key       TEXT        NOT NULL,          -- 'YYYY-MM'
    calls           INTEGER     NOT NULL DEFAULT 0,
    tokens          BIGINT      NOT NULL DEFAULT 0,
    cost_usd        DECIMAL(12, 6) NOT NULL DEFAULT 0.0,
    is_exhausted    BOOLEAN     NOT NULL DEFAULT FALSE,
    exhausted_at    TIMESTAMPTZ,
    next_reset_at   TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_provider_month UNIQUE (provider_name, month_key)
);

-- Fast lookups by provider or month
CREATE INDEX IF NOT EXISTS idx_quota_provider
    ON provider_quota_usage (provider_name);

CREATE INDEX IF NOT EXISTS idx_quota_month
    ON provider_quota_usage (month_key);

CREATE INDEX IF NOT EXISTS idx_quota_exhausted
    ON provider_quota_usage (is_exhausted)
    WHERE is_exhausted = TRUE;

-- ─── Row-level security (inherit from existing tables policy) ──────────────
-- The pipeline service role bypasses RLS — no additional policy needed.
-- Public reads are disabled by default in Supabase projects.

-- ─── Helper view: current-month quota status ───────────────────────────────

CREATE OR REPLACE VIEW v_quota_current_month AS
SELECT
    provider_name,
    month_key,
    calls,
    tokens,
    ROUND(cost_usd::NUMERIC, 4)            AS cost_usd,
    is_exhausted,
    exhausted_at,
    next_reset_at,
    updated_at
FROM provider_quota_usage
WHERE month_key = TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM')
ORDER BY provider_name;
