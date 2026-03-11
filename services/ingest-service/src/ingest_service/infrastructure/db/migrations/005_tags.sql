-- Migration: 005 — document tagging

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';

-- GIN index for fast array containment queries  (e.g. WHERE tags @> ARRAY['urgent'])
CREATE INDEX IF NOT EXISTS idx_documents_tags
    ON documents USING GIN (tags);
