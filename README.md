<div align="center">

# Allergo Nordic — Multi-Domain Agentic Governance Platform

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Azure](https://img.shields.io/badge/Azure-Container_Apps-0078D4?logo=microsoft-azure&logoColor=white)](https://azure.microsoft.com)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC?logo=terraform&logoColor=white)](https://terraform.io)

> **AI agents that detect issues, generate reviewable change proposals, and require human approval before anything is applied — across both financial documents and cloud infrastructure.**

</div>

---

## Table of Contents

- [What This Demonstrates](#what-this-demonstrates)
- [Architecture Overview](#architecture-overview)
- [AI Agent Layer](#ai-agent-layer)
- [Infrastructure Governance Agent](#infrastructure-governance-agent)
- [Drift Detection](#drift-detection)
- [Human-in-the-Loop Review](#human-in-the-loop-review)
- [Agent Guardrails and Auditability](#agent-guardrails-and-auditability)
- [Infrastructure Context System](#infrastructure-context-system)
- [Integrations](#integrations)
- [Fullstack Product](#fullstack-product)
- [Enterprise Requirements](#enterprise-requirements)
- [Infrastructure as Code (Terraform)](#infrastructure-as-code-terraform)
- [CI/CD Pipelines](#cicd-pipelines)
- [RAG Pipeline and Evals](#rag-pipeline-and-evals)
- [Services Reference](#services-reference)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [ADRs and Design Decisions](#adrs-and-design-decisions)

---

## What This Demonstrates

This project was built to address the exact problem space that Cloudgeni targets: **AI agents that help infrastructure and DevOps teams move faster, while keeping humans in control of what actually gets applied.**

The platform has two domains sharing one governance control plane:

| Domain | What the agent does |
|--------|-------------------|
| **Finance (CFO)** | Ingests invoices/contracts via LLM extraction → answers questions via RAG → flags anomalies for human review |
| **Infrastructure posture** | Reads Checkov scan results → reads live Terraform plan → detects drift → generates a unified diff + rationale as a reviewable change proposal → requires human approval before any change is applied |

Both domains reuse the same primitives: **workflow states** (`gathering_context → proposing → approved/rejected`), **append-only audit trail**, **human approval gate**, and **policy-enforced tool access**. The LLM is a component inside those workflows — not the product.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Next.js 14 Frontend  (TypeScript)                   │
│   Dashboard · Upload · Review Queue · Posture Findings · Proposal Diff  │
└──────────────┬──────────────────────────────────────────┬───────────────┘
               │ REST / Server Actions                     │ REST / SSE
  ┌────────────▼──────────┐                   ┌────────────▼───────────────┐
  │   ingest-service :8001│                   │   chat-service      :8004  │
  │  Upload · Email · ZIP │                   │   Agentic RAG · Tool-call  │
  └────────────┬──────────┘                   │   Finance + Infra sessions │
               │ Azure Service Bus             └────────────────────────────┘
  ┌────────────▼──────────┐
  │  processing-service   │  (queue worker — no inbound HTTP)
  │  Parse → LLM extract  │
  │  Chunk → Index → Alert│
  └──────┬────────┬───────┘
         │        │
  ┌──────▼───┐  ┌─▼────────────────────────────────┐
  │ Azure AI │  │  document-service          :8002  │
  │ Search   │  │  CRUD · Review · Webhooks         │
  │ (prod)   │  │  Posture API · Audit trail        │
  │ Elastic  │  │  Approval gate · PR export        │
  │ (local)  │  └──────────────────────────────────┘
  └──────────┘

Shared: PostgreSQL 16 + pgvector  ·  Azure Blob Storage  ·  Azure Key Vault
IaC:    Terraform (infra/)  ·  GitHub Actions (OIDC → ACR → Container Apps)
```

**Message contract** — `ingest-service` publishes `document_uploaded` to the `document-events` topic on Azure Service Bus (RabbitMQ locally). `processing-service` consumes it and runs the full pipeline. No synchronous HTTP between services — all coordination is event-driven.

---

## AI Agent Layer

The `chat-service` implements a **ReAct (Reason + Act) agent** using OpenAI tool-calling. The LLM iterates up to 6 tool rounds before composing a final answer grounded entirely in retrieved data.

### How it works

```
User question
     │
     ▼
System prompt (injected today's date, session type, tool schema)
     │
     ▼  ┌─────────────────────────────────────────┐
LLM decides│ Which tool? What args?                  │
     │     └─────────────────────────────────────────┘
     ▼
_execute_tool() → dispatches to handler
     │
     ▼
Tool result appended as tool-result message
     │
     └──► LLM iterates (up to MAX_TOOL_ROUNDS=6)
               │
               ▼
         Final answer  →  citations + tools_used + intent + suggestions
```

### Session types and tool allowlists

Two distinct agent profiles are enforced at runtime via `_SESSION_ALLOWED_TOOLS`:

| Session type | Allowed tools | Blocked tools |
|---|---|---|
| `finance_chat` | `search_document_content`, `query_financial_database` | All infra tools |
| `infra_remediation` | `list_infra_findings`, `get_infra_finding`, `get_terraform_plan_summary`, `detect_infra_drift`, `propose_remediation`, `get_infra_context_bundle` | All finance tools |

Crossing the boundary emits an audit event and returns a structured policy error — the LLM sees it and self-corrects. This is the **tool policy enforcement** pattern for safe AI in production.

### Finance agent tools

| Tool | What it does |
|---|---|
| `search_document_content` | Hybrid vector + keyword search (Azure AI Search) with tenant-scoped `odata_filter` |
| `query_financial_database` | Structured asyncpg queries: overdue invoices, expiring contracts, spend by period, ledger by account, legal obligations, dashboard snapshot — 13 query types |

### Streaming response

The agent streams token-by-token over SSE. Metadata (citations, tools used, intent) is emitted first so the UI can render source attribution while the answer is still generating:

```
data: {"type":"metadata","citations":[...],"tools_used":["search_document_content"],"intent":"content_search"}
data: {"type":"token","delta":"The "}
data: {"type":"token","delta":"NorgesGruppen "}
...
data: {"type":"suggestions","suggestions":["What are the renewal terms?","Show me related invoices"]}
data: [DONE]
```

---

## Infrastructure Governance Agent

This is the core of the infra posture domain — directly analogous to what Cloudgeni builds.

### The loop

```
1. Checkov scans infra/ on every push/PR (ci-infra-scan.yml)
2. scripts/import_checkov_findings.py writes rows into infra_findings (DB)
3. Chat agent (session_type=infra_remediation):
     list_infra_findings  → show open policy violations
     get_infra_finding    → get detail + remediation_hint
     detect_infra_drift   → compare current plan or two snapshots
     propose_remediation  → generate unified diff + rationale → write to DB
4. Human reviews the proposal in the UI (diff viewer, rationale, risk level)
5. POST /posture/proposals/{id}/approve  → state = approved → audit event
6. POST /posture/proposals/{id}/export   → PR title/body + git patch
7. Engineer applies the patch, opens a PR — Terraform apply remains manual
```

**The agent never runs `terraform apply`.** It only creates a proposal record. This is the human-in-the-loop pattern for safe AI in real infrastructure environments.

### Infra agent API call

```http
POST /api/v1/chat/
{
  "question": "We have a Key Vault purge protection finding — fix it",
  "session_type": "infra_remediation"
}

→ 200 {
  "answer": "I found finding CKV_AZURE_88 (purge_protection_enabled = false). Here is the fix:\n\n```diff\n--- a/infra/keyvault.tf\n+++ b/infra/keyvault.tf\n@@ -12,1 +12,1 @@\n-  purge_protection_enabled = false\n+  purge_protection_enabled = true\n```\n\nRationale: ...\n\nProposal created (ID: 22222222-...). **Human approval required.**",
  "tools_used": ["list_infra_findings", "get_infra_finding", "propose_remediation"],
  "session_type": "infra_remediation",
  "tool_rounds_used": 3
}
```

---

## Drift Detection

`detect_infra_drift` — a dedicated agent tool that answers "what has changed / drifted?"

### Mode 1: Plan analysis (no args)

Reads the current Terraform plan and returns every non-`no-op` resource change with severity classification and security regression detection:

```json
{
  "source": "local_file",
  "drift_count": 3,
  "drifted_resources": [
    {
      "address": "azurerm_key_vault.main",
      "type": "azurerm_key_vault",
      "action": "update",
      "changed_attributes": ["purge_protection_enabled", "soft_delete_retention_days"],
      "severity": "HIGH"
    },
    {
      "address": "azurerm_storage_account.data",
      "type": "azurerm_storage_account",
      "action": "update",
      "changed_attributes": ["allow_blob_public_access"],
      "severity": "HIGH"
    }
  ],
  "security_risks": [
    {
      "resource_type": "azurerm_key_vault",
      "regressions": [],
      "fixes": ["purge_protection_enabled"],
      "severity": "HIGH"
    }
  ],
  "requires_review": true,
  "recommendation": "3 resource(s) have pending changes — review before apply."
}
```

### Mode 2: Snapshot comparison

Pass `snapshot_id_baseline` + `snapshot_id_current` to diff two stored `infra_context_snapshots`:

```json
{
  "source": "snapshot_comparison",
  "drift_count": 1,
  "removed_count": 1,
  "drifted_resources": [
    {
      "address": "azurerm_kubernetes_cluster.main",
      "baseline_action": "no-op",
      "current_action": "update",
      "changed_attributes": ["kubernetes_version"],
      "severity": "MEDIUM"
    }
  ],
  "removed_resources": [
    {"address": "azurerm_network_security_rule.allow_rdp", "status": "removed_since_baseline"}
  ],
  "requires_review": true
}
```

### Severity classification

The `_classify_drift_severity` function classifies every drifted resource:

| Severity | Triggered when |
|---|---|
| `HIGH` | Security-sensitive resource type (`azurerm_key_vault`, `aws_s3_bucket`, AKS, RDS, etc.) with known security attribute change |
| `MEDIUM` | Security-sensitive type without known attribute change, or network/NSG resources |
| `LOW` | All other resource types |

Security regression detection (`_assess_security_risk`) flags when a known security attribute moves from a restrictive to permissive value (e.g. `purge_protection_enabled: true → false`, `allow_blob_public_access: false → true`).

### Live plan resolution

`get_terraform_plan_summary` resolves from three sources in priority order:

| Priority | Source | How to configure |
|---|---|---|
| 1 | **Local tfplan.json** | `TERRAFORM_PLAN_PATH=/path/to/tfplan.json` — produced by `terraform show -json tfplan.binary > tfplan.json` |
| 2 | **Terraform Cloud API** | `TFC_TOKEN=<token>` + `TFC_WORKSPACE_ID=<id>` — fetches latest run's plan JSON |
| 3 | **Fixture fallback** | Always available — clearly labelled `"source": "fixture_fallback"` so the LLM knows it is not live state |

---

## Human-in-the-Loop Review

Every agent-generated change proposal goes through a structured review workflow before anything can be applied.

### Proposal lifecycle

```
gathering_context
       │
       ▼
   proposing  ←── agent creates change_proposal (diff + rationale + risk_level)
       │
       ▼
  validation  ←── POST /posture/proposals/{id}/validate (schema gate)
       │
       ├──► approved  ←── POST /posture/proposals/{id}/approve
       │                    → audit event written
       │                    → engineer applies patch manually
       │
       └──► rejected  ←── POST /posture/proposals/{id}/reject
                           → audit event written
```

### What a proposal contains

| Field | Description |
|---|---|
| `unified_diff` | Valid unified diff (--- / +++ format) for the Terraform change |
| `rationale_md` | Markdown explanation: finding → root cause → fix → risk |
| `resource_addresses` | Terraform resource addresses affected |
| `risk_level` | `low / medium / high / critical` |
| `workflow_state` | `proposing → approved / rejected` |

### PR export

`POST /posture/proposals/{id}/export` returns a ready-to-use PR payload:

```json
{
  "pr_title": "fix: enable purge protection on azurerm_key_vault.main [CKV_AZURE_88]",
  "pr_body": "## Finding\n...\n## Change\n...\n## Risk\n...",
  "patch": "--- a/infra/keyvault.tf\n+++ ...",
  "git_apply_command": "git apply --check allergo-fix-CKV_AZURE_88.patch"
}
```

This mirrors the GitHub / Azure DevOps PR-based workflow that Cloudgeni uses: the AI proposes, the human reviews, the engineer merges.

---

## Agent Guardrails and Auditability

### Tool policy enforcement

Every tool call passes through a **policy gate** in `_execute_tool()`. If the LLM attempts to call a tool outside its session's allowlist:

1. The call is blocked and returns a structured error
2. An audit event is written via `chat.tool_policy_violation` 
3. The LLM receives the error and self-corrects in the next round

```python
# In _execute_tool():
if allowed_tools is not None and name not in allowed_tools:
    await self._emit_audit(action="chat.tool_policy_violation", ...)
    return {"error": f"Tool '{name}' is not allowed in session_type='{session_type}'"}
```

### Append-only audit trail

Every significant action — document approval, proposal approval/rejection, tool policy violation, agent run — is written to the `audit_events` table via `append_audit_event()`:

```python
await pool.execute(
    """INSERT INTO audit_events (
           tenant_id, actor, action, resource_type, resource_id,
           payload_hash, metadata_json
       ) VALUES ($1, $2, $3, $4, $5, $6, $7)""",
    tenant_id, actor, action, resource_type, resource_id,
    _payload_hash(metadata), metadata,
)
```

The table has PostgreSQL Row-Level Security enabled (`ENABLE ROW LEVEL SECURITY`) — tenants cannot read each other's audit records even with a compromised token.

### Proposal validation gate

Before a proposal can be approved, it must pass `POST /posture/proposals/{id}/validate`:
- Unified diff format is valid
- Resource addresses are non-empty
- Rationale is non-empty markdown
- Risk level is a valid enum value

This prevents the LLM from creating incomplete proposals that an engineer might accidentally approve.

### MAX_TOOL_ROUNDS

The agent loop is hard-capped at `MAX_TOOL_ROUNDS = 6`. If the LLM has not produced a final answer by then, the loop terminates and returns what it has. This prevents runaway tool calls in production.

---

## Infrastructure Context System

The `infra_context_snapshots` table stores a frozen point-in-time bundle of infrastructure state:

```json
{
  "snapshot_id": "uuid",
  "tenant_id": "allergo-prod",
  "created_at": "2026-05-14T18:00:00Z",
  "terraform_plan": {
    "source": "local_file",
    "resources": [...],
    "action_summary": {"update": 3, "no-op": 12},
    "security_risks": [...]
  },
  "findings": [...],
  "pipeline_run": { "workflow_id": "...", "checkov_version": "3.x", "scan_time": "..." },
  "policies": ["CKV_AZURE_88", "CKV_AZURE_35", "CKV_AZURE_131"],
  "metadata": { "environment": "prod", "triggered_by": "ci/main" }
}
```

The agent can retrieve any snapshot with `get_infra_context_bundle(snapshot_id)` to ground answers in a specific point-in-time state rather than live queries — useful for incident post-mortems and comparing before/after a change.

Context bundles are created automatically: `POST /posture/runs/{id}/context-snapshot` is called by the CI pipeline after each Checkov import, capturing plan + findings + pipeline metadata together.

---

## Integrations

### GitHub Actions → Checkov → DB

```yaml
# .github/workflows/ci-infra-scan.yml
- name: Run Checkov
  run: checkov -d infra/ -o json > checkov-results.json

- name: Import findings to DB
  run: |
    python scripts/import_checkov_findings.py \
      --input checkov-results.json \
      --tenant ${{ vars.ALLERGO_TENANT_ID }} \
      --source-scan-id ${{ github.sha }}
```

The importer generates **deterministic UUIDs** from `(tenant_id, rule_id, file_path, line_start)` → `ON CONFLICT DO NOTHING`. Re-running the same scan never creates duplicate findings.

### Terraform Cloud API

When `TFC_TOKEN` + `TFC_WORKSPACE_ID` are set, `get_terraform_plan_summary` calls:

```
GET https://app.terraform.io/api/v2/workspaces/{workspace_id}/runs?page[size]=1
GET https://app.terraform.io/api/v2/runs/{run_id}/plan/json-output
```

Returns the latest run's plan JSON including `run_id`, `run_status`, and full resource changes — live cloud state, not a fixture.

### Azure DevOps (same pattern)

The PR export endpoint generates a patch and git-apply command compatible with both GitHub and Azure DevOps PR workflows. The review + approval flow in the UI mirrors how platform teams use PR-based IaC in enterprise environments.

### Webhook engine (outbound)

For the finance domain, document lifecycle events are dispatched via HMAC-SHA256 signed webhooks — the same signing scheme GitHub uses (`X-Allergo-Signature: sha256=<hmac>`). Compatible with any ERP or downstream system that verifies webhook authenticity.

### Azure managed identity (no static keys)

In production, all Azure SDK clients use `DefaultAzureCredential`:

```python
# No key in environment — credential resolved from managed identity
credential = DefaultAzureCredential()
blob_client = BlobServiceClient(account_url, credential=credential)
```

RBAC roles assigned via Terraform `iam.tf`:
- `Storage Blob Data Contributor` → ingest + processing services
- `Azure Service Bus Data Owner` → ingest + processing
- `Search Index Data Contributor` → processing + search
- `Cognitive Services OpenAI User` → processing + chat
- `Key Vault Secrets User` → all services

---

## Fullstack Product

### Frontend (Next.js 14 + TypeScript)

| Page | Route | What it shows |
|---|---|---|
| Dashboard | `/` | Document stats, recent activity, contract expiry alerts |
| Upload | `/upload` | Drag-and-drop file upload with real-time status via SSE |
| Review queue | `/review` | CFO approval queue — one-click approve / reject with reason |
| Search | `/search` | Hybrid semantic search with document preview |
| Chat | `/chat` | Streaming RAG chat with citation cards |
| Posture findings | `/posture/findings` | IaC policy violations from Checkov; severity filter, detail drawer |
| Proposals | `/posture/proposals` | Agent workflow runs; state filter; "New infra remediation" button |
| Proposal detail | `/posture/proposals/[run_id]` | Diff viewer, markdown rationale, risk level, Approve / Reject modal, PR export |

### Data flow for the infra review UI

```
User visits /posture/proposals/{run_id}
     │
     ▼
GET /posture/runs/{run_id}        → workflow state, metadata
GET /posture/runs/{run_id}/proposals → unified_diff, rationale_md, risk_level
     │
     ▼
Diff viewer renders unified_diff with syntax highlighting
Rationale panel renders rationale_md as markdown
Risk badge shows risk_level (colour-coded)
     │
User clicks "Approve"
     │
     ▼
POST /posture/proposals/{id}/approve  → audit event → state = approved
UI updates optimistically, shows audit timestamp
```

### BFF pattern (Next.js API routes)

The frontend communicates with upstream Python services via `_proxy.ts` — a Next.js API route layer that handles tenant headers, auth forwarding, and path normalisation. The browser never calls Python services directly.

---

## Enterprise Requirements

### Multi-tenancy

Every table has a `tenant_id` column. PostgreSQL **Row-Level Security** is enabled on 12 tables including `audit_events`, `infra_findings`, `agent_workflow_runs`, `change_proposals`, and `infra_context_snapshots`:

```sql
-- From migration 012_posture_governance.sql
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
-- RLS policy uses app.tenant_id session GUC set at connection time
CREATE POLICY tenant_isolation ON audit_events
  USING (tenant_id = current_setting('app.tenant_id'));
```

Services set `SET LOCAL app.tenant_id = $1` before every query. A compromised service cannot read another tenant's data even with direct DB access.

### Authentication (JWKS / OIDC)

All services use a shared `make_auth_dependency()` factory that validates JWTs against a live JWKS endpoint (RS256, cached 1 hour):

```python
signing_key = jwks_client.get_signing_key_from_jwt(token)
payload = jwt.decode(token, signing_key.key, algorithms=["RS256"],
                     audience=audience, issuer=issuer)
tenant_id = payload.get("tenant_id") or payload.get("tid") or "default"
```

`AUTH_ENABLED=false` in local dev substitutes a no-op dependency (dev user, dev-tenant).

### Audit logs

`audit_events` is an **append-only** table — no UPDATE or DELETE on it via the application layer. Rows are written by:
- Document approval / rejection
- Infra proposal approval / rejection
- Agent tool policy violations
- Webhook delivery failures

Each row includes `payload_hash = sha256(metadata_json)` for tamper detection.

### Permissions (tool policy)

Infra tools cannot be called in finance sessions and vice versa. This is enforced at the Python level (not just prompt engineering) — the `allowed_tools` frozenset is checked before any tool handler runs.

### Structured logging + observability

All services use `structlog` with JSON output, OpenTelemetry context propagation, and a correlation ID middleware. Logs are structured (not printf-style) — compatible with Azure Monitor, Datadog, and any log aggregation platform.

---

## Infrastructure as Code (Terraform)

All Azure resources are defined in `infra/` using the `hashicorp/azurerm` provider. Target region: **Norway East**; Azure OpenAI in **Sweden Central** (GPT-4o availability).

### What is provisioned

| File | Azure Resource | Key settings |
|---|---|---|
| `resource_group.tf` | Resource Group | Tagged by environment |
| `container_apps.tf` | Azure Container Apps + Environment | One app per service, scale-to-zero |
| `openai.tf` | Azure OpenAI | GPT-4o (80 TPM prod / 20 dev) + text-embedding-3-large (120 TPM prod / 30 dev) |
| `ai_search.tf` | Azure AI Search | Standard tier, semantic search enabled |
| `postgresql.tf` | PostgreSQL Flexible Server | v16, pgvector + UUID-OSSP + PG_TRGM extensions, geo-redundant backup in prod |
| `service_bus.tf` | Azure Service Bus | Standard namespace, `document-events` topic |
| `storage.tf` | Azure Blob Storage | `raw-documents` container, private access |
| `keyvault.tf` | Azure Key Vault | Soft-delete 90 days, purge protection enabled |
| `iam.tf` | Managed Identity + RBAC | Principle of least privilege — separate role per service |

### Deploy

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Fill in: postgres_admin_password, nextauth_secret, environment

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### Local plan → agent

To give the infra agent a live plan instead of the fixture:

```bash
cd infra
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > /tmp/tfplan.json
TERRAFORM_PLAN_PATH=/tmp/tfplan.json \
  curl -X POST http://localhost:8004/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the current plan show?", "session_type": "infra_remediation"}'
```

The agent reads your actual plan and gives a real drift/change summary.

---

## CI/CD Pipelines

All workflows use **OIDC federated credentials** — no long-lived secrets in GitHub. Azure authenticates via `azure/login@v2` with `client-id`, `tenant-id`, `subscription-id`.

| Workflow | Trigger | Jobs |
|---|---|---|
| `ci-python-service.yml` | Push/PR (reusable) | ruff lint → mypy → pytest + coverage → Docker build/push to ACR |
| `ci-frontend.yml` | Push/PR on `frontend/**` | ESLint → tsc → Next.js build → ACR push → Container App deploy |
| `terraform.yml` | Push/PR on `infra/**` | `terraform init` → `fmt -check` → `validate` → `plan` (PR) → `apply` (main merge) |
| `ci-infra-scan.yml` | Push/PR on `infra/**` | Checkov scan → artifact upload → `import_checkov_findings.py` (main only) |
| `ci-evals.yml` | Push/PR on `evals/**` or `chat-service/**` | Infra agent evals (mock, 9 cases) + RAG quality evals (offline + live RAGAS) |
| Per-service CI | Push/PR | Calls reusable `ci-python-service.yml` for each of 5 Python services |

### IaC pipeline detail

```yaml
# terraform.yml — plan on PR, apply on merge to main
- name: Terraform Plan
  run: terraform plan -var-file="environments/staging/terraform.tfvars" -out=tfplan

- name: Terraform Apply
  if: github.ref == 'refs/heads/main'
  run: terraform apply tfplan
```

Checkov and tfsec run as part of `ci-infra-scan.yml` on every infrastructure change. Findings are imported to the DB and become queryable by the infra agent immediately after CI completes.

---

## RAG Pipeline and Evals

### Hybrid RAG (Azure AI Search)

The `chat-service` uses **hybrid vector + keyword** search — not just embedding similarity:

```python
vector_query = VectorizedQuery(
    vector=embedding,          # text-embedding-3-large
    k_nearest_neighbors=top_k,
    fields="embedding"
)
results = await search_client.search(
    search_text=query,         # BM25 keyword
    vector_queries=[vector_query],
    filter=f"tenant_id eq '{tenant_id}'",  # tenant isolation
    select=["id", "document_id", "text", "filename", "page_number"],
)
```

In local dev, the same interface switches to Elasticsearch kNN search (detected by endpoint heuristic). Production uses Azure AI Search Standard with semantic ranking.

### Evaluation framework

**Infra agent evals** (mock LLM — no cloud keys):

```bash
PYTHONPATH=services/chat-service/src:services/shared-lib/src \
  python evals/infra/eval_runner.py --cases evals/infra/cases.jsonl --mock --verbose
# → 9/9 PASS
```

Cases cover: multi-step remediation (list → detail → propose), drift detection (plan mode + snapshot comparison), Terraform plan summary, tool policy enforcement, and cross-session blocking.

**RAG quality evals** (RAGAS):

```bash
# Offline — lexical proxy metrics, no API key, CI default
python evals/rag/rag_eval.py --dataset evals/rag/eval_dataset.jsonl --offline
# Metrics: faithfulness 0.63 | answer_relevancy 0.67 | context_precision 0.95 | context_recall 0.50

# Online — real RAGAS with LLM judge
OPENAI_API_KEY=<key> \
  python evals/rag/rag_eval.py --dataset evals/rag/eval_dataset.jsonl --output evals/rag/results.json
```

Dataset: 10 Norwegian B2B finance Q&A pairs (invoices, contracts, VAT, liability caps, dispute resolution). Metrics: **faithfulness**, **answer_relevancy**, **context_precision**, **context_recall** via `ragas>=0.1`.

CI runs both eval suites on every PR that touches `evals/` or `services/chat-service/`. Live RAGAS runs on `main` merges if `OPENAI_API_KEY` secret is set.

---

## Services Reference

### ingest-service (port 8001)

- `POST /api/v1/documents/` — single file upload (PDF, DOCX, XLSX, TXT, HTML, image)
- `POST /api/v1/documents/bulk` — ZIP archive (all files queued in parallel)
- `GET  /api/v1/documents/` — tenant document list (paginated)
- `GET  /api/v1/documents/{id}` — single document
- `GET  /api/v1/documents/email-status` — IMAP poller health
- Background: IMAP email poller (asyncio task, 5-min interval)

### processing-service (queue worker, no HTTP)

- Subscribes to `document-events` queue
- Pipeline: `BlobParser` → `LLMExtractor` (GPT-4o, tenacity retry) → `TextChunker` (tiktoken cl100k, 512 tokens / 64 overlap) → `SearchIndexer` / `ESIndexer` → `DbUpdater` → `EmailNotifier`
- `ContractRenewalScanner` — APScheduler, 08:00 UTC daily — fires alert events + SMTP

### document-service (port 8002)

- Full document CRUD + review queue
- `GET /api/v1/review/queue` → `POST /api/v1/review/{id}/decision`
- Webhooks: HMAC-SHA256 signed outbound (`X-Allergo-Signature: sha256=<hmac>`)
- CSV export: streaming `StreamingResponse`
- **Governance API**: `/posture/findings`, `/posture/runs`, `/posture/proposals`, `/posture/snapshots`, `/audit`

### search-service (port 8003)

- `POST /api/v1/search/` — hybrid semantic + full-text search
- Dual backend: Azure AI Search (prod) / Elasticsearch (local)
- Tenant-scoped via `odata_filter`

### chat-service (port 8004)

- `POST /api/v1/chat/` — agentic RAG (standard or `stream: true` → SSE)
- Two session types: `finance_chat` and `infra_remediation`
- Tool policy enforcement + audit events on violations
- `GET/POST /api/v1/chat/saved` — bookmarked queries

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Backend framework** | FastAPI (async, Pydantic v2) | Async-first, clean dependency injection, automatic OpenAPI |
| **Database** | PostgreSQL 16 + pgvector | JSONB extraction fields, RLS for tenancy, vector column available |
| **DB driver** | asyncpg | Direct parameterised queries, no ORM overhead on hot paths |
| **Queue (prod)** | Azure Service Bus (topics + subscriptions) | Exactly-once delivery, dead-letter, replay |
| **Queue (dev)** | RabbitMQ via aio-pika | Same interface, no Azure account needed locally |
| **Blob (prod)** | Azure Blob Storage | Time-limited SAS URLs for secure downloads |
| **Blob (dev)** | Azurite | Local emulator — identical SDK interface |
| **Search (prod)** | Azure AI Search (Standard) | Hybrid vector + BM25, semantic ranking, tenant OData filter |
| **Search (dev)** | Elasticsearch 8 | kNN vectors, local Docker, no Azure dependency |
| **LLM** | Azure OpenAI GPT-4o | 128k context, structured output, tool-calling |
| **Embeddings** | text-embedding-3-large | 3072 dimensions, stored in Azure AI Search + pgvector |
| **Frontend** | Next.js 14 App Router + TypeScript | Server Components, SSE streaming, Tailwind CSS |
| **Auth** | JWT / JWKS via PyJWT + PyJWKClient | RS256, 1h key cache, OIDC-compatible |
| **IaC** | Terraform (azurerm) | Declarative Azure provisioning, remote state in Azure Blob |
| **CI/CD** | GitHub Actions (OIDC) | No long-lived secrets, ACR push, Container Apps deploy |
| **Logging** | structlog (JSON + OTel) | Structured, searchable, trace-context propagation |
| **Retries** | tenacity | Exponential back-off on all LLM + external API calls |
| **Evals** | RAGAS + custom mock runner | RAG quality + agent behaviour tested in CI |

---

## Quick Start

### Prerequisites

- Docker Engine + Compose v2
- An Azure OpenAI resource with `gpt-4o` and `text-embedding-3-large` deployments

### 1. Clone and configure

```bash
git clone https://github.com/saidulIslam1602/Allergo_Nordic.git
cd Allergo_Nordic
cp .env.example .env
# Edit .env: set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY
```

### 2. Start the full stack

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3001 |
| ingest-service API docs | http://localhost:8001/docs |
| document-service API docs | http://localhost:8002/docs |
| search-service API docs | http://localhost:8003/docs |
| chat-service API docs | http://localhost:8004/docs |
| RabbitMQ UI | http://localhost:15672 (allergo/allergo) |
| Elasticsearch | http://localhost:9200 |
| PostgreSQL | localhost:5435 (allergo/allergo/allergo) |

> Auth is disabled locally (`AUTH_ENABLED=false`). All endpoints are open without a Bearer token.

### 3. Run the infra agent (demo mode — no Azure keys)

```bash
# Seed demo findings
make migrate

# Start an infra remediation session
curl -X POST http://localhost:8004/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What HIGH severity infrastructure findings do we have?",
    "session_type": "infra_remediation",
    "tenant_id": "dev-tenant"
  }'
```

### 4. Run all evals

```bash
# Infra agent evals (9 cases, mock LLM, no keys)
PYTHONPATH=services/chat-service/src:services/shared-lib/src \
  python evals/infra/eval_runner.py --cases evals/infra/cases.jsonl --mock --verbose

# RAG quality evals (offline, no keys)
python evals/rag/rag_eval.py --dataset evals/rag/eval_dataset.jsonl --offline
```

---

## Environment Variables

### Core (all services)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql://user:pass@host:5432/db` |
| `AUTH_ENABLED` | — | `true` / `false` — disable JWT in local dev |
| `AUTH_JWKS_URI` | if auth | JWKS endpoint URL |
| `AUTH_AUDIENCE` | if auth | JWT audience claim |
| `AUTH_ISSUER` | if auth | JWT issuer claim |

### Azure services

| Variable | Required | Description |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | ✅ | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | — | Omit in prod (managed identity) |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | — | Default: `gpt-4o` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | — | Default: `text-embedding-3-large` |
| `AZURE_SEARCH_ENDPOINT` | ✅ | Azure AI Search endpoint (or Elasticsearch URL) |
| `AZURE_BLOB_ACCOUNT_URL` | ✅ | Blob Storage URL (or `http://azurite:10000/devstoreaccount1`) |
| `AZURE_SERVICEBUS_NAMESPACE_FQDN` | ✅ | Service Bus FQDN (or `rabbitmq:5672`) |

### Infra agent (chat-service only)

| Variable | Description |
|---|---|
| `TERRAFORM_PLAN_PATH` | Path to a local `tfplan.json` (from `terraform show -json`) |
| `TFC_TOKEN` | Terraform Cloud API token |
| `TFC_WORKSPACE_ID` | Terraform Cloud workspace ID |
| `DOCUMENT_SERVICE_URL` | Internal URL for posture API calls (default: `http://document-service:8002`) |

---

## API Reference

### Chat (infra remediation)

```http
POST /api/v1/chat/
Content-Type: application/json

{
  "question": "Fix the SSH open to 0.0.0.0/0 finding",
  "session_type": "infra_remediation",
  "history": []
}

→ 200 {
  "answer": "...",
  "tools_used": ["list_infra_findings", "get_infra_finding", "propose_remediation"],
  "session_type": "infra_remediation",
  "tool_rounds_used": 3
}
```

### Chat (streaming, finance)

```http
POST /api/v1/chat/
Content-Type: application/json

{ "question": "What is our total AP balance for Q1 2026?", "stream": true }

→ 200 text/event-stream
data: {"type":"metadata","citations":[...],"tools_used":["query_financial_database"],"intent":"financial_data"}
data: {"type":"token","delta":"The total "}
data: {"type":"token","delta":"accounts payable..."}
data: {"type":"suggestions","suggestions":["Break down by vendor?","Show overdue items?"]}
data: [DONE]
```

### Governance (posture)

```http
# List findings
GET /api/v1/posture/findings?severity=HIGH&limit=20

# Get detail
GET /api/v1/posture/findings/{finding_id}

# Create infra remediation run
POST /api/v1/posture/runs
{ "session_type": "infra_remediation", "max_tool_rounds": 6 }

# Attach proposal
POST /api/v1/posture/runs/{run_id}/proposals
{
  "unified_diff": "--- a/infra/keyvault.tf\n+++ ...",
  "rationale_md": "## Finding\nCKV_AZURE_88...",
  "resource_addresses": ["azurerm_key_vault.main"],
  "risk_level": "medium"
}

# Approve (human-in-the-loop gate)
POST /api/v1/posture/proposals/{id}/approve

# Export as PR patch
POST /api/v1/posture/proposals/{id}/export
→ { "pr_title": "...", "pr_body": "...", "patch": "...", "git_apply_command": "..." }
```

---

## ADRs and Design Decisions

| ADR | Decision | Rationale |
|---|---|---|
| [001](docs/adr/001-queue-based-document-processing.md) | Queue-based processing | Ingest returns 202 immediately; heavy LLM pipeline runs async without blocking the upload path |
| [002](docs/adr/002-vector-store-pgvector-vs-managed.md) | Azure AI Search over pgvector | Hybrid BM25 + vector in one index; semantic ranking; no custom similarity search code |
| [003](docs/adr/003-llm-for-extraction.md) | GPT-4o for structured extraction | 30+ field extraction with JSON mode + tenacity retry beats rule-based parsers on varied document layouts |
| [005](docs/adr/005-audit-architecture.md) | Single-service audit (document-service owns `audit_events`) | Cross-service audit writes via thin HTTP endpoint; avoids distributed transaction complexity |
| — | Tool policy enforced in Python, not prompt | Prompt engineering alone is not a security boundary; `allowed_tools` frozenset is checked before any handler runs |
| — | Proposals never apply Terraform | The agent creates a record. A human approves. An engineer applies. Three separate steps, three separate actors |

---

## License

Private repository — Allergo Nordic. All rights reserved.
