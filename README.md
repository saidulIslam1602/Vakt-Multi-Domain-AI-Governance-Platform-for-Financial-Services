# Allergo Nordic — AI-Driven Document Automation

> Production-grade microservice platform for CFO document intelligence — built on Azure, FastAPI, and Next.js.

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
