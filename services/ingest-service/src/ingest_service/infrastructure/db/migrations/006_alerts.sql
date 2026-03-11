-- Migration 006: Alert rules and alert events tables

CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    name            VARCHAR(256) NOT NULL,
    trigger_type    VARCHAR(64) NOT NULL,
    threshold_value NUMERIC,
    days_before     INTEGER,
    document_category VARCHAR(64),
    channels        TEXT[] NOT NULL DEFAULT '{}',
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_tenant_id
    ON alert_rules (tenant_id, enabled);

CREATE TABLE IF NOT EXISTS alert_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'default',
    rule_id         UUID REFERENCES alert_rules (rule_id) ON DELETE CASCADE,
    document_id     UUID,
    trigger_type    VARCHAR(64) NOT NULL,
    message         TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_events_tenant_id
    ON alert_events (tenant_id, acknowledged, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_events_rule_id
    ON alert_events (rule_id);
CREATE INDEX IF NOT EXISTS idx_alert_events_document_id
    ON alert_events (document_id);
