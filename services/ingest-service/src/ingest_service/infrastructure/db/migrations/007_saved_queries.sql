-- Migration: 007 — saved chat queries

CREATE TABLE IF NOT EXISTS saved_queries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   VARCHAR(128)    NOT NULL,
    name        VARCHAR(256)    NOT NULL,
    question    TEXT            NOT NULL,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_queries_tenant_id ON saved_queries (tenant_id, created_at DESC);
