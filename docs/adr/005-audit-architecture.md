# ADR 005 — Audit architecture: single-service audit trail with cross-service HTTP

**Status:** Accepted  
**Date:** 2026-05-14  
**Deciders:** Platform engineering

---

## Context

Allergo Nordic has two agent domains — finance document review and infrastructure remediation — both of which need a shared, append-only audit trail (`audit_events`). The audit covers:

- CFO approve/reject decisions on document review queue
- HITL approve/reject decisions on posture change proposals
- Chat agent policy violations (tool called outside session_type allowlist)
- Round-cap overruns

Two services need to write audit events:

1. **document-service** — owns the DB connection pool and `audit_events` table
2. **chat-service** — detects policy violations at tool-call time and must emit audit events

The question is: **how should chat-service write audit events?**

---

## Options considered

### Option A — Duplicate asyncpg logic in chat-service
Both services get their own `append_audit_event` function that writes directly to the DB.

**Pros:** No network hop; low latency; fully independent.  
**Cons:** Logic drift (two implementations of the same hash + INSERT); chat-service needs a direct DB connection with write access to `audit_events`; RLS requires `SET LOCAL app.tenant_id` gymnastics; two places to maintain.

### Option B — Shared library (`allergo-shared`)
Move `append_audit_event` into `allergo-shared` and import from both services.

**Pros:** Single implementation.  
**Cons:** Shared lib must grow DB-write logic; both services still need separate DB connections with write grants to `audit_events`; RLS tenant isolation still requires per-service connection setup.

### Option C (chosen) — Thin HTTP endpoint on document-service
document-service exposes `POST /api/v1/audit` that proxies to its own `append_audit_event`. chat-service calls it via `aiohttp`.

**Pros:**
- Single implementation of `append_audit_event` — one place to maintain
- Audit writes are always tenant-scoped via the authenticated JWT (chat-service cannot fake another tenant's audit trail)
- chat-service does not need direct `audit_events` write access — principle of least privilege
- Fails safely: if document-service is unreachable, chat-service logs a warning and continues (audit loss vs service failure trade-off is deliberate)

**Cons:**
- Network hop adds latency (~1–5ms intra-cluster)
- chat-service must forward the Bearer token so document-service can extract `tenant_id`
- Audit emit is fire-and-forget — not transactional with the action that triggered it

---

## Decision

Use **Option C**. document-service owns `audit_events` and exposes `POST /api/v1/audit`. chat-service calls it fire-and-forget from the policy guard in `_execute_tool`.

Key implementation details:
- Tenant is always taken from the authenticated JWT in document-service — chat-service cannot override it
- The `actor` field is set to `"chat-agent/{session_type}"` so audit entries are distinguishable from human actor decisions
- Failures are logged via `allergo_shared` structured logging with `level=WARNING` and do not propagate exceptions

---

## Consequences

- `document_service.presentation.routes.audit_api` — thin `POST /audit` endpoint
- `chat_service.application.rag.RagUseCase._emit_audit` — fire-and-forget aiohttp POST
- `chat_service.presentation.config.Settings.document_service_url` — configurable base URL
- In Docker Compose: `DOCUMENT_SERVICE_URL=http://document-service:8002`
- In Azure Container Apps: internal ingress URL of the document-service container app

## Future

If audit write volume grows or SLA tightens, replace the HTTP call with a **Service Bus** message on a dedicated `audit-events` topic consumed by a dedicated audit writer microservice. The interface (`action`, `resource_type`, `resource_id`, `metadata`) remains stable.
