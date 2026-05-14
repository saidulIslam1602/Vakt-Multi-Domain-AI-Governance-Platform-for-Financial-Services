-- Migration 010: Row-Level Security policies for all tenant-scoped tables
--
-- Purpose: Enforce tenant isolation at the database level so that even if
-- application-layer tenant filtering is bypassed, PostgreSQL itself refuses
-- to return or mutate rows belonging to another tenant.
--
-- Mechanism:
--   Each query MUST call  SET LOCAL app.tenant_id = '<tenant>';  inside the
--   same transaction (or connection).  The shared-lib DB helper already does
--   this via the allergo_shared.db.session_scope() context manager.
--
-- Tables covered:
--   documents, alert_rules, alert_events,
--   scheduled_alert_log, email_ingest_log
--   (012+) audit_events, infra_findings, agent_workflow_runs, change_proposals,
--          pipeline_runs, infra_context_snapshots — policies defined in 012
--
-- Note: The superuser / migration role bypasses RLS automatically (it holds
-- the BYPASSRLS privilege) so migrations themselves are never blocked.

-- ──────────────────────────────────────────────────────────────────────────
-- Helper function: current_tenant_id()
-- Returns the session-local GUC that application code must set before any
-- DML.  Falls back to '' so that rows with tenant_id = '' are never matched
-- (effectively blocking access if the app forgets to set the GUC).
-- ──────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS TEXT
    LANGUAGE sql STABLE PARALLEL SAFE
AS $$
    SELECT COALESCE(current_setting('app.tenant_id', true), '')
$$;

-- ──────────────────────────────────────────────────────────────────────────
-- documents
-- RLS was ENABLEd in migration 001; we only need to ADD the policy.
-- ──────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'documents'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $policy$
            CREATE POLICY tenant_isolation ON documents
                USING (tenant_id = current_tenant_id())
                WITH CHECK (tenant_id = current_tenant_id())
        $policy$;
    END IF;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────
-- alert_rules
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_rules FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'alert_rules'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $policy$
            CREATE POLICY tenant_isolation ON alert_rules
                USING (tenant_id = current_tenant_id())
                WITH CHECK (tenant_id = current_tenant_id())
        $policy$;
    END IF;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────
-- alert_events
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE alert_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_events FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'alert_events'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $policy$
            CREATE POLICY tenant_isolation ON alert_events
                USING (tenant_id = current_tenant_id())
                WITH CHECK (tenant_id = current_tenant_id())
        $policy$;
    END IF;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────
-- scheduled_alert_log
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE scheduled_alert_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_alert_log FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'scheduled_alert_log'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $policy$
            CREATE POLICY tenant_isolation ON scheduled_alert_log
                USING (tenant_id = current_tenant_id())
                WITH CHECK (tenant_id = current_tenant_id())
        $policy$;
    END IF;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────
-- email_ingest_log
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE email_ingest_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_ingest_log FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'email_ingest_log'
          AND policyname = 'tenant_isolation'
    ) THEN
        EXECUTE $policy$
            CREATE POLICY tenant_isolation ON email_ingest_log
                USING (tenant_id = current_tenant_id())
                WITH CHECK (tenant_id = current_tenant_id())
        $policy$;
    END IF;
END;
$$;
