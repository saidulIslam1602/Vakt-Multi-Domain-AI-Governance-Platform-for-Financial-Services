-- Migration: 003 — outbound webhook configuration per tenant

CREATE TABLE IF NOT EXISTS webhooks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       VARCHAR(128)    NOT NULL,
    name            VARCHAR(256)    NOT NULL,
    url             TEXT            NOT NULL,
    secret          VARCHAR(512)    NOT NULL,   -- HMAC-SHA256 signing secret (stored encrypted)
    events          TEXT[]          NOT NULL,   -- e.g. ARRAY['document.ready', 'document.failed']
    enabled         BOOLEAN         NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_tenant_id ON webhooks (tenant_id);

-- Delivery log — records every outbound webhook attempt and its outcome.
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id      UUID            NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type      VARCHAR(64)     NOT NULL,
    document_id     UUID,
    payload         JSONB           NOT NULL,
    status_code     INTEGER,
    response_body   TEXT,
    success         BOOLEAN         NOT NULL DEFAULT false,
    attempt         INTEGER         NOT NULL DEFAULT 1,
    delivered_at    TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook_id ON webhook_deliveries (webhook_id, delivered_at DESC);
