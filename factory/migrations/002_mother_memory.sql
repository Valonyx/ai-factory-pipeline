-- AI Factory Pipeline v5.6 — Mother Memory tables for Supabase
-- Run this once in the Supabase SQL editor (Database → SQL Editor → New query).
-- Safe to re-run — all statements are idempotent (IF NOT EXISTS / OR REPLACE).
--
-- Tables:
--   memory_messages   — every Telegram turn (user + bot, including off-topic)
--   memory_decisions  — pipeline stage decisions (stack, legal, architecture)
--   memory_insights   — long-term operator facts/preferences
--
-- After running this, add your Supabase credentials to .env:
--   SUPABASE_URL=https://<project-ref>.supabase.co
--   SUPABASE_SERVICE_KEY=<service_role_key>   (Settings → API → service_role)

-- ─── memory_messages ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS memory_messages (
    id          TEXT PRIMARY KEY,
    operator_id TEXT        NOT NULL,
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT,
    intent      TEXT        NOT NULL DEFAULT '',
    project_id  TEXT        NOT NULL DEFAULT '',
    session_tag TEXT        NOT NULL DEFAULT '',
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast lookup by operator, newest first
CREATE INDEX IF NOT EXISTS idx_mem_msg_op_ts
    ON memory_messages (operator_id, ts DESC);

-- Sync window queries (get_messages_since)
CREATE INDEX IF NOT EXISTS idx_mem_msg_ts
    ON memory_messages (ts ASC);


-- ─── memory_decisions ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS memory_decisions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT        NOT NULL,
    stage         TEXT        NOT NULL DEFAULT '',
    decision_type TEXT        NOT NULL DEFAULT '',
    content       TEXT,
    operator_id   TEXT        NOT NULL DEFAULT '',
    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mem_dec_proj_ts
    ON memory_decisions (project_id, ts DESC);


-- ─── memory_insights ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS memory_insights (
    id           TEXT PRIMARY KEY,
    operator_id  TEXT        NOT NULL,
    content      TEXT,
    insight_type TEXT        NOT NULL DEFAULT 'preference',
    importance   INTEGER     NOT NULL DEFAULT 3
                             CHECK (importance BETWEEN 1 AND 5),
    project_id   TEXT        NOT NULL DEFAULT '',
    ts           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Most important / most recent insights first
CREATE INDEX IF NOT EXISTS idx_mem_ins_op_imp
    ON memory_insights (operator_id, importance DESC, ts DESC);


-- ─── Row-Level Security (optional but recommended) ──────────────────────────
-- Enable only if you access Supabase from untrusted clients (not needed
-- for the service_role key used by this pipeline).

-- ALTER TABLE memory_messages   ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE memory_decisions  ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE memory_insights   ENABLE ROW LEVEL SECURITY;
