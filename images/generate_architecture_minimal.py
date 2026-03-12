"""
Allergo Nordic — Minimal System Architecture Diagram
High-DPI (300 DPI) clean flowchart for presentations.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

OUT = Path(__file__).parent
DPI = 300

# Palette
BRAND    = "#2563EB"
BRAND_LT = "#DBEAFE"
EMERALD  = "#059669"
EMLD_LT  = "#D1FAE5"
AMBER    = "#D97706"
AMBER_LT = "#FEF3C7"
VIOLET   = "#7C3AED"
VIOL_LT  = "#EDE9FE"
ROSE     = "#E11D48"
ROSE_LT  = "#FFE4E6"
SLATE    = "#1E293B"
SLATE_M  = "#475569"
SLATE_L  = "#CBD5E1"
BG       = "#F8FAFC"
WHITE    = "#FFFFFF"


def node(ax, cx, cy, w, h, label, sublabel="",
         fc=WHITE, bar=BRAND, fs=9, sfs=7.5, r=0.12, z=3):
    """Rounded card: coloured top strip + label + optional sublabel."""
    bh = h * 0.28
    # shadow
    ax.add_patch(FancyBboxPatch((cx - w/2 + 0.03, cy - h/2 - 0.03), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        lw=0, fc="#00000018", zorder=z-1))
    # body
    ax.add_patch(FancyBboxPatch((cx - w/2, cy - h/2), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        lw=1.4, ec=SLATE_L, fc=fc, zorder=z))
    # colour top bar
    ax.add_patch(plt.Rectangle(
        (cx - w/2, cy + h/2 - bh), w, bh,
        fc=bar, lw=0, zorder=z+1))
    ax.text(cx, cy + h/2 - bh/2, label,
            ha="center", va="center", fontsize=fs, fontweight="bold",
            color=WHITE, zorder=z+2)
    if sublabel:
        ax.text(cx, cy - h/2 + h * 0.28, sublabel,
                ha="center", va="center", fontsize=sfs,
                color=SLATE_M, zorder=z+2)


def arr(ax, x1, y1, x2, y2, label="", color=SLATE_L, lw=1.6, rad=0.0):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=lw, mutation_scale=11,
                                connectionstyle=f"arc3,rad={rad}"),
                zorder=2)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx+0.05, my+0.05, label,
                fontsize=6.8, color=color, style="italic",
                ha="center", va="bottom", zorder=3)


def generate():
    FW, FH = 18, 13
    fig, ax = plt.subplots(figsize=(FW, FH), dpi=DPI)
    ax.set_xlim(0, FW); ax.set_ylim(0, FH)
    ax.set_aspect("equal"); ax.axis("off")
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)

    # ── Title ───────────────────────────────────────────────────────────────
    ax.text(FW/2, FH - 0.35,
            "Allergo Nordic  -  System Architecture",
            ha="center", va="top", fontsize=15, fontweight="bold", color=SLATE)
    ax.text(FW/2, FH - 0.88,
            "AI-Powered CFO Document Intelligence Platform  |  March 2026",
            ha="center", va="top", fontsize=8.5, color=SLATE_L, style="italic")

    # ── Row positions ────────────────────────────────────────────────────────
    #  Row 1  (top)   : User
    #  Row 2          : Frontend
    #  Row 3          : API Services (4 boxes)
    #  Row 4          : Service Bus + Processing worker
    #  Row 5          : AI/ML (GPT-4o + Embeddings)
    #  Row 6  (bottom): Data stores (3 boxes)

    NW, NH = 3.0, 1.30   # default node width / height

    # ── User ────────────────────────────────────────────────────────────────
    node(ax, 9, 12.10, 2.6, 0.90, "CFO / Finance Team",
         fc=BRAND_LT, bar=BRAND, fs=8.5, r=0.10)

    # ── Frontend ────────────────────────────────────────────────────────────
    node(ax, 9, 10.55, NW, NH, "Next.js 14 Frontend",
         sublabel=":3000  |  Dashboard · Upload · Chat · Search",
         fc=BRAND_LT, bar=BRAND)
    arr(ax, 9, 11.65, 9, 11.20, "HTTPS", color=BRAND)

    # ── Core API Services ────────────────────────────────────────────────────
    APIS = [
        (3.0,  "ingest-service",   ":8001  File/ZIP/IMAP -> Blob + Bus", EMERALD, EMLD_LT),
        (7.0,  "document-service", ":8002  CRUD · Review · Webhooks",    EMERALD, EMLD_LT),
        (11.0, "search-service",   ":8003  Hybrid semantic + BM25",      EMERALD, EMLD_LT),
        (15.0, "chat-service",     ":8004  Agentic RAG · SSE stream",    VIOLET,  VIOL_LT),
    ]
    for cx, lbl, sub, bar, fc in APIS:
        node(ax, cx, 8.90, NW, NH, lbl, sublabel=sub, fc=fc, bar=bar)

    # Frontend -> each service
    for cx, *_ in APIS:
        arr(ax, 9, 9.90, cx, 9.56, color=EMERALD, lw=1.3)

    # ── Service Bus + Processing ─────────────────────────────────────────────
    node(ax, 4.2, 7.15, 3.0, 1.10, "Azure Service Bus",
         sublabel="Topic: document-events  |  DLQ",
         fc=AMBER_LT, bar=AMBER)
    node(ax, 9.5, 7.15, 5.0, 1.10, "processing-service",
         sublabel="Parse -> GPT-4o Extract -> Chunk -> Index -> Notify",
         fc=AMBER_LT, bar=AMBER)
    node(ax, 14.8, 7.15, 2.6, 1.10, "Alert Engine",
         sublabel="Contract expiry  |  SMTP  |  Webhooks",
         fc=AMBER_LT, bar=AMBER)

    arr(ax, 3.0, 8.24, 3.75, 7.70, "publish", color=AMBER)
    arr(ax, 5.7, 7.15, 7.0, 7.15, "subscribe", color=AMBER)
    arr(ax, 12.0, 7.15, 13.5, 7.15, "fire alert", color=AMBER)

    # ── AI / ML ──────────────────────────────────────────────────────────────
    node(ax, 5.0, 5.35, 3.6, 1.10, "GPT-4o",
         sublabel="Structured extraction  |  JSON schema",
         fc=VIOL_LT, bar=VIOLET)
    node(ax, 10.0, 5.35, 3.8, 1.10, "text-embedding-3-large",
         sublabel="1536-dim vectors  |  chunk + query embeds",
         fc=VIOL_LT, bar=VIOLET)
    node(ax, 15.0, 5.35, 2.8, 1.10, "RAG + ReAct",
         sublabel="Retrieval · Tool-calls · Streaming",
         fc=VIOL_LT, bar=VIOLET)

    arr(ax, 9.5, 6.60, 5.0, 5.91, "extract", color=VIOLET)
    arr(ax, 9.5, 6.60, 10.0, 5.91, "embed", color=VIOLET)
    arr(ax, 15.0, 8.24, 15.0, 5.91, "query+tools", color=VIOLET)

    # ── Data Stores ──────────────────────────────────────────────────────────
    node(ax, 3.5, 3.50, 3.2, 1.15, "Azure Blob Storage",
         sublabel="raw-documents  |  SAS URLs  |  Azurite (dev)",
         fc=ROSE_LT, bar=ROSE)
    node(ax, 8.5, 3.50, 3.6, 1.15, "PostgreSQL 16 + pgvector",
         sublabel="Metadata · Review · Alerts · Ledger",
         fc=ROSE_LT, bar=ROSE)
    node(ax, 13.8, 3.50, 3.6, 1.15, "Azure AI Search",
         sublabel="Semantic index  |  Hybrid BM25  |  Facets",
         fc=ROSE_LT, bar=ROSE)

    arr(ax, 4.2, 6.60, 3.5, 4.08, "read blob", color=ROSE, rad=0.2)
    arr(ax, 9.5, 6.60, 8.5, 4.08, "write metadata", color=ROSE)
    arr(ax, 9.5, 6.60, 13.8, 4.08, "index chunks", color=ROSE)
    arr(ax, 3.0, 8.24, 3.5, 4.08, "upload", color=ROSE, rad=-0.2)
    arr(ax, 11.0, 8.24, 13.8, 4.08, "search", color=ROSE, rad=0.15)

    # ── Security strip at bottom ──────────────────────────────────────────────
    ax.add_patch(plt.Rectangle((0.4, 0.50), FW - 0.8, 0.55,
                                fc="#F1F5F9", ec=SLATE_L, lw=1, zorder=1))
    items = [
        "Azure Entra ID / JWT Auth",
        "Managed Identity  (no passwords)",
        "Azure Key Vault  (all secrets)",
        "OpenTelemetry  (traces + metrics)",
        "Azure Container Apps  (auto-scale)",
        "GitHub Actions CI/CD",
    ]
    for i, txt in enumerate(items):
        ax.add_patch(plt.Rectangle((0.6 + i * 2.90, 0.56), 0.14, 0.42,
                                    fc=SLATE, ec="none", zorder=2))
        ax.text(0.85 + i * 2.90, 0.77, txt,
                fontsize=6.8, color=SLATE_M, va="center", zorder=2)

    ax.text(FW/2, 0.35, "Security  |  Identity  |  Observability  |  CI/CD",
            ha="center", fontsize=7, color=SLATE_L, style="italic")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend = [
        (BRAND,   "Frontend"),
        (EMERALD, "Core APIs"),
        (AMBER,   "Async Worker"),
        (VIOLET,  "AI / ML"),
        (ROSE,    "Data Stores"),
    ]
    lx, ly = 0.55, 12.55
    ax.text(lx, ly, "LEGEND:", fontsize=7.5, fontweight="bold", color=SLATE, va="center")
    for i, (c, lbl) in enumerate(legend):
        bx = lx + 1.1 + i * 2.85
        ax.add_patch(plt.Rectangle((bx, ly - 0.13), 0.36, 0.28,
                                    fc=c, ec="none", zorder=5))
        ax.text(bx + 0.50, ly, lbl, fontsize=7.5, color=SLATE_M, va="center")

    # Watermark
    fig.text(0.997, 0.003,
             "Allergo Nordic  |  Minimal Architecture  |  March 2026",
             ha="right", va="bottom", fontsize=6.5, color=SLATE_L, style="italic")

    out = OUT / "system_architecture_minimal.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"  system_architecture_minimal.png  ->  {out}  [{DPI} DPI]")


if __name__ == "__main__":
    generate()
