-- Migration: 001 — create documents table
-- Run once during initial deployment

CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY,
    tenant_id       VARCHAR(128)    NOT NULL,
    filename        VARCHAR(512)    NOT NULL,
    document_type   VARCHAR(32)     NOT NULL,
    status          VARCHAR(32)     NOT NULL DEFAULT 'uploaded',
    blob_path       TEXT            NOT NULL,
    raw_text_path   TEXT,
    error_message   TEXT,
    extraction      JSONB,
    uploaded_at     TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    page_count      INTEGER,
    size_bytes      BIGINT,
    content_type    VARCHAR(128)
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_id   ON documents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_status      ON documents (status);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents (uploaded_at DESC);

-- Row-level security policy (enable per tenant isolation)
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
