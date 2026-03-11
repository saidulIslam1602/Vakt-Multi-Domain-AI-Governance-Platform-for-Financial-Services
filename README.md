<div align="center">

# Allergo Nordic — AI-Powered CFO Document Intelligence Platform

> **Intelligent document management for Nordic finance teams.**  
> Upload invoices, contracts, and financial reports — the system extracts structured data, flags anomalies, schedules contract renewal alerts, and lets the CFO interrogate the entire document corpus via a conversational AI assistant.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Services](#services)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start (Local Dev)](#quick-start-local-dev)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Infrastructure (Azure / Terraform)](#infrastructure-azure--terraform)
- [Development Guide](#development-guide)
- [Testing](#testing)
- [Deployment](#deployment)
- [ADRs & Design Decisions](#adrs--design-decisions)

---

## Overview

Allergo Nordic is a multi-tenant SaaS platform that automates the financial document lifecycle:

1. **Ingest** — Upload files via browser or email (IMAP polling); ZIP bulk-upload supported
2. **Process** — Parse PDF/DOCX/XLSX/images → LLM extraction → semantic chunking → vector + full-text indexing
3. **Review** — CFO review queue flags high-value or anomalous documents before approval
4. **Alert** — Contract renewal scanner runs daily; webhook dispatch notifies downstream systems
5. **Search** — Hybrid semantic + full-text search across all processed documents
6. **Chat** — Agentic RAG assistant answers natural-language questions with citations, grounded on both vector search and structured financial DB queries

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Next.js Frontend  (port 3000)                  │
└───────────────────────┬──────────────────────────────────────┬──────────┘
                        │ REST                                  │ REST / SSE
          ┌─────────────▼──────────┐              ┌────────────▼───────────┐
          │   ingest-service :8001 │              │  chat-service  :8004   │
          │  Upload · List · Email │              │  Agentic RAG · SSE     │
          └─────────────┬──────────┘              └────────────────────────┘
                        │ Azure Service Bus / RabbitMQ (local)
          ┌─────────────▼──────────┐
          │ processing-service     │  (no HTTP — pure queue worker)
          │  Parse · Extract · LLM │
          │  Chunk · Index · Alert │
          └──────┬──────────┬──────┘
                 │          │
    ┌────────────▼──┐  ┌────▼─────────────────────┐
    │ Azure AI      │  │  document-service  :8002  │
    │ Search (prod) │  │  CRUD · Review · Export   │
    │ Elasticsearch │  │  Tags · Webhooks · Stats  │
    │ (local)       │  └──────────────────────────-┘
    └────────────┬──┘
                 │ embed queries
    ┌────────────▼──────────┐
    │  search-service :8003 │
    │  Hybrid search API    │
    └───────────────────────┘

Shared infrastructure:
  PostgreSQL 16 + pgvector  ·  Azure Blob Storage / Azurite  ·  Azure Key Vault
```

**Queue contract** — `ingest-service` publishes a `document_uploaded` event to the `document-events` topic. `processing-service` consumes it, runs the full pipeline, and writes results back to PostgreSQL. No direct HTTP calls between services — all coordination is message-driven.

---

## Services

| Service | Port | Role |
|---------|------|------|
| `ingest-service` | 8001 | Document upload (file, ZIP, IMAP email) → blob storage → queue publish |
| `processing-service` | — | Queue worker: parse → LLM extract → chunk → index → alert |
| `document-service` | 8002 | Document CRUD, review queue, export, webhooks, analytics |
| `search-service` | 8003 | Hybrid semantic + full-text search (Azure AI Search / Elasticsearch) |
| `chat-service` | 8004 | Agentic RAG with tool-calling, streaming SSE, saved queries |
| `frontend` | 3000 | Next.js 14 App Router — dashboard, upload, review, search, chat |
| `shared-lib` | — | Shared domain models, auth, blob, queue, rate-limit, logging |

### ingest-service
- `POST /api/v1/documents/` — upload single document (PDF, DOCX, XLSX, TXT, HTML, image)
- `GET  /api/v1/documents/` — list tenant documents (paginated)
- `GET  /api/v1/documents/email-status` — IMAP poller health & today's stats
- `GET  /api/v1/documents/{id}` — get single document
- `POST /api/v1/documents/bulk` — upload ZIP archive (all files queued in parallel)
- IMAP email poller runs as a background `asyncio` task; polls every 5 min by default

### processing-service
- Subscribes to `document-events` queue
- Pipeline: `BlobParser` → `LLMExtractor` (GPT-4o, retry with tenacity) → `TextChunker` (tiktoken cl100k) → `SearchIndexer` / `ESIndexer` → `DbUpdater` → `EmailNotifier`
- `ContractRenewalScanner` runs daily at 08:00 UTC via APScheduler — fires alert events and SMTP notifications

### document-service
- Full document lifecycle management for the CFO dashboard
- Review queue: `GET /api/v1/review/queue` → `POST /api/v1/review/{id}/decision`
- Alert rules: CRUD + real-time event log
- Analytics: spend-by-month, vendor concentration, upcoming contract expiries
- Webhooks: HMAC-SHA256 signed outbound notifications on document lifecycle events
- CSV export: streaming `StreamingResponse` for bulk data export

### search-service
- `POST /api/v1/search/` — hybrid search (semantic embedding + full-text BM25)
- Adapts automatically: Azure AI Search in production, Elasticsearch locally

### chat-service
- `POST /api/v1/chat/` — agentic RAG (standard or `stream: true` → SSE)
- Tools: `search_documents`, `query_financial_data`, `list_vendors`, `get_contract_expiries`, `get_overdue_invoices`
- `GET/POST /api/v1/chat/saved` — bookmark frequently-used questions

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| HTTP framework | **FastAPI** (async, Pydantic v2) |
| Database | **PostgreSQL 16** with **pgvector** extension |
| DB driver | **asyncpg** (direct parameterised queries) |
| Queue (prod) | **Azure Service Bus** (topics + subscriptions) |
| Queue (dev) | **RabbitMQ** via aio-pika (same interface) |
| Blob storage (prod) | **Azure Blob Storage** |
| Blob storage (dev) | **Azurite** (local emulator) |
| Search (prod) | **Azure AI Search** |
| Search (dev) | **Elasticsearch 8** |
| LLM / Embeddings | **Azure OpenAI** — GPT-4o + text-embedding-3-large |
| Auth | **JWT / JWKS** via PyJWT + PyJWKClient (cached, 1 h TTL) |
| Frontend | **Next.js 14** App Router, Tailwind CSS, TypeScript |
| Infrastructure | **Terraform** (Azure provider — Norway East region) |
| Containerisation | **Docker** + **Docker Compose** |
| Logging | **structlog** (JSON, OpenTelemetry context) |
| Retries | **tenacity** (exponential back-off on LLM calls) |
| Scheduling | **APScheduler** (contract renewal scan at 08:00 UTC) |
| Tokenisation | **tiktoken** cl100k_base (chunking pipeline) |

---

## Project Structure

```
Allergo_Nordic/
├── docker-compose.yml          # Full local stack
├── Makefile                    # Dev shortcuts
├── data/                       # Sample documents (invoices, contracts, ledgers)
├── docs/
│   ├── FRONTEND_INSPIRATION.md
│   └── adr/                    # Architecture Decision Records
├── frontend/                   # Next.js 14 app
│   └── src/app/                # App Router pages (dashboard, chat, search, …)
├── infra/                      # Terraform modules (Azure)
│   ├── main.tf
│   ├── container_apps.tf       # Azure Container Apps
│   ├── openai.tf               # Azure OpenAI deployments
│   ├── ai_search.tf            # Azure AI Search
│   ├── postgresql.tf           # Azure Database for PostgreSQL Flexible Server
│   ├── service_bus.tf          # Azure Service Bus namespace + topics
│   ├── storage.tf              # Azure Blob Storage
│   ├── keyvault.tf             # Azure Key Vault
│   └── iam.tf                  # Managed identity + RBAC role assignments
├── presentation/               # Slide deck & talking points
└── services/
    ├── shared-lib/             # Domain models, interfaces, shared infrastructure
    ├── ingest-service/         # Upload API + IMAP poller
    ├── processing-service/     # Queue worker + LLM pipeline
    ├── document-service/       # CFO CRUD API
    ├── search-service/         # Hybrid search API
    └── chat-service/           # Agentic RAG API
```

---

## Quick Start (Local Dev)

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- An Azure OpenAI resource with `gpt-4o` and `text-embedding-3-large` deployments

### 1. Clone and configure

```bash
git clone https://github.com/saidulIslam1602/Business_Case_Study.git
cd Business_Case_Study

# Copy and fill in Azure OpenAI credentials
cp .env.example .env        # or create .env manually
```

Minimum `.env` for local dev:

```env
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
```

### 2. Start the full stack

```bash
docker compose up --build
```

Services start in dependency order. The first run builds all images and seeds the database (migrations are applied automatically by the ingest-service init container).

| Service | Local URL |
|---------|-----------|
| Frontend | http://localhost:3001 |
| ingest-service API | http://localhost:8001/docs |
| document-service API | http://localhost:8002/docs |
| search-service API | http://localhost:8003/docs |
| chat-service API | http://localhost:8004/docs |
| RabbitMQ Management | http://localhost:15672 (allergo / allergo) |
| Elasticsearch | http://localhost:9200 |
| PostgreSQL | localhost:5435 (allergo / allergo / allergo) |

> **Note:** Auth is disabled in local dev (`AUTH_ENABLED: "false"`). All endpoints are open without a Bearer token.

### 3. Upload your first document

```bash
curl -X POST http://localhost:8001/api/v1/documents/ \
  -F "file=@data/invoices/invoice_telenor_2026_01.txt"
```

The document will be ingested, processed by the LLM pipeline, indexed, and searchable within seconds.

---

## Environment Variables

### ingest-service

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | — | asyncpg DSN: `postgresql://user:pass@host:5432/db` |
| `AZURE_BLOB_ACCOUNT_URL` | ✅ | — | Blob account URL (or `http://azurite:10000/devstoreaccount1`) |
| `AZURE_SERVICEBUS_NAMESPACE_FQDN` | ✅ | — | Service Bus FQDN (or `rabbitmq:5672` locally) |
| `AUTH_ENABLED` | — | `true` | Set `false` to disable JWT validation |
| `AUTH_JWKS_URI` | if auth | — | JWKS endpoint URL |
| `AUTH_AUDIENCE` | if auth | — | JWT audience claim |
| `AUTH_ISSUER` | if auth | — | JWT issuer claim |
| `EMAIL_INGEST_ENABLED` | — | `false` | Enable IMAP email polling |
| `IMAP_HOST` | if email | — | IMAP server hostname |
| `IMAP_USERNAME` | if email | — | IMAP login username |
| `IMAP_PASSWORD` | if email | — | IMAP login password |
| `IMAP_TENANT_ID` | — | `default` | Allergo tenant for ingested email docs |
| `IMAP_ALLOWED_SENDERS` | — | `""` | Comma-separated allowed sender addresses/domains |
| `CORS_ORIGINS` | — | `["*"]` | JSON array of allowed CORS origins |

### processing-service

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | — | asyncpg DSN |
| `AZURE_BLOB_ACCOUNT_URL` | ✅ | — | Blob account URL |
| `AZURE_SERVICEBUS_NAMESPACE_FQDN` | ✅ | — | Service Bus FQDN |
| `AZURE_SEARCH_ENDPOINT` | ✅ | — | Azure AI Search endpoint (or ES URL) |
| `AZURE_OPENAI_ENDPOINT` | ✅ | — | Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | — | `""` | API key (omit to use managed identity) |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | — | `gpt-4o` | Chat model deployment name |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | — | `text-embedding-3-large` | Embedding deployment name |
| `SCHEDULER_ENABLED` | — | `true` | Enable daily contract renewal scan |
| `SCHEDULER_HOUR_UTC` | — | `8` | Hour (UTC) to run the renewal scan |
| `SMTP_HOST` | — | — | SMTP server for email alerts |
| `SMTP_USERNAME` | — | — | SMTP login username |
| `SMTP_PASSWORD` | — | — | SMTP login password |
| `SMTP_TO_ADDRESS` | — | — | Recipient for renewal alerts |

### document-service

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | — | asyncpg DSN |
| `AZURE_STORAGE_ACCOUNT_URL` | ✅ | — | Blob account URL (for SAS URL generation) |
| `AUTH_ENABLED` | — | `true` | JWT validation toggle |
| `AUTH_JWKS_URI` / `AUTH_AUDIENCE` / `AUTH_ISSUER` | if auth | — | OIDC settings |

### search-service / chat-service

Both share the same pattern: `AZURE_SEARCH_ENDPOINT`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, auth settings, and `CORS_ORIGINS`.

---

## API Reference

All services expose OpenAPI docs at `/docs` (disabled in production):

| Service | Swagger UI |
|---------|-----------|
| ingest-service | http://localhost:8001/docs |
| document-service | http://localhost:8002/docs |
| search-service | http://localhost:8003/docs |
| chat-service | http://localhost:8004/docs |

### Key endpoints

**Document Upload**
```http
POST /api/v1/documents/
Content-Type: multipart/form-data
Body: file=<binary>
→ 202 Accepted { document_id, filename, status, ... }
```

**Bulk Upload (ZIP)**
```http
POST /api/v1/documents/bulk
Content-Type: multipart/form-data
Body: file=<zip-binary>
→ 202 Accepted { total_files, queued, skipped, errors, results[] }
```

**Hybrid Search**
```http
POST /api/v1/search/
{ "query": "overdue invoices from Telenor", "top": 10 }
→ 200 { query, hits[], total, search_mode }
```

**Chat (standard)**
```http
POST /api/v1/chat/
{ "question": "What is our total AP balance for Q1 2026?", "history": [] }
→ 200 { answer, citations[], tools_used[], suggestions[], model, intent }
```

**Chat (streaming SSE)**
```http
POST /api/v1/chat/
{ "question": "...", "stream": true }
→ 200 text/event-stream
  data: {"type":"metadata","citations":[...],"tools_used":[...],"intent":"..."}
  data: {"type":"token","delta":"The "}
  data: {"type":"token","delta":"total..."}
  data: {"type":"suggestions","suggestions":["Follow-up 1","Follow-up 2"]}
  data: [DONE]
```

**Document CSV Export**
```http
GET /api/v1/documents/export.csv?document_category=invoice&review_status=pending_review
→ 200 text/csv  (streaming, UTF-8)
```

**Webhook Registration**
```http
POST /api/v1/webhooks/
{ "name": "ERP sync", "url": "https://erp.allergo.no/hook", "events": ["document.ready","document.approved"] }
→ 201 { webhook_id, name, url, events, enabled, created_at }
```
Payloads are signed with `X-Allergo-Signature: sha256=<hmac>` (compatible with GitHub webhook verification).

---

## Infrastructure (Azure / Terraform)

All infrastructure is defined in `infra/` using Terraform. Target region: **Norway East** (`norwayeast`); Azure OpenAI in **Sweden Central** (GPT-4o availability).

### Resources provisioned

| Module | Azure Resource |
|--------|---------------|
| `main.tf` | Provider, backend, naming conventions |
| `resource_group.tf` | Resource Group |
| `container_apps.tf` | Azure Container Apps (one per service) + Container Apps Environment |
| `openai.tf` | Azure OpenAI (GPT-4o + text-embedding-3-large deployments) |
| `ai_search.tf` | Azure AI Search (Standard tier) |
| `postgresql.tf` | Azure Database for PostgreSQL Flexible Server (with pgvector) |
| `service_bus.tf` | Azure Service Bus Namespace (Standard) + `document-events` topic |
| `storage.tf` | Azure Blob Storage account + `raw-documents` container |
| `keyvault.tf` | Azure Key Vault (secrets for all services) |
| `iam.tf` | User-assigned Managed Identity + RBAC role assignments |

### Deploy

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set environment, postgres_admin_password, nextauth_secret

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Required secrets in `terraform.tfvars`:
- `postgres_admin_password` — PostgreSQL admin password
- `nextauth_secret` — NextAuth.js session signing secret (min 32 chars)
- `smtp_password` — SMTP password for renewal alerts (optional)
- `imap_password` — IMAP password for email ingestion (optional)

---

## Development Guide

### Run a single service locally (without Docker)

```bash
# Install shared-lib first (editable)
cd services/shared-lib
pip install -e ".[dev]"

# Then install and run the service
cd ../ingest-service
pip install -e ".[dev]"
uvicorn ingest_service.presentation.api:create_app --factory --reload --port 8001
```

### Code style

All Python services use:
- `ruff` — linting + import sorting
- `mypy` — strict type checking
- `pytest` + `pytest-asyncio` — async test runner

```bash
# From any service directory:
ruff check src/
mypy src/
pytest tests/
```

### Makefile shortcuts

```bash
make up          # docker compose up --build
make down        # docker compose down -v
make logs        # docker compose logs -f
make test        # run all service test suites
make lint        # ruff + mypy across all services
```

---

## Testing

Each service has a `tests/` directory with unit tests:

```
services/<name>/tests/
├── __init__.py
└── unit/
    ├── test_*.py
```

Run all tests:

```bash
docker compose run --rm ingest-service pytest tests/
docker compose run --rm processing-service pytest tests/
# ...or use: make test
```

Key test patterns:
- Use `AsyncMock` for queue, blob, and DB dependencies
- `make_noop_auth_dependency()` is injected via `AUTH_ENABLED=false` in test config
- All DB calls tested against a real PostgreSQL (via `pytest-asyncio` fixtures)

---

## Deployment

Production deployment uses Azure Container Apps (serverless containers with scale-to-zero). Each service container is built from its `Dockerfile` in the repository root context.

Managed Identity is used in production — no secret keys in environment variables:
- **Blob Storage** → `Storage Blob Data Contributor` role
- **Service Bus** → `Azure Service Bus Data Owner` role
- **AI Search** → `Search Index Data Contributor` role
- **Azure OpenAI** → `Cognitive Services OpenAI User` role
- **Key Vault** → `Key Vault Secrets User` role

Set `AZURE_OPENAI_API_KEY=""` (empty) in production to automatically fall back to `DefaultAzureCredential`.

---

## ADRs & Design Decisions

| ADR | Decision |
|-----|----------|
| [001 — Queue-based processing](docs/adr/001-queue-based-document-processing.md) | Async queue decouples upload from heavy LLM pipeline; ingest returns 202 immediately |
| [002 — Vector store: pgvector vs managed](docs/adr/002-vector-store-pgvector-vs-managed.md) | Azure AI Search (prod) / Elasticsearch (dev) — not pgvector — for hybrid search capability |
| [003 — LLM for extraction](docs/adr/003-llm-for-extraction.md) | GPT-4o chosen over rule-based extraction; structured output via JSON mode + retry |

---

## License

Private repository — Allergo Nordic AS. All rights reserved.
 — AI-Driven CFO Document Intelligence

**Production-grade microservice platform for financial document automation**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org)
[![Azure](https://img.shields.io/badge/Azure-Container_Apps-0078D4?logo=microsoft-azure&logoColor=white)](https://azure.microsoft.com)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC?logo=terraform&logoColor=white)](https://terraform.io)
[![License](https://img.shields.io/badge/license-Private-red)](#license)

> Allergo Nordic eliminates CFO overhead by automatically ingesting, parsing, extracting, and intelligently answering questions about financial documents — invoices, contracts, ledger exports, and financial reports — using GPT-4o, Azure AI Search, and an agentic RAG chatbot.

</div>

---

## Overview

Allergo Nordic automates the processing of high-volume financial documents (invoices, contracts, reports) using AI extraction, structured metadata storage, and an agentic RAG chatbot. Designed for CFO workflows with full compliance, audit trails, and ERP integration via webhooks.

**Core capabilities**

| Feature | Detail |
|---|---|
| AI Extraction | GPT-4o extracts 30+ financial fields (vendor, amount, due date, KID, VAT, IBAN, GL account) |
| Confidence scoring | Low-confidence documents auto-flagged for CFO review |
| Review queue | One-click approve / reject with full audit trail |
| Agentic chatbot | ReAct pattern — uses vector search + structured DB queries |
| Webhook engine | HMAC-SHA256 signed outbound events to ERP / accounting systems |
| Secure downloads | Time-limited Azure SAS URLs — no static keys |
| CFO dashboard | Live stats: total, pending, approved, rejected, failed documents |

---

## Architecture

```
┌─────────────┐     ┌───────────────────────────────────────────────────┐
│  Next.js 14 │────▶│  API Gateway (Next.js rewrites)                   │
│  Frontend   │     └───────────────────┬───────────────────────────────┘
└─────────────┘                         │
                         ┌──────────────┼──────────────┐
                         ▼              ▼               ▼
               ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
               │ ingest-svc   │ │document-svc │ │  search-svc  │
               │  :8001       │ │  :8002      │ │  :8003       │
               └──────┬───────┘ └──────┬──────┘ └──────────────┘
                      │                │
              Azure Service Bus        │             ┌──────────────┐
                      │                │             │  chat-svc    │
               ┌──────▼───────┐        │             │  :8004       │
               │processing-svc│        │             └──────────────┘
               └──────────────┘        │
                                       ▼
                               PostgreSQL + pgvector
                               Azure AI Search
                               Azure Blob Storage
```

**Services**

| Service | Port | Responsibility |
|---|---|---|
| `ingest-service` | 8001 | File upload → Blob Storage → Service Bus event |
| `processing-service` | — | Worker: OCR → LLM extraction → DB + Search index |
| `document-service` | 8002 | Metadata CRUD, review queue, webhooks, SAS downloads |
| `search-service` | 8003 | Semantic vector search via Azure AI Search |
| `chat-service` | 8004 | Agentic RAG chatbot (ReAct, tool-calling) |
| `shared-lib` | — | Shared Pydantic models, Azure SDK helpers |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Cloud** | Azure (Container Apps, OpenAI, AI Search, Blob, Service Bus, PostgreSQL, Key Vault) |
| **Backend** | Python 3.12, FastAPI, asyncpg, Pydantic v2 |
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, TanStack Query |
| **IaC** | Terraform (hashicorp/azurerm) |
| **CI/CD** | GitHub Actions (OIDC with Azure, ACR push, Container Apps deploy) |
| **Local dev** | Docker Compose, Azurite (Blob), RabbitMQ (Service Bus emu), Elasticsearch |

---

## Quick Start (Local Development)

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- An Azure OpenAI resource with `gpt-4o` and `text-embedding-3-large` deployments

### 1. Clone & configure

```bash
git clone https://github.com/saidulIslam1602/Business_Case_Study.git
cd Business_Case_Study

# Create local env file
cp .env.example .env
# Edit .env — add your AZURE_OPENAI_ENDPOINT
```

### 2. Start all services

```bash
docker compose up --build
```

Services will be available at:

| Service | URL |
|---|---|
| Frontend | http://localhost:3001 |
| Ingest API | http://localhost:8001/docs |
| Document API | http://localhost:8002/docs |
| Search API | http://localhost:8003/docs |
| Chat API | http://localhost:8004/docs |

### 3. Run database migrations

```bash
docker compose exec ingest-service python -m ingest_service.infrastructure.db.migrate
```

---

## Project Structure

```
.
├── services/
│   ├── ingest-service/         # FastAPI upload service
│   ├── processing-service/     # Async document processor
│   ├── document-service/       # Metadata & review API
│   ├── search-service/         # Vector search API
│   ├── chat-service/           # Agentic RAG chatbot
│   └── shared-lib/             # Shared domain models
├── frontend/                   # Next.js 14 app
├── infra/                      # Terraform (Azure)
│   └── terraform.tfvars.example
├── .github/workflows/          # CI/CD pipelines
├── docs/
│   └── adr/                    # Architecture Decision Records
├── presentation/               # Business case slides & proposal
├── docker-compose.yml
└── .env.example
```

---

## Infrastructure (Azure)

All infrastructure is defined as code in `infra/`. To deploy:

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Fill in your values in terraform.tfvars

terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

See `infra/variables.tf` for all configurable parameters.

---

## CI/CD

GitHub Actions workflows live in `.github/workflows/`:

| Workflow | Trigger | Action |
|---|---|---|
| `ci-frontend.yml` | Push to `main` / PR | Lint, build, push to ACR, deploy to Container App |
| `ci-python-service.yml` | Push to `main` / PR | Ruff lint, mypy, pytest, build & push to ACR |
| `terraform.yml` | Push to `main` (infra changes) | `terraform plan` on PR, `apply` on merge |

### Required GitHub secrets

| Secret | Description |
|---|---|
| `AZURE_CLIENT_ID` | OIDC federated credential client ID |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `ACR_LOGIN_SERVER` | Azure Container Registry login server |

---

## Environment Variables

Each service has its own `.env.example`. See:

- `services/ingest-service/.env.example`
- `services/processing-service/.env.example`
- `services/document-service/.env.example`
- `services/search-service/.env.example`
- `services/chat-service/.env.example`
- `frontend/.env.example`

---

## Architecture Decision Records

| ADR | Decision |
|---|---|
| [ADR-001](docs/adr/001-queue-based-document-processing.md) | Queue-based async document processing |
| [ADR-002](docs/adr/002-vector-store-pgvector-vs-managed.md) | Azure AI Search over pgvector |
| [ADR-003](docs/adr/003-llm-for-extraction.md) | GPT-4o for structured extraction |

---

## License

Private — Allergo Nordic internal use.
