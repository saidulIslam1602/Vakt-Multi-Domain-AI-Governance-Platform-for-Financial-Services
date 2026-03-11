-- Migration 009: Email ingestion deduplication log
--
-- Purpose: The IMAP poller runs every N minutes. Without deduplication it
-- would re-ingest the same email attachment every poll cycle.
-- This table records every (message_id, attachment_filename) pair that
-- has already been processed. The poller skips any combination that
-- already has a row here.
--
-- message_id  — the RFC 2822 "Message-ID" header value of the source email,
--               e.g. "<CAFx...@mail.gmail.com>"
-- attachment_filename — original filename from Content-Disposition header
-- document_id — the allergo document UUID that was created for this attachment
-- sender      — From: address of the email (for audit trail)
-- subject     — Subject: line of the email (for audit trail)

CREATE TABLE IF NOT EXISTS email_ingest_log (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           TEXT        NOT NULL,
    message_id          TEXT        NOT NULL,   -- RFC 2822 Message-ID header
    attachment_filename TEXT        NOT NULL,
    document_id         UUID,                   -- NULL if ingestion failed
    sender              TEXT,
    subject             TEXT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error               TEXT,                   -- populated if ingestion failed

    -- One row per email attachment — never re-process the same attachment
    CONSTRAINT uq_email_ingest_log UNIQUE (tenant_id, message_id, attachment_filename)
);

CREATE INDEX IF NOT EXISTS idx_email_ingest_log_tenant
    ON email_ingest_log (tenant_id, ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_ingest_log_message_id
    ON email_ingest_log (message_id);
