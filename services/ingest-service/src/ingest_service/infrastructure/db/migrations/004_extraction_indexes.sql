-- Migration: 004 — performance indexes for new extraction fields
-- Enables fast CFO queries: by location, cost center, legal risk, report type,
-- posting period, and GL account without full table scans.

-- GIN index on the full extraction JSONB column for arbitrary key queries.
-- Already safe to run if 001 applied; CREATE INDEX IF NOT EXISTS is idempotent.
CREATE INDEX IF NOT EXISTS idx_documents_extraction_gin
    ON documents USING GIN (extraction);

-- Functional indexes on frequently queried scalar extraction fields.
-- Each one covers a specific CFO query pattern in FinancialDbReader.

CREATE INDEX IF NOT EXISTS idx_documents_store_location
    ON documents ((extraction->>'store_location'))
    WHERE extraction->>'store_location' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_department
    ON documents ((extraction->>'department'))
    WHERE extraction->>'department' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_cost_center
    ON documents ((extraction->>'cost_center'))
    WHERE extraction->>'cost_center' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_gl_account
    ON documents ((extraction->>'gl_account'))
    WHERE extraction->>'gl_account' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_posting_period
    ON documents ((extraction->>'posting_period'))
    WHERE extraction->>'posting_period' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_legal_risk_flag
    ON documents ((extraction->>'legal_risk_flag'))
    WHERE extraction->>'legal_risk_flag' = 'true';

CREATE INDEX IF NOT EXISTS idx_documents_report_type
    ON documents ((extraction->>'report_type'))
    WHERE extraction->>'report_type' IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_report_period
    ON documents ((extraction->>'report_period'))
    WHERE extraction->>'report_period' IS NOT NULL;

-- Composite index for spend-by-period queries (tenant + invoice date + category).
CREATE INDEX IF NOT EXISTS idx_documents_tenant_invoice_date
    ON documents (tenant_id, (extraction->>'invoice_date'), (extraction->>'document_category'))
    WHERE extraction->>'invoice_date' IS NOT NULL;

-- Composite index for cost-center rollup queries.
CREATE INDEX IF NOT EXISTS idx_documents_tenant_cost_center_category
    ON documents (tenant_id, (extraction->>'cost_center'), (extraction->>'document_category'))
    WHERE extraction->>'cost_center' IS NOT NULL;

-- Composite index for location-based aggregation queries.
CREATE INDEX IF NOT EXISTS idx_documents_tenant_location_category
    ON documents (tenant_id, (extraction->>'store_location'), (extraction->>'document_category'))
    WHERE extraction->>'store_location' IS NOT NULL;
