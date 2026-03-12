"""CFO dashboard statistics and analytics endpoints."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/stats", tags=["stats"])


class DashboardStats(BaseModel):
    total_documents: int
    pending_review: int
    approved: int
    rejected: int
    failed: int
    not_required: int
    total_amount_sum: str | None


class SpendDataPoint(BaseModel):
    period: str
    total_invoices: int
    document_count: int


class VendorConcentration(BaseModel):
    vendor_name: str
    document_count: int
    invoice_count: int


class ExpiryItem(BaseModel):
    document_id: str
    filename: str
    vendor_name: str | None
    contract_end_date: str
    contract_value: str | None
    days_until_expiry: int


class AnalyticsResponse(BaseModel):
    spend_by_month: list[SpendDataPoint]
    vendor_concentration: list[VendorConcentration]
    upcoming_expiries: list[ExpiryItem]


@router.get("/", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> DashboardStats:
    """Return aggregate counts for the CFO dashboard."""
    row = await pool.fetchrow(
        """SELECT
               COUNT(*)                                                      AS total_documents,
               COUNT(*) FILTER (WHERE review_status = 'pending_review')     AS pending_review,
               COUNT(*) FILTER (WHERE review_status = 'approved')           AS approved,
               COUNT(*) FILTER (WHERE review_status = 'rejected')           AS rejected,
               COUNT(*) FILTER (WHERE review_status = 'not_required')       AS not_required,
               COUNT(*) FILTER (WHERE status = 'failed')                    AS failed
           FROM documents
           WHERE tenant_id = $1""",
        str(current_user.tenant_id),
    )
    return DashboardStats(
        total_documents=row["total_documents"],
        pending_review=row["pending_review"],
        approved=row["approved"],
        rejected=row["rejected"],
        failed=row["failed"],
        not_required=row["not_required"],
        total_amount_sum=None,
    )


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    months: int = Query(default=12, ge=1, le=36, description="Number of months of spend history"),
    expiry_days: int = Query(default=180, ge=7, le=365, description="Expiry lookahead window in days"),
) -> AnalyticsResponse:
    """Return chart-ready analytics data: spend trend, vendor concentration, expiry timeline."""
    tid = str(current_user.tenant_id)

    # ── Spend by month ────────────────────────────────────────────────────────
    spend_rows = await pool.fetch(
        """SELECT
               to_char(date_trunc('month', (extraction->>'invoice_date')::date), 'YYYY-MM') AS period,
               COUNT(*)                                                                       AS document_count,
               COUNT(*) FILTER (WHERE extraction->>'document_category' = 'invoice')          AS total_invoices
           FROM documents
           WHERE tenant_id = $1
             AND extraction->>'invoice_date' IS NOT NULL
             AND (extraction->>'invoice_date')::date >= NOW() - ($2 || ' months')::interval
           GROUP BY period
           ORDER BY period ASC""",
        tid, str(months),
    )
    spend_by_month = [
        SpendDataPoint(
            period=r["period"],
            total_invoices=r["total_invoices"],
            document_count=r["document_count"],
        )
        for r in spend_rows
    ]

    # ── Vendor concentration (top 10) ─────────────────────────────────────────
    vendor_rows = await pool.fetch(
        """SELECT
               COALESCE(extraction->>'vendor_name', 'Unknown') AS vendor_name,
               COUNT(*)                                          AS document_count,
               COUNT(*) FILTER (WHERE extraction->>'document_category' = 'invoice') AS invoice_count
           FROM documents
           WHERE tenant_id = $1
             AND extraction->>'vendor_name' IS NOT NULL
           GROUP BY vendor_name
           ORDER BY document_count DESC
           LIMIT 10""",
        tid,
    )
    vendor_concentration = [
        VendorConcentration(
            vendor_name=r["vendor_name"],
            document_count=r["document_count"],
            invoice_count=r["invoice_count"],
        )
        for r in vendor_rows
    ]

    # ── Upcoming contract expiries ────────────────────────────────────────────
    expiry_rows = await pool.fetch(
        """SELECT
               id,
               filename,
               extraction->>'vendor_name'        AS vendor_name,
               extraction->>'contract_end_date'  AS contract_end_date,
               extraction->>'contract_value'     AS contract_value,
               ((extraction->>'contract_end_date')::date - CURRENT_DATE) AS days_until_expiry
           FROM documents
           WHERE tenant_id = $1
             AND extraction->>'document_category' = 'contract'
             AND extraction->>'contract_end_date' IS NOT NULL
             AND (extraction->>'contract_end_date')::date BETWEEN CURRENT_DATE
                 AND CURRENT_DATE + ($2 || ' days')::interval
           ORDER BY contract_end_date ASC
           LIMIT 20""",
        tid, str(expiry_days),
    )
    upcoming_expiries = [
        ExpiryItem(
            document_id=str(r["id"]),
            filename=r["filename"],
            vendor_name=r["vendor_name"],
            contract_end_date=r["contract_end_date"],
            contract_value=r["contract_value"],
            days_until_expiry=r["days_until_expiry"],
        )
        for r in expiry_rows
    ]

    return AnalyticsResponse(
        spend_by_month=spend_by_month,
        vendor_concentration=vendor_concentration,
        upcoming_expiries=upcoming_expiries,
    )
