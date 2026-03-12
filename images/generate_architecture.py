"""
Allergo Nordic — System Architecture Diagram Generator
Produces a high-DPI (300 DPI) PNG architecture diagram for presentations.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

OUT = Path(__file__).parent
DPI = 300

# Brand palette
BRAND      = "#2563EB"
BRAND_LT   = "#DBEAFE"
BRAND_DK   = "#1D4ED8"
EMERALD    = "#059669"
EMERALD_LT = "#D1FAE5"
AMBER      = "#D97706"
AMBER_LT   = "#FEF3C7"
ROSE       = "#E11D48"
ROSE_LT    = "#FFE4E6"
VIOLET     = "#7C3AED"
VIOLET_LT  = "#EDE9FE"
SLATE      = "#1E293B"
SLATE_MID  = "#475569"
SLATE_LT   = "#94A3B8"
SLATE_BG   = "#F1F5F9"
BG         = "#F8FAFC"
WHITE      = "#FFFFFF"
GRAY_BD    = "#CBD5E1"


def rbox(ax, x, y, w, h, title, lines=(),
         face=WHITE, bar=BRAND, bar_txt=WHITE, border=GRAY_BD,
         badge="", fontsize=8.2, title_sz=9.2, radius=0.18, z=3):
    bar_h = h * 0.30
    ax.add_patch(FancyBboxPatch(
        (x + 0.05, y - 0.05), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        lw=0, fc="#00000015", zorder=z - 1))
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        lw=1.2, ec=border, fc=face, zorder=z))
    ax.add_patch(plt.Rectangle(
        (x, y + h - bar_h), w, bar_h,
        fc=bar, lw=0, zorder=z + 1))
    if badge:
        bw = len(badge) * 0.10 + 0.22
        ax.add_patch(plt.Rectangle(
            (x + w - bw - 0.09, y + h - bar_h + 0.07),
            bw, bar_h - 0.14,
            fc="#FFFFFF40", lw=0, zorder=z + 2))
        ax.text(x + w - bw / 2 - 0.09, y + h - bar_h / 2, badge,
                ha="center", va="center", fontsize=6.5,
                color=WHITE, fontweight="bold", zorder=z + 3)
    ax.text(x + 0.14, y + h - bar_h / 2, title,
            ha="left", va="center", fontsize=title_sz, fontweight="bold",
            color=bar_txt, zorder=z + 2)
    if lines:
        avail_h = h - bar_h - 0.12
        step = avail_h / (len(lines) + 0.5)
        for i, ln in enumerate(lines):
            ax.text(x + 0.14, y + h - bar_h - 0.20 - i * step,
                    ln, ha="left", va="top",
                    fontsize=fontsize, color=SLATE_MID, zorder=z + 2)


def arrow(ax, x1, y1, x2, y2, color=SLATE_LT, lw=1.5,
          label="", lc=None, rad=0.0, z=2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(
                    arrowstyle="-|>", color=color, lw=lw, mutation_scale=10,
                    connectionstyle=f"arc3,rad={rad}"),
                zorder=z)
    if label:
        mx = (x1 + x2) / 2 + 0.06
        my = (y1 + y2) / 2 + 0.06
        ax.text(mx, my, label, fontsize=6.8, color=lc or color,
                ha="center", va="bottom", style="italic", zorder=z + 1)


def grp(ax, x, y, w, h, label, face="#F1F5F918", border=GRAY_BD, lc=SLATE_MID, z=1):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.28",
        lw=1.8, ec=border, fc=face, ls="--", zorder=z))
    ax.text(x + 0.20, y + h - 0.14, label,
            fontsize=8.5, color=lc, fontweight="bold",
            va="top", ha="left", zorder=z + 1)


def generate_architecture():
    FW, FH = 28, 20
    fig, ax = plt.subplots(figsize=(FW, FH), dpi=DPI)
    ax.set_xlim(0, FW); ax.set_ylim(0, FH)
    ax.set_aspect("equal"); ax.axis("off")
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)

    # Title
    ax.text(FW / 2, FH - 0.42,
            "Allergo Nordic  --  AI-Powered CFO Document Intelligence Platform",
            ha="center", va="top", fontsize=18, fontweight="bold", color=SLATE)
    ax.text(FW / 2, FH - 1.08,
            "System Architecture Overview   |   March 2026",
            ha="center", va="top", fontsize=10.5, color=SLATE_LT, style="italic")

    # ── Layer 1: Client ──────────────────────────────────────────────────────
    grp(ax, 0.6, 15.8, 26.8, 2.50,
        "[1]  CLIENT LAYER", face="#DBEAFE14", border=BRAND, lc=BRAND_DK)

    rbox(ax, 1.1, 16.15, 4.6, 1.80,
         "Next.js 14  Frontend", [
             "Port :3000  |  App Router  |  TypeScript 5",
             "Dashboard  |  Document Upload  |  Chat UI",
             "Review Queue  |  Search  |  Analytics pages",
             "Tailwind CSS  |  JWT auth header injection",
         ],
         face=BRAND_LT, bar=BRAND, badge=":3000", fontsize=7.8)

    ax.text(3.4, 18.57, "CFO / Finance Team",
            ha="center", va="center", fontsize=9,
            color=BRAND_DK, fontweight="bold")
    ax.annotate("", xy=(3.4, 17.97), xytext=(3.4, 18.50),
                arrowprops=dict(arrowstyle="-|>", color=BRAND_DK,
                                lw=2, mutation_scale=10), zorder=4)
    ax.text(3.95, 18.24, "HTTPS", fontsize=7.5, color=BRAND_DK,
            style="italic", va="center")

    # ── Layer 2: Core APIs ───────────────────────────────────────────────────
    grp(ax, 0.6, 12.65, 26.8, 2.90,
        "[2]  CORE API SERVICES  (Azure Container Apps)",
        face="#D1FAE514", border=EMERALD, lc=EMERALD)

    SVC_Y = 13.05
    rbox(ax, 0.9, SVC_Y, 4.2, 2.05,
         "ingest-service", [
             "Port :8001  |  FastAPI  |  async",
             "File / ZIP / IMAP email upload endpoint",
             "Writes raw docs -> Azure Blob Storage",
             "Publishes document-events -> Service Bus",
             "JWT auth  |  50 MB upload limit",
         ],
         face=EMERALD_LT, bar=EMERALD, badge=":8001", fontsize=7.5)

    rbox(ax, 5.75, SVC_Y, 4.5, 2.05,
         "document-service", [
             "Port :8002  |  FastAPI  |  async",
             "Metadata CRUD  |  CFO Review Queue",
             "Alert Rules  |  Webhooks (HMAC-SHA256)",
             "Streaming CSV Export  |  Analytics API",
             "Spend / Vendor / Contract Expiry stats",
         ],
         face=EMERALD_LT, bar=EMERALD, badge=":8002", fontsize=7.5)

    rbox(ax, 10.9, SVC_Y, 4.4, 2.05,
         "search-service", [
             "Port :8003  |  FastAPI  |  async",
             "Hybrid semantic + full-text (BM25)",
             "Azure AI Search  (production)",
             "Elasticsearch  (local dev)",
             "Faceted filters  |  semantic re-ranking",
         ],
         face=EMERALD_LT, bar=EMERALD, badge=":8003", fontsize=7.5)

    rbox(ax, 16.0, SVC_Y, 4.7, 2.05,
         "chat-service", [
             "Port :8004  |  FastAPI  |  SSE stream",
             "Agentic RAG  |  ReAct reasoning loop",
             "12+ structured DB tool-call functions",
             "Intent classification  |  Follow-ups",
             "Streaming token output to browser",
         ],
         face=VIOLET_LT, bar=VIOLET, badge=":8004", fontsize=7.5)

    for sx, lbl in [(3.0, "REST"), (8.0, "REST"), (13.1, "REST"), (18.35, "REST/SSE")]:
        arrow(ax, sx, 16.15, sx, 15.10, color=EMERALD, lw=1.6, label=lbl, lc=EMERALD)

    # ── Layer 3: Async Processing ────────────────────────────────────────────
    grp(ax, 0.6, 9.60, 26.8, 2.80,
        "[3]  ASYNC PROCESSING LAYER",
        face="#FEF3C714", border=AMBER, lc=AMBER)

    rbox(ax, 0.9, 10.00, 4.5, 1.95,
         "Azure Service Bus", [
             "Standard tier  (production)",
             "Topic :  document-events",
             "Subscription per consumer service",
             "Dead-Letter Queue (DLQ) on failure",
             "RabbitMQ  (local dev equivalent)",
         ],
         face=AMBER_LT, bar=AMBER, fontsize=7.5)

    rbox(ax, 6.4, 10.00, 7.0, 1.95,
         "processing-service  (pure queue worker - no HTTP port)", [
             "BlobParser  ->  LLMExtractor (GPT-4o, tenacity 3x retry)",
             "TextChunker (tiktoken cl100k_base)  ->  SearchIndexer",
             "ESIndexer  ->  DbUpdater  ->  EmailNotifier",
             "Idempotent processing  |  circuit-breaker on LLM calls",
             "ContractRenewalScanner via APScheduler (daily 08:00 UTC)",
         ],
         face=AMBER_LT, bar=AMBER, fontsize=7.5)

    rbox(ax, 14.3, 10.00, 4.5, 1.95,
         "Alert & Notification Engine", [
             "Contract expiry detection (N-day horizon)",
             "SMTP notifications -> finance team",
             "Alert events -> document-service log",
             "Real-time event log in CFO dashboard",
             "Outbound webhooks (HMAC-SHA256 signed)",
         ],
         face=AMBER_LT, bar=AMBER, fontsize=7.5)

    arrow(ax, 3.0, 13.05, 3.15, 11.95, color=AMBER, lw=1.8, label="publish event", lc=AMBER)
    arrow(ax, 5.4, 10.98, 6.4, 10.98, color=AMBER, lw=1.8, label="subscribe", lc=AMBER)
    arrow(ax, 13.4, 10.98, 14.3, 10.98, color=AMBER, lw=1.4, label="fire alert", lc=AMBER)

    # ── Layer 4: AI / ML ─────────────────────────────────────────────────────
    grp(ax, 0.6, 6.70, 26.8, 2.65,
        "[4]  AI / ML LAYER  (Azure OpenAI)",
        face="#EDE9FE14", border=VIOLET, lc=VIOLET)

    rbox(ax, 0.9, 7.05, 5.0, 1.90,
         "GPT-4o  (Structured Extraction)", [
             "Azure OpenAI  gpt-4o  deployment",
             "JSON schema-enforced output parsing",
             "Invoice | Contract | Report | Ledger",
             "tenacity retry (3 attempts, exp backoff)",
             "~2 000 tokens/doc  (approx. $0.005/doc)",
         ],
         face=VIOLET_LT, bar=VIOLET, fontsize=7.5)

    rbox(ax, 6.7, 7.05, 5.3, 1.90,
         "text-embedding-3-large", [
             "Azure OpenAI  embedding  deployment",
             "1 536-dimensional dense vectors",
             "Document chunk embeddings at ingest",
             "Query embeddings at search/chat time",
             "~1 500 tokens/doc  (approx. $0.0002/doc)",
         ],
         face=VIOLET_LT, bar=VIOLET, fontsize=7.5)

    rbox(ax, 12.8, 7.05, 5.1, 1.90,
         "RAG Pipeline  (Retrieval-Augmented Gen)", [
             "Vector similarity + BM25 score fusion",
             "Semantic re-ranking  |  Top-K chunks",
             "Context window management (tiktoken)",
             "Grounded, cited CFO-facing responses",
             "Hybrid search via Azure AI Search",
         ],
         face=VIOLET_LT, bar=VIOLET, fontsize=7.5)

    rbox(ax, 18.7, 7.05, 5.0, 1.90,
         "Agentic Tool-Calling  (ReAct Loop)", [
             "12+ structured DB / analytics tools",
             "Intent classification per utterance",
             "Reasoning trace  ->  tool selection",
             "Follow-up question suggestions",
             "GPT-4o streaming token output",
         ],
         face=VIOLET_LT, bar=VIOLET, fontsize=7.5)

    arrow(ax, 9.65, 10.00, 3.4, 8.95, color=VIOLET, lw=1.6, label="extract", lc=VIOLET)
    arrow(ax, 9.65, 10.00, 9.35, 8.95, color=VIOLET, lw=1.6, label="embed chunks", lc=VIOLET)
    arrow(ax, 18.35, 13.05, 15.35, 8.95, color=VIOLET, lw=1.5, label="query", lc=VIOLET)
    arrow(ax, 20.35, 13.05, 21.2, 8.95, color=VIOLET, lw=1.4, label="tool call", lc=VIOLET)

    # ── Layer 5: Data & Storage ──────────────────────────────────────────────
    grp(ax, 0.6, 3.70, 26.8, 2.75,
        "[5]  DATA & STORAGE LAYER  (Azure-managed services)",
        face="#FFE4E614", border=ROSE, lc=ROSE)

    rbox(ax, 0.9, 4.05, 4.0, 2.00,
         "Azure Blob Storage", [
             "Container :  raw-documents",
             "PDF / DOCX / TXT / ZIP ingestion",
             "SAS URLs for secure downloads",
             "Azurite emulator  (local dev)",
             "Managed Identity access (no keys)",
         ],
         face=ROSE_LT, bar=ROSE, fontsize=7.5)

    rbox(ax, 5.6, 4.05, 4.7, 2.00,
         "PostgreSQL 16  +  pgvector", [
             "Azure Database for PostgreSQL Flex.",
             "Document metadata  |  Review queue",
             "Alert rules  |  Webhook configs",
             "General ledger journal entries",
             "async SQLAlchemy  +  Alembic",
         ],
         face=ROSE_LT, bar=ROSE, fontsize=7.5)

    rbox(ax, 11.1, 4.05, 4.6, 2.00,
         "Azure AI Search", [
             "Standard tier  |  1 semantic index",
             "Dense vectors  (1 536-dim chunks)",
             "Hybrid :  semantic vector + BM25",
             "Faceted attribute filtering",
             "Elasticsearch  (local dev)",
         ],
         face=ROSE_LT, bar=ROSE, fontsize=7.5)

    rbox(ax, 16.5, 4.05, 4.0, 2.00,
         "Azure Key Vault", [
             "All service secrets centralised",
             "DB URLs | API keys | JWT secrets",
             "No hard-coded credentials",
             "Managed Identity read access",
             "Secret references in ACA env vars",
         ],
         face=ROSE_LT, bar=ROSE, fontsize=7.5)

    rbox(ax, 21.3, 4.05, 4.0, 2.00,
         "Azure Container Registry", [
             "Docker images for all 6 services",
             "ingest | processing | document",
             "search | chat | frontend",
             "Managed Identity pull  (no creds)",
             "Tagged by git SHA  in CI pipeline",
         ],
         face=ROSE_LT, bar=ROSE, fontsize=7.5)

    arrow(ax, 7.5, 10.00, 2.9, 6.05, color=ROSE, lw=1.4, label="read blob", lc=ROSE, rad=0.3)
    arrow(ax, 9.65, 10.00, 7.95, 6.05, color=ROSE, lw=1.4, label="write metadata", lc=ROSE)
    arrow(ax, 9.65, 10.00, 13.4, 6.05, color=ROSE, lw=1.4, label="index chunks", lc=ROSE)
    arrow(ax, 13.1, 13.05, 13.4, 6.05, color=ROSE, lw=1.2, rad=0.15)
    arrow(ax, 18.35, 13.05, 7.95, 6.05, color=ROSE, lw=1.2, rad=0.15)
    arrow(ax, 1.9, 13.05, 1.9, 6.05, color=ROSE, lw=1.4, label="upload", lc=ROSE)

    # ── Layer 6: Security / Infra ────────────────────────────────────────────
    grp(ax, 0.6, 1.05, 26.8, 2.40,
        "[6]  SECURITY  |  IDENTITY  |  OBSERVABILITY  |  CI/CD",
        face="#F1F5F918", border=SLATE_LT, lc=SLATE_MID)

    rbox(ax, 0.9, 1.40, 3.8, 1.70,
         "Azure Entra ID / JWT", [
             "OIDC / Azure AD authentication",
             "JWT Bearer tokens on all APIs",
             "JWKS URI verification per service",
             "AUTH_ENABLED flag for local testing",
         ],
         face=SLATE_BG, bar=SLATE, fontsize=7.5)

    rbox(ax, 5.4, 1.40, 3.8, 1.70,
         "Managed Identity (UAMI)", [
             "User-assigned managed identity",
             "Zero passwords or access keys",
             "RBAC:  Blob | KV | Service Bus | ACR",
             "Least-privilege role assignments",
         ],
         face=SLATE_BG, bar=SLATE, fontsize=7.5)

    rbox(ax, 9.9, 1.40, 4.3, 1.70,
         "OpenTelemetry  &  Logging", [
             "Distributed tracing across services",
             "structlog  JSON structured logging",
             "Metrics:  latency | throughput | errors",
             "Error rate per pipeline stage",
         ],
         face=SLATE_BG, bar=SLATE, fontsize=7.5)

    rbox(ax, 14.9, 1.40, 4.3, 1.70,
         "Azure Container Apps  (ACA)", [
             "One Container App per service (6)",
             "Container Apps Environment shared",
             "Auto-scaling  |  Health-check probes",
             "Ingress:  internal / external routing",
         ],
         face=SLATE_BG, bar=SLATE, fontsize=7.5)

    rbox(ax, 19.9, 1.40, 4.7, 1.70,
         "CI / CD  (GitHub Actions)", [
             "Lint:  ruff  +  mypy  +  terraform fmt",
             "Test:  pytest (all 6 services, async)",
             "Build & push Docker images to ACR",
             "Terraform plan  +  apply on merge",
         ],
         face=SLATE_BG, bar=SLATE, fontsize=7.5)

    # Legend
    legend = [
        (BRAND,   "Frontend"),
        (EMERALD, "Core APIs"),
        (AMBER,   "Async Worker"),
        (VIOLET,  "AI / ML"),
        (ROSE,    "Data & Storage"),
        (SLATE,   "Infra / Security"),
    ]
    lx, ly = 0.8, 0.68
    ax.text(lx, ly, "LEGEND:", fontsize=8, fontweight="bold", color=SLATE, va="center")
    for i, (c, lbl) in enumerate(legend):
        bx = lx + 1.2 + i * 4.2
        ax.add_patch(plt.Rectangle((bx, ly - 0.14), 0.42, 0.30,
                                    fc=c, ec="none", lw=0, zorder=5))
        ax.text(bx + 0.56, ly, lbl, fontsize=8, color=SLATE_MID, va="center")

    fig.text(0.997, 0.005,
             "Allergo Nordic  |  System Architecture  |  Confidential  |  March 2026",
             ha="right", va="bottom", fontsize=7.5, color=SLATE_LT, style="italic")

    out = OUT / "system_architecture.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"  system_architecture.png  ->  {out}  [{DPI} DPI]")


if __name__ == "__main__":
    generate_architecture()
