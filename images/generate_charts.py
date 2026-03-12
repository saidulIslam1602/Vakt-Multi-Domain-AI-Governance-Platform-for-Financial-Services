"""
Allergo Nordic — Business Presentation Charts Generator
Produces high-DPI (300 dpi) PNG charts for use in pitch decks / presentations.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent
DPI = 1000

# ── Brand palette ─────────────────────────────────────────────────────────────
BRAND    = "#2563EB"   # brand-600 blue
BRAND_LT = "#DBEAFE"  # brand-100
BRAND_DK = "#1D4ED8"  # brand-700
EMERALD  = "#059669"
AMBER    = "#D97706"
ROSE     = "#E11D48"
SLATE    = "#334155"
SLATE_LT = "#94A3B8"
BG       = "#F8FAFC"
WHITE    = "#FFFFFF"

def apply_style(fig, ax_list):
    fig.patch.set_facecolor(BG)
    for ax in (ax_list if isinstance(ax_list, list) else [ax_list]):
        ax.set_facecolor(WHITE)
        ax.spines[["top","right"]].set_visible(False)
        ax.spines[["left","bottom"]].set_color("#E2E8F0")
        ax.tick_params(colors=SLATE, labelsize=9)
        ax.xaxis.label.set_color(SLATE)
        ax.yaxis.label.set_color(SLATE)
        ax.title.set_color(SLATE)

def add_watermark(fig):
    fig.text(0.99, 0.01, "Allergo Nordic · Business Case",
             ha="right", va="bottom", fontsize=7, color=SLATE_LT, style="italic")

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Document Processing Volume — Monthly Trend
# ═══════════════════════════════════════════════════════════════════════════════
def chart_processing_volume():
    months = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    manual  = [320, 310, 298, 285, 270, 250, 140,  80,  35]
    auto    = [ 15,  28,  55, 110, 190, 280, 420, 510, 580]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    apply_style(fig, ax)

    x = np.arange(len(months))
    w = 0.38
    bars_m = ax.bar(x - w/2, manual, w, label="Manual Processing", color=SLATE_LT, zorder=3)
    bars_a = ax.bar(x + w/2, auto,   w, label="AI-Automated",       color=BRAND,    zorder=3)

    # value labels
    for bar in bars_a:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 8, str(int(h)),
                ha="center", va="bottom", fontsize=8, color=BRAND_DK, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(months)
    ax.set_ylabel("Documents Processed", labelpad=10)
    ax.set_title("Document Processing Volume  ·  Manual vs AI-Automated", 
                 fontsize=13, fontweight="bold", pad=16)
    ax.legend(frameon=False, fontsize=9)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(100))
    ax.set_ylim(0, 680)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8, zorder=0)

    # annotation arrow
    ax.annotate("Platform\nLaunch", xy=(5.5, 280), xytext=(5.5, 450),
                arrowprops=dict(arrowstyle="->", color=BRAND_DK, lw=1.5),
                ha="center", fontsize=8, color=BRAND_DK, fontweight="bold")

    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "01_processing_volume.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  01_processing_volume.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Time-to-Approval Reduction (Days)
# ═══════════════════════════════════════════════════════════════════════════════
def chart_approval_time():
    categories = ["Invoice\nApproval", "Contract\nReview", "High-Value\nCFO Sign-off", "Vendor\nOnboarding"]
    before = [8.5, 14.2, 21.0, 18.5]
    after  = [1.2,  2.8,  3.5,  4.0]
    pct    = [int((b-a)/b*100) for b, a in zip(before, after)]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    apply_style(fig, ax)

    x = np.arange(len(categories))
    w = 0.38
    ax.bar(x - w/2, before, w, label="Before Allergo",  color=SLATE_LT, zorder=3)
    bars_a = ax.bar(x + w/2, after, w, label="With Allergo", color=EMERALD, zorder=3)

    for i, (bar, p) in enumerate(zip(bars_a, pct)):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"−{p}%", ha="center", va="bottom", fontsize=9,
                color=EMERALD, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylabel("Average Cycle Time (days)", labelpad=10)
    ax.set_title("Approval Cycle Time Reduction  ·  Days to Decision",
                 fontsize=13, fontweight="bold", pad=16)
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 26)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8, zorder=0)
    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "02_approval_time_reduction.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  02_approval_time_reduction.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Cost Savings — FTE Hours Saved per Month
# ═══════════════════════════════════════════════════════════════════════════════
def chart_fte_savings():
    months = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    hours  = [120, 210, 310, 430, 510, 590]
    nok_k  = [h * 650 / 1000 for h in hours]   # NOK 650/hr blended rate

    fig, ax1 = plt.subplots(figsize=(10, 5.5))
    apply_style(fig, ax1)

    ax2 = ax1.twinx()
    ax2.set_facecolor(WHITE)
    ax2.spines[["top","right"]].set_color("#E2E8F0")
    ax2.tick_params(colors=SLATE, labelsize=9)

    bars = ax1.bar(months, hours, color=BRAND, alpha=0.85, zorder=3, width=0.5)
    line, = ax2.plot(months, nok_k, color=AMBER, linewidth=2.5,
                     marker="o", markersize=7, zorder=4, label="Cost Saved (NOK k)")

    for bar, h in zip(bars, hours):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 8,
                 f"{h}h", ha="center", va="bottom", fontsize=8,
                 color=BRAND_DK, fontweight="bold")

    for x, y in zip(months, nok_k):
        ax2.text(months.index(x), y + 8, f"NOK {y:.0f}k",
                 ha="center", va="bottom", fontsize=7.5, color=AMBER, fontweight="bold")

    ax1.set_ylabel("FTE Hours Saved / Month", labelpad=10)
    ax2.set_ylabel("Cost Saved (NOK thousands)", labelpad=10)
    ax2.yaxis.label.set_color(SLATE)
    ax1.set_title("Finance Team Hours Freed by Automation  ·  Monthly",
                  fontsize=13, fontweight="bold", pad=16)
    ax1.set_ylim(0, 750)
    ax2.set_ylim(0, 500)
    ax1.grid(axis="y", color="#E2E8F0", linewidth=0.8, zorder=0)

    p1 = mpatches.Patch(color=BRAND, label="FTE Hours Saved")
    p2 = mpatches.Patch(color=AMBER, label="Cost Saved (NOK k)")
    ax1.legend(handles=[p1, p2], frameon=False, fontsize=9)
    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "03_fte_hours_saved.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  03_fte_hours_saved.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 4. ROI Timeline — Cumulative
# ═══════════════════════════════════════════════════════════════════════════════
def chart_roi():
    quarters = ["Q3 '25", "Q4 '25", "Q1 '26", "Q2 '26\n(proj)", "Q3 '26\n(proj)", "Q4 '26\n(proj)"]
    cost_cum   = [480, 780, 980, 1080, 1130, 1180]   # NOK k cumulative investment
    benefit_cum= [  0, 120, 510, 1050, 1750, 2600]   # NOK k cumulative benefit

    fig, ax = plt.subplots(figsize=(10, 5.5))
    apply_style(fig, ax)

    ax.fill_between(quarters, benefit_cum, cost_cum,
                    where=[b > c for b, c in zip(benefit_cum, cost_cum)],
                    alpha=0.15, color=EMERALD, label="_nolegend_")
    ax.fill_between(quarters, benefit_cum, cost_cum,
                    where=[b <= c for b, c in zip(benefit_cum, cost_cum)],
                    alpha=0.12, color=ROSE, label="_nolegend_")

    ax.plot(quarters, cost_cum,    color=ROSE,    linewidth=2.5, marker="s",
            markersize=7, label="Cumulative Cost (NOK k)", zorder=4)
    ax.plot(quarters, benefit_cum, color=EMERALD, linewidth=2.5, marker="o",
            markersize=7, label="Cumulative Benefit (NOK k)", zorder=4)

    # breakeven annotation
    ax.axvline(x=2.35, color=BRAND, linewidth=1.5, linestyle="--", alpha=0.7)
    ax.text(2.38, 1400, "Breakeven\n~Month 9", fontsize=8.5,
            color=BRAND_DK, fontweight="bold")

    ax.set_ylabel("Cumulative Value (NOK thousands)", labelpad=10)
    ax.set_title("Return on Investment  ·  Cumulative Cost vs Benefit",
                 fontsize=13, fontweight="bold", pad=16)
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(-100, 3000)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8, zorder=0)
    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "04_roi_timeline.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  04_roi_timeline.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 5. Error Rate Reduction (Data Entry & Misrouting)
# ═══════════════════════════════════════════════════════════════════════════════
def chart_error_reduction():
    categories = ["Data Entry\nErrors", "Misrouted\nDocuments", "Duplicate\nPayments", "Late\nApprovals", "Missed\nDeadlines"]
    before = [12.4, 8.7, 3.2, 34.5, 18.0]
    after  = [ 1.1, 0.6, 0.1,  4.2,  2.5]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    apply_style(fig, ax)

    x = np.arange(len(categories))
    w = 0.38
    ax.bar(x - w/2, before, w, label="Before", color="#FCA5A5", zorder=3)
    bars_a = ax.bar(x + w/2, after, w, label="With Allergo", color=EMERALD, zorder=3, alpha=0.9)

    for i, (bar, b, a) in enumerate(zip(bars_a, before, after)):
        pct = int((b-a)/b*100)
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"−{pct}%", ha="center", va="bottom", fontsize=9,
                color=EMERALD, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylabel("Error / Incident Rate (%)", labelpad=10)
    ax.set_title("Operational Error Rate Reduction  ·  % of Processed Documents",
                 fontsize=13, fontweight="bold", pad=16)
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 45)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8, zorder=0)
    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "05_error_rate_reduction.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  05_error_rate_reduction.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 6. KPI Summary — Horizontal Bar (Big Numbers)
# ═══════════════════════════════════════════════════════════════════════════════
def chart_kpi_summary():
    kpis = [
        ("Documents Processed / Month",  "580",  "↑ 38×",  BRAND),
        ("Approval Cycle Time",           "1.2 days", "↓ 86%", EMERALD),
        ("Finance FTE Hours Freed",       "590 hrs",  "/ month", BRAND),
        ("Data Entry Error Rate",         "1.1%",    "↓ from 12.4%", EMERALD),
        ("Duplicate Payment Incidents",   "0.1%",    "↓ from 3.2%", EMERALD),
        ("Estimated Annual Saving",       "NOK 4.6M", "by end of 2026", AMBER),
        ("ROI Breakeven",                 "Month 9",  "Q1 2026", BRAND_DK),
        ("AI Automation Coverage",        "94%",     "of document types", BRAND),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(14, 6.5))
    fig.patch.set_facecolor(BG)
    fig.suptitle("Allergo Nordic  ·  Business KPI Summary", 
                 fontsize=15, fontweight="bold", color=SLATE, y=1.01)

    for ax, (label, value, sub, color) in zip(axes.flat, kpis):
        ax.set_facecolor(WHITE)
        for spine in ax.spines.values():
            spine.set_color("#E2E8F0")

        ax.text(0.5, 0.72, value, transform=ax.transAxes,
                ha="center", va="center", fontsize=26, fontweight="bold",
                color=color)
        ax.text(0.5, 0.42, sub, transform=ax.transAxes,
                ha="center", va="center", fontsize=10, color=SLATE_LT)
        ax.text(0.5, 0.14, label, transform=ax.transAxes,
                ha="center", va="center", fontsize=8.5, color=SLATE,
                fontweight="semibold", wrap=True)

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        # coloured top border strip
        ax.add_patch(mpatches.FancyBboxPatch(
            (0, 0.92), 1, 0.08, transform=ax.transAxes,
            boxstyle="square,pad=0", facecolor=color, zorder=5, clip_on=False
        ))

    add_watermark(fig)
    fig.tight_layout(pad=1.2)
    fig.savefig(OUT / "06_kpi_summary.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  06_kpi_summary.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 7. Accounts Payable Ageing — Before vs After
# ═══════════════════════════════════════════════════════════════════════════════
def chart_ap_ageing():
    buckets = ["Current\n(0-30d)", "31-60 days", "61-90 days", ">90 days\nOverdue"]
    before_pct = [52, 22, 14, 12]
    after_pct  = [81, 12,  5,  2]

    x = np.arange(len(buckets))
    w = 0.38
    colors_b = [EMERALD, AMBER, "#F97316", ROSE]
    colors_a = [EMERALD, BRAND_LT, BRAND_LT, "#FCA5A5"]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    apply_style(fig, ax)

    for i, (b, a, cb) in enumerate(zip(before_pct, after_pct, colors_b)):
        ax.bar(i - w/2, b, w, color=cb,     alpha=0.75, zorder=3, label="Before" if i==0 else "_")
        ax.bar(i + w/2, a, w, color=BRAND,  alpha=0.85, zorder=3, label="With Allergo" if i==0 else "_")
        ax.text(i - w/2, b + 0.8, f"{b}%", ha="center", fontsize=9, fontweight="bold", color=SLATE)
        ax.text(i + w/2, a + 0.8, f"{a}%", ha="center", fontsize=9, fontweight="bold", color=BRAND_DK)

    ax.set_xticks(x)
    ax.set_xticklabels(buckets, fontsize=9)
    ax.set_ylabel("% of Total AP Balance", labelpad=10)
    ax.set_title("Accounts Payable Ageing  ·  Before vs With Allergo",
                 fontsize=13, fontweight="bold", pad=16)
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 100)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8, zorder=0)
    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "07_ap_ageing.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  07_ap_ageing.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 8. Automation Coverage by Document Type — Donut
# ═══════════════════════════════════════════════════════════════════════════════
def chart_automation_coverage():
    labels   = ["Invoices\n(Auto)", "Contracts\n(Auto)", "Reports\n(Auto)", "Payroll\n(Auto)", "Manual\nReview Still Needed"]
    sizes    = [34, 24, 18, 12, 12]
    colors   = [BRAND, EMERALD, AMBER, "#8B5CF6", "#E2E8F0"]
    explode  = (0.03, 0.03, 0.03, 0.03, 0.06)

    fig, ax = plt.subplots(figsize=(8, 7))
    apply_style(fig, ax)

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.0f%%",
        colors=colors, explode=explode,
        startangle=140, pctdistance=0.72,
        wedgeprops=dict(width=0.55, edgecolor=WHITE, linewidth=2),
        textprops={"fontsize": 9, "color": SLATE}
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_fontweight("bold")
        at.set_color(WHITE)

    ax.text(0, 0, "94%\nAutomated", ha="center", va="center",
            fontsize=16, fontweight="bold", color=BRAND)

    ax.set_title("Document Processing Automation Coverage",
                 fontsize=13, fontweight="bold", pad=20, color=SLATE)
    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "08_automation_coverage.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  08_automation_coverage.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 9. Monthly Recurring Revenue Impact — Cash Flow Visibility
# ═══════════════════════════════════════════════════════════════════════════════
def chart_cash_flow_visibility():
    months = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    overdue_before = [14.2, 15.8, 17.1, 18.5, 19.2, 20.1]   # % of AR
    overdue_after  = [14.2, 13.1, 10.5,  7.2,  4.8,  3.1]   # % of AR (after alerts)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    apply_style(fig, ax)

    ax.fill_between(months, overdue_before, overdue_after,
                    alpha=0.15, color=EMERALD)
    ax.plot(months, overdue_before, color=ROSE, linewidth=2.5, marker="s",
            markersize=7, label="Overdue AR % (without platform)", zorder=4)
    ax.plot(months, overdue_after,  color=EMERALD, linewidth=2.5, marker="o",
            markersize=7, label="Overdue AR % (with Allergo alerts)", zorder=4)

    ax.axvline(x=0, color=BRAND, linewidth=1.5, linestyle="--", alpha=0.6)
    ax.text(0.08, 18.8, "Platform\nActivated", fontsize=8, color=BRAND_DK, fontweight="bold")

    ax.set_ylabel("Overdue Receivables (% of Total AR)", labelpad=10)
    ax.set_title("Accounts Receivable Overdue Rate  ·  Cash Flow Visibility Impact",
                 fontsize=13, fontweight="bold", pad=16)
    ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, 25)
    ax.grid(axis="y", color="#E2E8F0", linewidth=0.8, zorder=0)
    add_watermark(fig)
    fig.tight_layout()
    fig.savefig(OUT / "09_ar_overdue_trend.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  09_ar_overdue_trend.png")

# ═══════════════════════════════════════════════════════════════════════════════
# 10. Executive Summary — Combined Dashboard (presentation hero slide)
# ═══════════════════════════════════════════════════════════════════════════════
def chart_executive_dashboard():
    fig = plt.figure(figsize=(16, 9))
    fig.patch.set_facecolor(BG)

    # Title bar
    fig.text(0.5, 0.96, "Allergo Nordic  ·  Executive Business Impact Summary",
             ha="center", va="top", fontsize=16, fontweight="bold", color=SLATE)
    fig.text(0.5, 0.915, "AI-Powered Document Intelligence Platform  ·  March 2026",
             ha="center", va="top", fontsize=10, color=SLATE_LT)

    # ── Top row: 4 big KPI tiles ──────────────────────────────────────────────
    kpi_data = [
        ("Documents / Month", "580", "38× increase", BRAND),
        ("Approval Time",     "1.2d",  "↓ 86% faster", EMERALD),
        ("Hours Freed",       "590h",  "per month", AMBER),
        ("Annual Saving",     "NOK 4.6M", "projected", EMERALD),
    ]
    for i, (label, val, sub, col) in enumerate(kpi_data):
        ax = fig.add_axes([0.03 + i*0.245, 0.64, 0.215, 0.22])
        ax.set_facecolor(WHITE)
        for sp in ax.spines.values(): sp.set_color("#E2E8F0")
        ax.set_xticks([]); ax.set_yticks([])
        ax.add_patch(mpatches.FancyBboxPatch(
            (0, 0.86), 1, 0.14, transform=ax.transAxes,
            boxstyle="square,pad=0", facecolor=col, zorder=5, clip_on=False))
        ax.text(0.5, 0.62, val, transform=ax.transAxes,
                ha="center", va="center", fontsize=24, fontweight="bold", color=col)
        ax.text(0.5, 0.35, sub, transform=ax.transAxes,
                ha="center", va="center", fontsize=9.5, color=SLATE_LT)
        ax.text(0.5, 0.12, label, transform=ax.transAxes,
                ha="center", va="center", fontsize=9, color=SLATE, fontweight="semibold")

    # ── Bottom-left: processing volume bar ───────────────────────────────────
    ax1 = fig.add_axes([0.03, 0.07, 0.42, 0.50])
    ax1.set_facecolor(WHITE)
    ax1.spines[["top","right"]].set_visible(False)
    ax1.spines[["left","bottom"]].set_color("#E2E8F0")
    ax1.tick_params(colors=SLATE, labelsize=8)

    months = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    manual = [320,310,298,285,270,250,140,80,35]
    auto   = [15,28,55,110,190,280,420,510,580]
    x = np.arange(len(months))
    ax1.bar(x-0.19, manual, 0.38, color=SLATE_LT, label="Manual", zorder=3)
    ax1.bar(x+0.19, auto,   0.38, color=BRAND,    label="AI-Automated", zorder=3)
    ax1.set_xticks(x); ax1.set_xticklabels(months, fontsize=7.5)
    ax1.set_title("Processing Volume (Monthly)", fontsize=10, fontweight="bold", color=SLATE, pad=8)
    ax1.legend(frameon=False, fontsize=8)
    ax1.set_ylim(0, 700)
    ax1.grid(axis="y", color="#E2E8F0", linewidth=0.7)

    # ── Bottom-middle: ROI curve ──────────────────────────────────────────────
    ax2 = fig.add_axes([0.50, 0.07, 0.24, 0.50])
    ax2.set_facecolor(WHITE)
    ax2.spines[["top","right"]].set_visible(False)
    ax2.spines[["left","bottom"]].set_color("#E2E8F0")
    ax2.tick_params(colors=SLATE, labelsize=7.5)

    qs = ["Q3'25","Q4'25","Q1'26","Q2'26","Q3'26","Q4'26"]
    cost_c    = [480, 780, 980,1080,1130,1180]
    benefit_c = [  0, 120, 510,1050,1750,2600]
    ax2.fill_between(qs, benefit_c, cost_c,
                     where=[b>c for b,c in zip(benefit_c,cost_c)],
                     alpha=0.12, color=EMERALD)
    ax2.plot(qs, cost_c,    color=ROSE,   lw=2, marker="s", ms=5, label="Cost")
    ax2.plot(qs, benefit_c, color=EMERALD,lw=2, marker="o", ms=5, label="Benefit")
    ax2.axvline(x=2.35, color=BRAND, lw=1.2, ls="--", alpha=0.7)
    ax2.set_title("ROI Timeline (NOK k)", fontsize=10, fontweight="bold", color=SLATE, pad=8)
    ax2.legend(frameon=False, fontsize=8)
    ax2.set_ylim(-50, 3000)
    ax2.tick_params(axis="x", rotation=30)
    ax2.grid(axis="y", color="#E2E8F0", linewidth=0.7)

    # ── Bottom-right: donut ───────────────────────────────────────────────────
    ax3 = fig.add_axes([0.76, 0.07, 0.22, 0.50])
    ax3.set_facecolor(WHITE)
    ax3.spines[["top","right","left","bottom"]].set_color("#E2E8F0")
    ax3.set_xticks([]); ax3.set_yticks([])

    sizes  = [34, 24, 18, 12, 12]
    clrs   = [BRAND, EMERALD, AMBER, "#8B5CF6", "#E2E8F0"]
    lbls   = ["Invoices", "Contracts", "Reports", "Payroll", "Manual"]
    wedges, _, autotexts = ax3.pie(
        sizes, autopct="%1.0f%%", colors=clrs, startangle=140,
        pctdistance=0.72,
        wedgeprops=dict(width=0.52, edgecolor=WHITE, linewidth=1.5),
        textprops={"fontsize": 7})
    for at in autotexts:
        at.set_fontsize(7.5); at.set_fontweight("bold"); at.set_color(WHITE)
    ax3.text(0, 0, "94%\nAuto", ha="center", va="center",
             fontsize=13, fontweight="bold", color=BRAND)
    ax3.set_title("Automation\nCoverage", fontsize=10, fontweight="bold", color=SLATE, pad=8)
    ax3.legend(lbls, loc="lower center", fontsize=7, frameon=False,
               bbox_to_anchor=(0.5, -0.08), ncol=3)

    add_watermark(fig)
    fig.savefig(OUT / "10_executive_dashboard.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("✅  10_executive_dashboard.png")


# ── Run all ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\nGenerating charts → {OUT}\n{'─'*50}")
    chart_processing_volume()
    chart_approval_time()
    chart_fte_savings()
    chart_roi()
    chart_error_reduction()
    chart_kpi_summary()
    chart_ap_ageing()
    chart_automation_coverage()
    chart_cash_flow_visibility()
    chart_executive_dashboard()
    print(f"\n{'─'*50}")
    print(f"✅  All 10 charts saved to  {OUT}")
    print("   Resolution: 300 DPI (print-ready)\n")
