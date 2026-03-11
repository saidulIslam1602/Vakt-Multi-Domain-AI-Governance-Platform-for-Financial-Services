-- Migration 008: Scheduled alert deduplication log
--
-- Purpose: The contract-renewal scanner runs every day at 08:00.
-- Without deduplication, it would insert a new alert_event for the same
-- contract every single day for 60 days.  This table acts as a "has this
-- milestone already been notified?" ledger.
--
-- A "milestone" is a named checkpoint in the alert timeline, e.g.:
--   '60d'  → first warning at 60 days before expiry
--   '30d'  → second warning at 30 days before expiry
--   '14d'  → urgent warning at 14 days before expiry
--   '7d'   → critical warning at 7 days before expiry
--   '0d'   → expired today
--
-- The scanner inserts a row here the first time a milestone fires, then
-- skips it on subsequent runs for the same (rule_id, document_id, milestone).

CREATE TABLE IF NOT EXISTS scheduled_alert_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT        NOT NULL,
    rule_id         UUID        NOT NULL REFERENCES alert_rules(rule_id) ON DELETE CASCADE,
    document_id     UUID        NOT NULL,
    milestone       VARCHAR(16) NOT NULL,   -- e.g. '60d', '30d', '14d', '7d', '0d'
    fired_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One row per (rule, document, milestone) — never fire the same milestone twice
    CONSTRAINT uq_scheduled_alert_log UNIQUE (rule_id, document_id, milestone)
);

CREATE INDEX IF NOT EXISTS idx_scheduled_alert_log_tenant
    ON scheduled_alert_log (tenant_id, document_id);
