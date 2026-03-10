"""Structured financial DB reader for the chat service.

The LLM calls these functions as tools when questions require precise
numbers, aggregations, or filtered lists from the metadata database
(e.g. "total unpaid invoices this month", "contracts expiring in 30 days").
This is the second retrieval path that complements vector search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import asyncpg

from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FinancialRecord:
    document_id: str
    filename: str
    document_category: str | None
    vendor_name: str | None
    total_amount: str | None
    due_date: str | None
    invoice_number: str | None
    currency: str | None
    status: str
    review_status: str | None
    uploaded_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregationResult:
    label: str
    value: str
    count: int
    breakdown: list[dict[str, Any]] = field(default_factory=list)


class FinancialDbReader:
    """Executes pre-defined safe read queries against the documents table.

    All queries are tenant-scoped and parameterised — no raw user input
    is ever interpolated into SQL.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── Overdue / due-soon invoices ───────────────────────────────────────────

    async def get_overdue_invoices(self, tenant_id: str) -> list[FinancialRecord]:
        """Return invoices whose due_date has passed and are not yet approved."""
        today = date.today().isoformat()
        rows = await self._pool.fetch(
            """SELECT id, filename,
                      extraction->>'document_category' AS document_category,
                      extraction->>'vendor_name'        AS vendor_name,
                      extraction->>'total_amount'       AS total_amount,
                      extraction->>'due_date'           AS due_date,
                      extraction->>'invoice_number'     AS invoice_number,
                      extraction->>'currency'           AS currency,
                      status, review_status, uploaded_at
               FROM documents
               WHERE tenant_id = $1
                 AND extraction->>'document_category' = 'invoice'
                 AND extraction->>'due_date' IS NOT NULL
                 AND extraction->>'due_date' < $2
                 AND review_status != 'approved'
               ORDER BY extraction->>'due_date' ASC
               LIMIT 50""",
            tenant_id, today,
        )
        return [self._map(r) for r in rows]

    async def get_due_soon_invoices(
        self, tenant_id: str, days_ahead: int = 30
    ) -> list[FinancialRecord]:
        """Return invoices due within the next N days."""
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=days_ahead)).isoformat()
        rows = await self._pool.fetch(
            """SELECT id, filename,
                      extraction->>'document_category' AS document_category,
                      extraction->>'vendor_name'        AS vendor_name,
                      extraction->>'total_amount'       AS total_amount,
                      extraction->>'due_date'           AS due_date,
                      extraction->>'invoice_number'     AS invoice_number,
                      extraction->>'currency'           AS currency,
                      status, review_status, uploaded_at
               FROM documents
               WHERE tenant_id = $1
                 AND extraction->>'document_category' = 'invoice'
                 AND extraction->>'due_date' BETWEEN $2 AND $3
               ORDER BY extraction->>'due_date' ASC
               LIMIT 50""",
            tenant_id, today, future,
        )
        return [self._map(r) for r in rows]

    # ── Expiring contracts ────────────────────────────────────────────────────

    async def get_expiring_contracts(
        self, tenant_id: str, days_ahead: int = 90
    ) -> list[FinancialRecord]:
        """Return contracts whose end date falls within the next N days."""
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=days_ahead)).isoformat()
        rows = await self._pool.fetch(
            """SELECT id, filename,
                      extraction->>'document_category'    AS document_category,
                      extraction->>'vendor_name'           AS vendor_name,
                      extraction->>'contract_value'        AS total_amount,
                      extraction->>'contract_end_date'     AS due_date,
                      extraction->>'invoice_number'        AS invoice_number,
                      extraction->>'currency'              AS currency,
                      status, review_status, uploaded_at
               FROM documents
               WHERE tenant_id = $1
                 AND extraction->>'document_category' = 'contract'
                 AND extraction->>'contract_end_date' BETWEEN $2 AND $3
               ORDER BY extraction->>'contract_end_date' ASC
               LIMIT 50""",
            tenant_id, today, future,
        )
        return [self._map(r) for r in rows]

    # ── Amount aggregation ────────────────────────────────────────────────────

    async def count_by_category(
        self, tenant_id: str, date_from: str | None = None, date_to: str | None = None
    ) -> list[dict[str, Any]]:
        """Return document count and pending-review count per category."""
        params: list[Any] = [tenant_id]
        date_filter = ""
        if date_from:
            params.append(date_from)
            date_filter += f" AND uploaded_at >= ${len(params)}"
        if date_to:
            params.append(date_to)
            date_filter += f" AND uploaded_at <= ${len(params)}"

        rows = await self._pool.fetch(
            f"""SELECT
                    COALESCE(extraction->>'document_category', 'unknown') AS category,
                    COUNT(*)                                               AS total,
                    COUNT(*) FILTER (WHERE review_status = 'pending_review') AS pending,
                    COUNT(*) FILTER (WHERE review_status = 'approved')        AS approved
                FROM documents
                WHERE tenant_id = $1 {date_filter}
                GROUP BY category
                ORDER BY total DESC""",
            *params,
        )
        return [dict(r) for r in rows]

    async def list_by_vendor(
        self,
        tenant_id: str,
        vendor_name: str,
        document_category: str | None = None,
    ) -> list[FinancialRecord]:
        """Return all documents from a specific vendor (fuzzy ILIKE match)."""
        params: list[Any] = [tenant_id, f"%{vendor_name}%"]
        cat_filter = ""
        if document_category:
            params.append(document_category)
            cat_filter = f" AND extraction->>'document_category' = ${len(params)}"

        rows = await self._pool.fetch(
            f"""SELECT id, filename,
                       extraction->>'document_category' AS document_category,
                       extraction->>'vendor_name'        AS vendor_name,
                       extraction->>'total_amount'       AS total_amount,
                       extraction->>'due_date'           AS due_date,
                       extraction->>'invoice_number'     AS invoice_number,
                       extraction->>'currency'           AS currency,
                       status, review_status, uploaded_at
                FROM documents
                WHERE tenant_id = $1
                  AND extraction->>'vendor_name' ILIKE $2
                  {cat_filter}
                ORDER BY uploaded_at DESC
                LIMIT 50""",
            *params,
        )
        return [self._map(r) for r in rows]

    async def list_pending_approvals(self, tenant_id: str) -> list[FinancialRecord]:
        """Return documents currently awaiting CFO approval."""
        rows = await self._pool.fetch(
            """SELECT id, filename,
                      extraction->>'document_category' AS document_category,
                      extraction->>'vendor_name'        AS vendor_name,
                      extraction->>'total_amount'       AS total_amount,
                      extraction->>'due_date'           AS due_date,
                      extraction->>'invoice_number'     AS invoice_number,
                      extraction->>'currency'           AS currency,
                      status, review_status, uploaded_at
               FROM documents
               WHERE tenant_id = $1
                 AND review_status = 'pending_review'
               ORDER BY uploaded_at DESC
               LIMIT 50""",
            tenant_id,
        )
        return [self._map(r) for r in rows]

    async def get_document_summary(
        self, tenant_id: str, document_id: str
    ) -> dict[str, Any] | None:
        """Return full extraction metadata for a specific document."""
        row = await self._pool.fetchrow(
            """SELECT id, filename, status, review_status, needs_review,
                      reviewed_by, reviewed_at, uploaded_at, extraction
               FROM documents
               WHERE id = $1 AND tenant_id = $2""",
            document_id, tenant_id,
        )
        if row is None:
            return None
        result: dict[str, Any] = {
            "document_id": str(row["id"]),
            "filename": row["filename"],
            "status": row["status"],
            "review_status": row["review_status"],
            "needs_review": row["needs_review"],
            "reviewed_by": row["reviewed_by"],
            "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
            "uploaded_at": row["uploaded_at"].isoformat(),
        }
        if row["extraction"]:
            result.update(dict(row["extraction"]))
        return result

    async def get_dashboard_snapshot(self, tenant_id: str) -> dict[str, Any]:
        """Return a comprehensive financial snapshot for the CFO."""
        row = await self._pool.fetchrow(
            """SELECT
                 COUNT(*)                                              AS total,
                 COUNT(*) FILTER (WHERE status = 'failed')            AS failed,
                 COUNT(*) FILTER (WHERE review_status = 'pending_review') AS pending,
                 COUNT(*) FILTER (WHERE review_status = 'approved')   AS approved,
                 COUNT(*) FILTER (WHERE review_status = 'rejected')   AS rejected,
                 COUNT(*) FILTER (
                     WHERE extraction->>'document_category' = 'invoice'
                       AND extraction->>'due_date' < $2
                       AND review_status != 'approved'
                 ) AS overdue_invoices,
                 COUNT(*) FILTER (
                     WHERE extraction->>'document_category' = 'contract'
                       AND extraction->>'contract_end_date' BETWEEN $2 AND $3
                 ) AS expiring_contracts_90d
               FROM documents
               WHERE tenant_id = $1""",
            tenant_id,
            date.today().isoformat(),
            (date.today() + timedelta(days=90)).isoformat(),
        )
        return dict(row)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _map(r: asyncpg.Record) -> FinancialRecord:
        return FinancialRecord(
            document_id=str(r["id"]),
            filename=r["filename"],
            document_category=r.get("document_category"),
            vendor_name=r.get("vendor_name"),
            total_amount=r.get("total_amount"),
            due_date=r.get("due_date"),
            invoice_number=r.get("invoice_number"),
            currency=r.get("currency"),
            status=r["status"],
            review_status=r.get("review_status"),
            uploaded_at=r["uploaded_at"].isoformat() if r.get("uploaded_at") else "",
        )
