-- Migration 011: Per-tenant email ingestion configuration
--
-- Purpose: Allow each tenant to self-register their IMAP inbox via the API
-- instead of relying on server-side environment variables.  The email
-- ingestion poller becomes dynamic: on startup, and whenever a config is
-- created / updated / deleted, the EmailPollerManager syncs running pollers
-- with active rows in this table.
--
-- Security model:
--   • imap_password is stored encrypted using pgcrypto's symmetric AES
--     encryption.  The encryption key is supplied at runtime via the
--     ALLERGO_DB_ENCRYPTION_KEY environment variable (32-byte hex string).
--   • The application layer NEVER returns the raw password in API responses
--     (masked as "••••••••" in all responses).
--   • Row-Level Security is enabled (added in 011b below) so tenants can
--     only see / modify their own config.
--
-- Columns:
--   id              — UUID primary key
--   tenant_id       — Allergo tenant identifier (multi-tenant isolation)
--   imap_host       — e.g. "imap.gmail.com"
--   imap_port       — typically 993 (SSL) or 143 (STARTTLS)
--   imap_username   — email address / login username
--   imap_password_enc — AES-encrypted password (bytea)
--   imap_mailbox    — folder to poll, default "INBOX"
--   use_ssl         — SSL on connect vs STARTTLS
--   poll_interval_sec — seconds between poll cycles (min 60, default 300)
--   enabled         — soft toggle without deleting config
--   status          — last known operational status (idle/running/error)
--   status_message  — human-readable error detail when status = 'error'
--   last_polled_at  — timestamp of the most recent successful poll
--   -- Email filter settings (mirrors env-var filter config) --
--   allowed_senders      — CSV of trusted addresses/@domains (empty = any)
--   blocked_senders      — CSV of always-blocked addresses/@domains
--   required_subject_kw  — ALL of these words must appear in subject
--   blocked_subject_kw   — ANY of these words causes email to be skipped
--   min_attachment_bytes — minimum attachment size (default 1 KB)
--   max_attachment_bytes — maximum attachment size (default 50 MB)
--   created_at      — when the config was first saved
--   updated_at      — last modification time

-- ── pgcrypto extension ────────────────────────────────────────────────────────
-- On Azure Database for PostgreSQL Flexible Server, pgcrypto must first be
-- allow-listed in the server's azure.extensions parameter (see postgresql.tf).
-- On vanilla PostgreSQL (local dev / CI) it ships bundled and just needs loading.
--
-- We attempt the CREATE here; if it fails because it has not been allow-listed
-- yet (Azure restriction), the migration aborts with a clear message telling the
-- operator to run `terraform apply` first to update azure.extensions.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION
        'Cannot create pgcrypto extension: %'
        '\nFix: ensure PGCRYPTO is in azure.extensions on the Flexible Server.'
        '\nRun: terraform apply (infra/postgresql.tf already includes PGCRYPTO).'
        '\nOriginal error: %', SQLERRM, SQLERRM;
END;
$$;

CREATE TABLE IF NOT EXISTS email_ingest_configs (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            TEXT        NOT NULL,

    -- ── IMAP connection settings ──────────────────────────────────────────
    imap_host            TEXT        NOT NULL,
    imap_port            INTEGER     NOT NULL DEFAULT 993
                                     CHECK (imap_port BETWEEN 1 AND 65535),
    imap_username        TEXT        NOT NULL,
    imap_password_enc    BYTEA       NOT NULL,  -- AES-encrypted; never returned as-is
    imap_mailbox         TEXT        NOT NULL DEFAULT 'INBOX',
    use_ssl              BOOLEAN     NOT NULL DEFAULT TRUE,
    poll_interval_sec    INTEGER     NOT NULL DEFAULT 300
                                     CHECK (poll_interval_sec >= 60),

    -- ── Operational state ─────────────────────────────────────────────────
    enabled              BOOLEAN     NOT NULL DEFAULT TRUE,
    status               TEXT        NOT NULL DEFAULT 'idle'
                                     CHECK (status IN ('idle', 'running', 'error', 'disabled')),
    status_message       TEXT,
    last_polled_at       TIMESTAMPTZ,

    -- ── Email filter settings ─────────────────────────────────────────────
    allowed_senders      TEXT        NOT NULL DEFAULT '',
    blocked_senders      TEXT        NOT NULL DEFAULT '',
    required_subject_kw  TEXT        NOT NULL DEFAULT '',
    blocked_subject_kw   TEXT        NOT NULL DEFAULT '',
    min_attachment_bytes INTEGER     NOT NULL DEFAULT 1024
                                     CHECK (min_attachment_bytes >= 0),
    max_attachment_bytes INTEGER     NOT NULL DEFAULT 52428800  -- 50 MB
                                     CHECK (max_attachment_bytes > 0),

    -- ── Audit ─────────────────────────────────────────────────────────────
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One config per tenant (can be expanded to many-per-tenant later)
    CONSTRAINT uq_email_config_tenant UNIQUE (tenant_id)
);

-- Fast lookup for the poller manager (loads all enabled configs on startup)
CREATE INDEX IF NOT EXISTS idx_email_ingest_configs_enabled
    ON email_ingest_configs (enabled)
    WHERE enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_email_ingest_configs_tenant
    ON email_ingest_configs (tenant_id);

-- auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION _set_email_config_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_email_ingest_configs_updated_at ON email_ingest_configs;
CREATE TRIGGER trg_email_ingest_configs_updated_at
    BEFORE UPDATE ON email_ingest_configs
    FOR EACH ROW EXECUTE FUNCTION _set_email_config_updated_at();

-- ── Row-Level Security ────────────────────────────────────────────────────────
ALTER TABLE email_ingest_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_ingest_configs FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'email_ingest_configs'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $policy$
            CREATE POLICY tenant_isolation ON email_ingest_configs
                USING (tenant_id = current_tenant_id())
                WITH CHECK (tenant_id = current_tenant_id())
        $policy$;
    END IF;
END;
$$;
