-- Migration 012: Posture / IaC governance plane — audit trail, findings, workflow runs,
-- change proposals, pipeline snapshots, and versioned infra context bundles.
--
-- Aligns with governed agent workflows: structured findings → proposals → validation → HITL.

-- ─────────────────────────────────────────────────────────────────────────────
-- Append-only audit log (application never UPDATEs/DELETEs; DB owner bypasses RLS)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       VARCHAR(128)    NOT NULL,
    actor           VARCHAR(256)    NOT NULL,
    action          VARCHAR(128)    NOT NULL,
    resource_type   VARCHAR(128)    NOT NULL,
    resource_id     VARCHAR(256),
    payload_hash    VARCHAR(64)     NOT NULL,
    metadata_json   JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_created
    ON audit_events (tenant_id, created_at DESC);

COMMENT ON TABLE audit_events IS
    'Append-only security / governance audit trail (review decisions, proposal gates, policy hits).';

-- ─────────────────────────────────────────────────────────────────────────────
-- IaC / policy findings (ingested from CI scanners or fixtures)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS infra_findings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           VARCHAR(128)    NOT NULL,
    severity            VARCHAR(32)     NOT NULL,
    rule_id             VARCHAR(256)    NOT NULL,
    title               TEXT            NOT NULL,
    file_path           TEXT,
    line_start          INTEGER,
    line_end            INTEGER,
    policy_pack_ref     VARCHAR(256),
    remediation_hint    TEXT,
    detail_json         JSONB           NOT NULL DEFAULT '{}',
    source_scan_id      VARCHAR(128),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_infra_findings_tenant_severity
    ON infra_findings (tenant_id, severity);
CREATE INDEX IF NOT EXISTS idx_infra_findings_rule
    ON infra_findings (tenant_id, rule_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Agent workflow runs — explicit state machine for infra (and future) sessions
-- States: gathering_context | proposing | validating | pending_approval |
--          approved | rejected | failed_validation
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_workflow_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           VARCHAR(128)    NOT NULL,
    session_type        VARCHAR(64)     NOT NULL,
    workflow_state      VARCHAR(64)     NOT NULL DEFAULT 'gathering_context',
    created_by          VARCHAR(256)    NOT NULL,
    tool_rounds_used    INTEGER         NOT NULL DEFAULT 0,
    max_tool_rounds     INTEGER         NOT NULL DEFAULT 16,
    metadata_json       JSONB           NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_workflow_runs_tenant_state
    ON agent_workflow_runs (tenant_id, workflow_state, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Machine-generated change proposals (diff + rationale + validation / HITL)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS change_proposals (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               VARCHAR(128)    NOT NULL,
    run_id                  UUID            NOT NULL REFERENCES agent_workflow_runs(id) ON DELETE CASCADE,
    unified_diff            TEXT            NOT NULL,
    rationale_md            TEXT            NOT NULL DEFAULT '',
    resource_addresses      JSONB           NOT NULL DEFAULT '[]',
    risk_level              VARCHAR(32)     NOT NULL DEFAULT 'medium',
    validation_errors       JSONB,
    decided_by              VARCHAR(256),
    decided_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_change_proposals_run_id UNIQUE (run_id)
);

CREATE INDEX IF NOT EXISTS idx_change_proposals_tenant_created
    ON change_proposals (tenant_id, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Mock / ingested CI pipeline context for agent tools
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       VARCHAR(128)    NOT NULL,
    workflow        VARCHAR(256)    NOT NULL,
    conclusion      VARCHAR(32)     NOT NULL,
    sha             VARCHAR(64),
    triggered_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),
    metadata_json   JSONB           NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_tenant_triggered
    ON pipeline_runs (tenant_id, triggered_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Versioned infra context bundles per workflow run (findings + plan + inventory + pipeline)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS infra_context_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       VARCHAR(128)    NOT NULL,
    run_id          UUID            REFERENCES agent_workflow_runs(id) ON DELETE SET NULL,
    bundle_json     JSONB           NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_infra_context_snapshots_tenant_run
    ON infra_context_snapshots (tenant_id, run_id, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Row-Level Security (tenant isolation via app.tenant_id session GUC)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE infra_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE infra_findings FORCE ROW LEVEL SECURITY;
ALTER TABLE agent_workflow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_workflow_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE change_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_proposals FORCE ROW LEVEL SECURITY;
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE infra_context_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE infra_context_snapshots FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'audit_events'
          AND policyname = 'tenant_isolation_select'
    ) THEN
        CREATE POLICY tenant_isolation_select ON audit_events
            FOR SELECT USING (tenant_id = current_tenant_id());
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'audit_events'
          AND policyname = 'tenant_isolation_insert'
    ) THEN
        CREATE POLICY tenant_isolation_insert ON audit_events
            FOR INSERT WITH CHECK (tenant_id = current_tenant_id());
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'infra_findings'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON infra_findings
            USING (tenant_id = current_tenant_id())
            WITH CHECK (tenant_id = current_tenant_id());
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'agent_workflow_runs'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON agent_workflow_runs
            USING (tenant_id = current_tenant_id())
            WITH CHECK (tenant_id = current_tenant_id());
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'change_proposals'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON change_proposals
            USING (tenant_id = current_tenant_id())
            WITH CHECK (tenant_id = current_tenant_id());
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'pipeline_runs'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON pipeline_runs
            USING (tenant_id = current_tenant_id())
            WITH CHECK (tenant_id = current_tenant_id());
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'infra_context_snapshots'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON infra_context_snapshots
            USING (tenant_id = current_tenant_id())
            WITH CHECK (tenant_id = current_tenant_id());
    END IF;
END;
$$;
