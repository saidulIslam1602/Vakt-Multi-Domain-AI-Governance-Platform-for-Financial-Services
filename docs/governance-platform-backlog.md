# Governance & posture backlog (Cloudgeni-style thematic coverage)

Checkbox backlog mapping product themes to concrete repo artifacts. Goal is **full thematic coverage with honest scope** (fixtures, sandbox, CI), not a production multi-tenant clone.

**Suggested order** matches dependencies: schema and audit first, then ingestion and UI, then agent profile and gates.

---

## Phase 1 — Foundation (schema, audit, state machine)

- [x] **DB: append-only `audit_events`** — `services/ingest-service/src/ingest_service/infrastructure/db/migrations/012_posture_governance.sql`
- [x] **DB: `agent_workflow_runs` + `change_proposals`** (workflow states, proposal artifact columns)
- [x] **DB: `infra_findings`, `pipeline_runs`, `infra_context_snapshots`** (fixture-ready posture data plane)
- [x] **Emit audit on document review decisions** — `services/document-service/src/document_service/presentation/routes/review.py`, `services/document-service/src/document_service/infrastructure/audit.py`
- [x] **Emit audit on posture proposal approve/reject** — `services/document-service/src/document_service/presentation/routes/posture_proposals.py` (POST `.../approve` / `.../reject` → `append_audit_event`)
- [x] **Emit audit on chat policy violations** — `services/chat-service/src/chat_service/application/rag.py` (tool policy guard → HTTP POST `/api/v1/audit` on document-service)

---

## Phase 2 — Findings ingestion (CI → DB)

- [x] **IaC scan in CI** — `.github/workflows/ci-infra-scan.yml` (Checkov on `infra/`, JSON artifact upload)
- [x] **Importer script** — `scripts/import_checkov_findings.py` (JSON → `infra_findings`; run after CI artifact download or locally)
- [x] **Seed fixtures for local dev** — `fixtures/checkov-sample.json` (5 redacted findings) and `fixtures/terraform-plan-sample.json`; demo seeds in `013_posture_seed_demo.sql`

---

## Phase 3 — Posture API + UI (findings → proposals → approve)

- [x] **Findings API** — `document-service` at `/api/v1/posture/findings` (GET list, GET by id) — `services/document-service/src/document_service/presentation/routes/posture.py`
- [x] **Proposal API** — `POST /posture/runs`, `POST /posture/runs/{id}/proposals`, `POST /posture/proposals/{id}/validate`, `POST /posture/proposals/{id}/approve`, `POST /posture/proposals/{id}/reject`, `GET /posture/runs`, `GET /posture/runs/{id}`, `GET /posture/proposals/{id}` — `services/document-service/src/document_service/presentation/routes/posture_proposals.py`
- [x] **Next.js pages** — `frontend/src/app/posture/findings/page.tsx` (findings list + drawer), `frontend/src/app/posture/proposals/page.tsx` (runs list + new run button)
- [x] **Proposal detail view** — `frontend/src/app/posture/proposals/[id]/page.tsx` (diff, markdown rationale, Approve / Reject modal, export)

---

## Phase 4 — Agent workflows (not "RAG-only" infra path)

- [x] **Session types** — `finance_chat` vs `infra_remediation` on `POST /api/v1/chat/` — `services/chat-service/src/chat_service/presentation/routes/chat.py`
- [x] **Persist runs** with explicit states: `gathering_context` → `proposing` → `validating` → `pending_approval` → `approved` | `rejected` | `failed_validation` | `context_frozen` — `agent_workflow_runs` table + proposal state machine in `posture_proposals.py`
- [x] **Infra-oriented tools** — `services/chat-service/src/chat_service/application/tools.py`:
  - `list_infra_findings`, `get_infra_finding`, `get_terraform_plan_summary`, `propose_remediation`, `get_infra_context_bundle`
  - **No** `apply_terraform` in v1
- [x] **Pydantic validation** on proposals before `pending_approval` — `POST /posture/proposals/{id}/validate` with schema rules + `failed_validation` state
- [x] **Tool policy config** — allowed tools per `session_type`; caps on tool rounds in `MAX_TOOL_ROUNDS`; policy violations → audit event via document-service `/api/v1/audit`

---

## Phase 5 — Integrations (Git-first, CI boundaries)

- [x] **`pipeline_run` usage** — `get_terraform_plan_summary` tool reads `pipeline_runs` fixture context; `build_context_bundle` includes latest pipeline row
- [x] **`POST /posture/proposals/{id}/export`** — PR title/body template, patch file, git apply instructions — `services/document-service/src/document_service/presentation/routes/posture_proposals.py`
- [ ] **`POST /integrations/github/webhook`** — stub + signature placeholder → enqueue "rescan" (documents integration surface)

---

## Phase 6 — Infrastructure context bundle ("not RAG" brain)

- [x] **Builder** — `services/document-service/src/document_service/domain/infra_context.py` — `build_context_bundle(pool, run_id, tenant_id)` merges findings, pipeline_run, terraform plan summary, policy_pack_refs → `bundle_json`
- [x] **Snapshot endpoint** — `POST /posture/runs/{run_id}/context-snapshot` → insert `infra_context_snapshots`, transition run to `context_frozen`
- [x] **Tool `get_infra_context_bundle(snapshot_id)`** — chat tool that GETs `/api/v1/posture/snapshots/{id}` on document-service
- [ ] **Drift narrative tool** — structured summary from fixture `plan.json` + optional short LLM summary **grounded on JSON**

---

## Phase 7 — Evals & CI discipline

- [x] **Golden JSONL** — `evals/infra/cases.jsonl` (tool sequence + schema assertions)
- [x] **CI eval job** — `.github/workflows/ci-evals.yml` (mock LLM driver, no Azure keys required)
- [ ] **Optional: CFO RAG smoke tests** — separate from infra evals

---

## Phase 8 — Enterprise pluses

- [ ] **RBAC sketch** — roles `viewer`, `approver`, `admin`; enforce on posture approve routes
- [ ] **ADR: SSO** — JWT today vs Entra ID later (`docs/adr/…`)
- [x] **ADR: audit architecture** — `docs/adr/005-audit-architecture.md` (single-service audit pattern, cross-service HTTP)
- [ ] **Denied approve attempts audited** — non-approver → 403 + `audit_events`

---

## Phase 9 — Sandbox & ops story

- [ ] **Doc + optional Docker profile** — agent-runner image **without** cloud credentials; read-only tools only
- [ ] **ADR** — isolated runner, network egress allowlists for production-shaped deployments

---

## Honest scope (README / interviews)

**In repo:** fixture-backed cloud inventory and plan summaries; governance workflows; audit; CI policy scans as data; Git export templates; webhook stubs.

**Out of scope unless heavily invested:** live multi-account drift detection, production GitHub App OAuth at scale, true WASM/isolated cloud sandbox execution.

*Production would swap fixtures for cloud SDKs + runner isolation.*
