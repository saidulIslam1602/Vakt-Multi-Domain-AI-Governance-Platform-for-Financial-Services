-- Migration 014: Banking compliance tables
-- Introduces three tables for the banking_compliance agent session:
--   transaction_records  — demo transaction data with AML/KYC risk attributes
--   compliance_flags     — governed AML flags requiring human review before action
--   sar_drafts           — SAR narrative drafts requiring human approval before filing
--
-- All tables are tenant-scoped and RLS-protected, consistent with the
-- existing multi-tenant isolation pattern in this database.

-- ── transaction_records ───────────────────────────────────────────────────────
-- Represents financial transactions ingested from a core banking system.
-- In production this would be a view over the core banking ledger; here it
-- is a standalone demo table populated by the seed migration below.

CREATE TABLE IF NOT EXISTS transaction_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    amount_nok      NUMERIC(18, 2) NOT NULL,
    counterparty    TEXT NOT NULL,           -- customer/entity ID (no full PII)
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    risk_score      NUMERIC(5, 2) NOT NULL DEFAULT 0,  -- 0–100; >=70 HIGH, >=85 CRITICAL
    kyc_status      TEXT NOT NULL DEFAULT 'verified'
                        CHECK (kyc_status IN ('verified', 'pending', 'expired', 'rejected')),
    pep_flag        BOOLEAN NOT NULL DEFAULT false,
    transaction_type TEXT NOT NULL DEFAULT 'transfer'
                        CHECK (transaction_type IN (
                            'transfer', 'cash_deposit', 'cash_withdrawal',
                            'international_wire', 'internal_transfer', 'payment'
                        )),
    currency        TEXT NOT NULL DEFAULT 'NOK',
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transaction_records_tenant
    ON transaction_records (tenant_id);
CREATE INDEX IF NOT EXISTS idx_transaction_records_risk
    ON transaction_records (tenant_id, risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_transaction_records_pep
    ON transaction_records (tenant_id, pep_flag)
    WHERE pep_flag = true;
CREATE INDEX IF NOT EXISTS idx_transaction_records_kyc
    ON transaction_records (tenant_id, kyc_status)
    WHERE kyc_status IN ('expired', 'pending');
CREATE INDEX IF NOT EXISTS idx_transaction_records_amount
    ON transaction_records (tenant_id, amount_nok DESC);
CREATE INDEX IF NOT EXISTS idx_transaction_records_timestamp
    ON transaction_records (tenant_id, timestamp DESC);

ALTER TABLE transaction_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY transaction_records_tenant_isolation ON transaction_records
    USING (tenant_id = current_setting('app.current_tenant', true));

-- ── compliance_flags ──────────────────────────────────────────────────────────
-- Governed AML/KYC compliance flags created by the banking_compliance agent.
-- Status transitions: open → reviewed | escalated
-- A human compliance officer MUST review before any regulatory action is taken.
-- The agent can only create flags (status='open'); transitions require human API calls.

CREATE TABLE IF NOT EXISTS compliance_flags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    transaction_id  TEXT NOT NULL,           -- references transaction_records.id (loose FK for demo)
    flag_reason     TEXT NOT NULL
                        CHECK (flag_reason IN (
                            'structuring', 'velocity_violation', 'pep_counterparty',
                            'layering_pattern', 'unusual_geography', 'kyc_mismatch',
                            'threshold_breach', 'other'
                        )),
    evidence_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_level      TEXT NOT NULL DEFAULT 'HIGH'
                        CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'reviewed', 'escalated', 'closed')),
    created_by      TEXT NOT NULL,           -- e.g. 'chat-agent/banking_compliance'
    reviewed_by     TEXT,                    -- compliance officer ID when reviewed
    reviewed_at     TIMESTAMPTZ,
    review_notes    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_compliance_flags_tenant
    ON compliance_flags (tenant_id);
CREATE INDEX IF NOT EXISTS idx_compliance_flags_open
    ON compliance_flags (tenant_id, status, risk_level)
    WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_compliance_flags_transaction
    ON compliance_flags (tenant_id, transaction_id);

ALTER TABLE compliance_flags ENABLE ROW LEVEL SECURITY;

CREATE POLICY compliance_flags_tenant_isolation ON compliance_flags
    USING (tenant_id = current_setting('app.current_tenant', true));

-- ── sar_drafts ────────────────────────────────────────────────────────────────
-- SAR narrative drafts generated by the banking_compliance agent.
-- Status transitions: pending_review → approved | rejected
-- CRITICAL: 'approved' does NOT automatically file with Finanstilsynet.
-- A compliance officer must explicitly trigger the filing process after approval.

CREATE TABLE IF NOT EXISTS sar_drafts (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            TEXT NOT NULL,
    narrative_md         TEXT NOT NULL,      -- Markdown SAR narrative
    source_flag_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,  -- array of compliance_flags.id
    reporting_obligation TEXT NOT NULL DEFAULT 'discretionary'
                             CHECK (reporting_obligation IN (
                                 'discretionary', 'mandatory_ctr', 'mandatory_str'
                             )),
    status               TEXT NOT NULL DEFAULT 'pending_review'
                             CHECK (status IN (
                                 'pending_review', 'approved', 'rejected', 'filed'
                             )),
    approved_by          TEXT,               -- compliance officer ID when approved
    approved_at          TIMESTAMPTZ,
    filed_at             TIMESTAMPTZ,        -- when actually transmitted to Finanstilsynet
    rejection_reason     TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sar_drafts_tenant
    ON sar_drafts (tenant_id);
CREATE INDEX IF NOT EXISTS idx_sar_drafts_pending
    ON sar_drafts (tenant_id, status)
    WHERE status = 'pending_review';

ALTER TABLE sar_drafts ENABLE ROW LEVEL SECURITY;

CREATE POLICY sar_drafts_tenant_isolation ON sar_drafts
    USING (tenant_id = current_setting('app.current_tenant', true));

-- ── Audit events additions ────────────────────────────────────────────────────
-- No schema change needed — banking compliance events (banking.compliance_flag_created,
-- banking.sar_draft_created) use the existing audit_events table from migration 012.

-- ── Demo seed data for dev-tenant ────────────────────────────────────────────
-- Inserts realistic anomaly patterns for local development and eval runners:
--   1. Structuring pattern — 9 transfers just below NOK 100,000
--   2. Velocity violation — 5 rapid international wires in 2 hours
--   3. PEP counterparty hit — high-value transfer to PEP-flagged entity
--   4. KYC-expired high-risk customer

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM transaction_records WHERE tenant_id = 'dev-tenant' LIMIT 1
    ) THEN

        -- Structuring pattern: 9 transactions just below CTR threshold
        INSERT INTO transaction_records
            (tenant_id, amount_nok, counterparty, timestamp, risk_score, kyc_status, transaction_type, metadata)
        VALUES
            ('dev-tenant', 98500.00, 'CUST-4471', now() - INTERVAL '6 hours', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 1}'::jsonb),
            ('dev-tenant', 97200.00, 'CUST-4471', now() - INTERVAL '5 hours 45 minutes', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 2}'::jsonb),
            ('dev-tenant', 99100.00, 'CUST-4471', now() - INTERVAL '5 hours 30 minutes', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 3}'::jsonb),
            ('dev-tenant', 98800.00, 'CUST-4471', now() - INTERVAL '5 hours 15 minutes', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 4}'::jsonb),
            ('dev-tenant', 97500.00, 'CUST-4471', now() - INTERVAL '5 hours', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 5}'::jsonb),
            ('dev-tenant', 98300.00, 'CUST-4471', now() - INTERVAL '4 hours 45 minutes', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 6}'::jsonb),
            ('dev-tenant', 99000.00, 'CUST-4471', now() - INTERVAL '4 hours 30 minutes', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 7}'::jsonb),
            ('dev-tenant', 97800.00, 'CUST-4471', now() - INTERVAL '4 hours 15 minutes', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 8}'::jsonb),
            ('dev-tenant', 98100.00, 'CUST-4471', now() - INTERVAL '4 hours', 72, 'verified', 'cash_deposit',
             '{"pattern_hint": "structuring", "sequence": 9}'::jsonb),

        -- Velocity violation: 5 international wires in 2 hours
            ('dev-tenant', 145000.00, 'CUST-8823', now() - INTERVAL '2 hours', 88, 'verified', 'international_wire',
             '{"pattern_hint": "velocity_violation", "destination_country": "AE"}'::jsonb),
            ('dev-tenant', 132000.00, 'CUST-8823', now() - INTERVAL '1 hour 45 minutes', 88, 'verified', 'international_wire',
             '{"pattern_hint": "velocity_violation", "destination_country": "AE"}'::jsonb),
            ('dev-tenant', 118500.00, 'CUST-8823', now() - INTERVAL '1 hour 30 minutes', 88, 'verified', 'international_wire',
             '{"pattern_hint": "velocity_violation", "destination_country": "AE"}'::jsonb),
            ('dev-tenant', 127000.00, 'CUST-8823', now() - INTERVAL '1 hour 15 minutes', 88, 'verified', 'international_wire',
             '{"pattern_hint": "velocity_violation", "destination_country": "AE"}'::jsonb),
            ('dev-tenant', 153000.00, 'CUST-8823', now() - INTERVAL '1 hour', 88, 'verified', 'international_wire',
             '{"pattern_hint": "velocity_violation", "destination_country": "AE"}'::jsonb),

        -- PEP counterparty hit
            ('dev-tenant', 2350000.00, 'CUST-1195', now() - INTERVAL '3 days', 91, 'verified', 'transfer',
             '{"pattern_hint": "pep_counterparty", "pep_category": "foreign_official"}'::jsonb),

        -- KYC-expired high-risk customer — moderate amounts but expired KYC
            ('dev-tenant', 450000.00, 'CUST-3367', now() - INTERVAL '1 day', 65, 'expired', 'payment',
             '{"pattern_hint": "kyc_expired"}'::jsonb),
            ('dev-tenant', 380000.00, 'CUST-3367', now() - INTERVAL '2 days', 65, 'expired', 'payment',
             '{"pattern_hint": "kyc_expired"}'::jsonb);

        -- Mark the PEP counterparty transaction as pep_flag=true
        UPDATE transaction_records
        SET pep_flag = true
        WHERE tenant_id = 'dev-tenant'
          AND counterparty = 'CUST-1195';

    END IF;
END $$;
