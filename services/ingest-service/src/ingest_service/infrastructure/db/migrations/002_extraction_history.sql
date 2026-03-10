-- Migration: 002 — extraction history (audit trail) and review workflow

-- Tracks every version of extracted metadata so CFOs can see what changed and who changed it.
CREATE TABLE IF NOT EXISTS extraction_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID            NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id       VARCHAR(128)    NOT NULL,
    extraction      JSONB           NOT NULL,
    changed_by      VARCHAR(256)    NOT NULL,   -- user sub from JWT
    changed_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    change_reason   VARCHAR(512)
);

CREATE INDEX IF NOT EXISTS idx_extraction_history_document_id ON extraction_history (document_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_extraction_history_tenant_id   ON extraction_history (tenant_id);

-- Adds review workflow columns to the documents table.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS needs_review     BOOLEAN         DEFAULT false,
    ADD COLUMN IF NOT EXISTS review_status    VARCHAR(32)     DEFAULT 'not_required',
    ADD COLUMN IF NOT EXISTS reviewed_by      VARCHAR(256),
    ADD COLUMN IF NOT EXISTS reviewed_at      TIMESTAMPTZ;

-- review_status: not_required | pending_review | approved | rejected
CREATE INDEX IF NOT EXISTS idx_documents_needs_review ON documents (tenant_id, needs_review)
    WHERE needs_review = true;
