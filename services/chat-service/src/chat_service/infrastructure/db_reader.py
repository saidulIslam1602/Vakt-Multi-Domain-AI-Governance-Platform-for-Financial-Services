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
        """Return ALL invoices whose due_date has passed, regardless of review_status.

        NOTE: review_status reflects the CFO *approval workflow* state, NOT payment state.
          - 'approved'     → CFO reviewed and approved the invoice for payment
          - 'rejected'     → CFO rejected/disputed the invoice
          - 'not_required' → below the approval threshold (auto-passed)
          - 'pending_review' → awaiting CFO action
        An invoice can be overdue regardless of any of these states — do NOT filter by
        review_status here. The document status field tracks processing state, not payment.
        """
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
            # Filter on invoice_date (extracted from document), not file upload time
            date_filter += f" AND extraction->>'invoice_date' >= ${len(params)}"
        if date_to:
            params.append(date_to)
            date_filter += f" AND extraction->>'invoice_date' <= ${len(params)}"

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
                 ) AS overdue_invoices,
                 COUNT(*) FILTER (
                     WHERE extraction->>'document_category' = 'contract'
                       AND extraction->>'contract_end_date' BETWEEN $2 AND $3
                 ) AS expiring_contracts_90d,
                 COUNT(*) FILTER (
                     WHERE (extraction->>'legal_risk_flag')::boolean = true
                 ) AS legal_risk_documents
               FROM documents
               WHERE tenant_id = $1""",
            tenant_id,
            date.today().isoformat(),
            (date.today() + timedelta(days=90)).isoformat(),
        )
        return dict(row)

    # ── Location / store aggregation ──────────────────────────────────────────

    async def aggregate_by_location(
        self,
        tenant_id: str,
        document_category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate document count and total spend grouped by store_location."""
        params: list[Any] = [tenant_id]
        filters = "tenant_id = $1 AND extraction->>'store_location' IS NOT NULL"

        if document_category:
            params.append(document_category)
            filters += f" AND extraction->>'document_category' = ${len(params)}"
        if date_from:
            params.append(date_from)
            filters += f" AND extraction->>'invoice_date' >= ${len(params)}"
        if date_to:
            params.append(date_to)
            filters += f" AND extraction->>'invoice_date' <= ${len(params)}"

        rows = await self._pool.fetch(
            f"""SELECT
                    extraction->>'store_location'                           AS location,
                    COUNT(*)                                                AS document_count,
                    COUNT(*) FILTER (
                        WHERE extraction->>'document_category' = 'invoice'
                    )                                                       AS invoice_count,
                    COUNT(*) FILTER (
                        WHERE extraction->>'document_category' = 'contract'
                    )                                                       AS contract_count,
                    COUNT(*) FILTER (
                        WHERE (extraction->>'legal_risk_flag')::boolean = true
                    )                                                       AS legal_risk_count,
                    jsonb_agg(DISTINCT extraction->>'document_category')
                        FILTER (WHERE extraction->>'document_category' IS NOT NULL)
                                                                            AS categories,
                    MIN(extraction->>'contract_end_date')
                        FILTER (WHERE extraction->>'document_category' = 'contract')
                                                                            AS earliest_contract_expiry
                FROM documents
                WHERE {filters}
                GROUP BY location
                ORDER BY document_count DESC""",
            *params,
        )
        return [dict(r) for r in rows]

    # ── Spend by period ───────────────────────────────────────────────────────

    async def spend_by_period(
        self,
        tenant_id: str,
        period_unit: str = "month",
        document_category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate total document amounts grouped by invoice_date period.

        period_unit: 'month' (YYYY-MM) or 'quarter' (YYYY-Q#) or 'year' (YYYY).
        """
        params: list[Any] = [tenant_id]
        filters = "tenant_id = $1 AND extraction->>'invoice_date' IS NOT NULL"

        if document_category:
            params.append(document_category)
            filters += f" AND extraction->>'document_category' = ${len(params)}"
        if date_from:
            params.append(date_from)
            filters += f" AND extraction->>'invoice_date' >= ${len(params)}"
        if date_to:
            params.append(date_to)
            filters += f" AND extraction->>'invoice_date' <= ${len(params)}"

        # Period truncation expression
        if period_unit == "year":
            period_expr = "to_char((extraction->>'invoice_date')::date, 'YYYY')"
        elif period_unit == "quarter":
            period_expr = "to_char((extraction->>'invoice_date')::date, 'YYYY-Q') || to_char(EXTRACT(QUARTER FROM (extraction->>'invoice_date')::date)::int, 'FM9')"
        else:
            period_expr = "to_char((extraction->>'invoice_date')::date, 'YYYY-MM')"

        rows = await self._pool.fetch(
            f"""SELECT
                    {period_expr}                               AS period,
                    COUNT(*)                                    AS document_count,
                    COUNT(DISTINCT extraction->>'vendor_name')  AS vendor_count,
                    SUM(
                        CASE
                            WHEN extraction->>'total_amount' IS NOT NULL
                                 AND regexp_replace(extraction->>'total_amount', '[^0-9.]', '', 'g') <> ''
                            THEN regexp_replace(extraction->>'total_amount', '[^0-9.]', '', 'g')::numeric
                            ELSE 0
                        END
                    )                                           AS total_amount_nok,
                    SUM(
                        CASE
                            WHEN extraction->>'vat_amount' IS NOT NULL
                                 AND regexp_replace(extraction->>'vat_amount', '[^0-9.]', '', 'g') <> ''
                            THEN regexp_replace(extraction->>'vat_amount', '[^0-9.]', '', 'g')::numeric
                            ELSE 0
                        END
                    )                                           AS total_vat_nok,
                    SUM(
                        CASE
                            WHEN extraction->>'net_amount' IS NOT NULL
                                 AND regexp_replace(extraction->>'net_amount', '[^0-9.]', '', 'g') <> ''
                            THEN regexp_replace(extraction->>'net_amount', '[^0-9.]', '', 'g')::numeric
                            ELSE 0
                        END
                    )                                           AS total_net_nok,
                    jsonb_agg(
                        jsonb_build_object(
                            'document_id', id::text,
                            'filename', filename,
                            'vendor', extraction->>'vendor_name',
                            'amount', extraction->>'total_amount',
                            'vat_amount', extraction->>'vat_amount',
                            'net_amount', extraction->>'net_amount',
                            'vat_rate', extraction->>'vat_rate',
                            'category', extraction->>'document_category'
                        )
                    ) FILTER (WHERE true)                       AS documents
                FROM documents
                WHERE {filters}
                GROUP BY 1
                ORDER BY 1 DESC""",
            *params,
        )
        return [dict(r) for r in rows]

    # ── Spend by cost center ──────────────────────────────────────────────────

    async def spend_by_cost_center(
        self,
        tenant_id: str,
        document_category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate document count and amounts grouped by cost_center."""
        params: list[Any] = [tenant_id]
        filters = "tenant_id = $1 AND extraction->>'cost_center' IS NOT NULL"

        if document_category:
            params.append(document_category)
            filters += f" AND extraction->>'document_category' = ${len(params)}"
        if date_from:
            params.append(date_from)
            filters += f" AND extraction->>'invoice_date' >= ${len(params)}"
        if date_to:
            params.append(date_to)
            filters += f" AND extraction->>'invoice_date' <= ${len(params)}"

        rows = await self._pool.fetch(
            f"""SELECT
                    extraction->>'cost_center'                          AS cost_center,
                    extraction->>'department'                           AS department,
                    COUNT(*)                                            AS document_count,
                    jsonb_agg(DISTINCT extraction->>'document_category')
                        FILTER (WHERE extraction->>'document_category' IS NOT NULL)
                                                                        AS categories,
                    jsonb_agg(
                        jsonb_build_object(
                            'document_id', id::text,
                            'filename', filename,
                            'vendor', extraction->>'vendor_name',
                            'amount', extraction->>'total_amount',
                            'date', extraction->>'invoice_date'
                        )
                        ORDER BY extraction->>'invoice_date' DESC
                    )                                                   AS documents
                FROM documents
                WHERE {filters}
                GROUP BY cost_center, department
                ORDER BY document_count DESC""",
            *params,
        )
        return [dict(r) for r in rows]

    # ── Legal obligations tracker ─────────────────────────────────────────────

    async def get_legal_obligations(
        self,
        tenant_id: str,
        include_risk_only: bool = False,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all contracts with legal fields: obligations, termination,
        penalties, liability caps, and risk flag."""
        params: list[Any] = [tenant_id]
        filters = (
            "tenant_id = $1 "
            "AND extraction->>'document_category' = 'contract'"
        )

        if include_risk_only:
            filters += " AND (extraction->>'legal_risk_flag')::boolean = true"
        if location:
            params.append(f"%{location}%")
            filters += f" AND extraction->>'store_location' ILIKE ${len(params)}"

        rows = await self._pool.fetch(
            f"""SELECT
                    id::text                                        AS document_id,
                    filename,
                    extraction->>'vendor_name'                      AS vendor_name,
                    extraction->>'store_location'                   AS location,
                    extraction->>'contract_start_date'              AS contract_start_date,
                    extraction->>'contract_end_date'                AS contract_end_date,
                    extraction->>'contract_value'                   AS contract_value,
                    extraction->>'governing_law'                    AS governing_law,
                    extraction->>'termination_clause'               AS termination_clause,
                    extraction->>'penalty_clause'                   AS penalty_clause,
                    extraction->>'liability_cap'                    AS liability_cap,
                    extraction->>'dispute_resolution'               AS dispute_resolution,
                    (extraction->>'force_majeure')::boolean         AS force_majeure,
                    (extraction->>'indemnity_clause')::boolean      AS indemnity_clause,
                    (extraction->>'legal_risk_flag')::boolean       AS legal_risk_flag,
                    extraction->'legal_obligations'                 AS legal_obligations,
                    review_status,
                    uploaded_at
                FROM documents
                WHERE {filters}
                ORDER BY (extraction->>'legal_risk_flag')::boolean DESC NULLS LAST,
                         extraction->>'contract_end_date' ASC NULLS LAST
                LIMIT 100""",
            *params,
        )
        return [dict(r) for r in rows]

    # ── Ledger / GL account queries ───────────────────────────────────────────

    async def ledger_by_account(
        self,
        tenant_id: str,
        account_code: str | None = None,
        posting_period: str | None = None,
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return journal entries from uploaded ledger documents,
        optionally filtered by GL account code, posting period, or location."""
        params: list[Any] = [tenant_id]
        filters = (
            "tenant_id = $1 "
            "AND extraction->>'document_category' IN ('financial_report', 'other') "
            "AND jsonb_array_length(COALESCE(extraction->'ledger_entries', '[]'::jsonb)) > 0"
        )

        if posting_period:
            params.append(posting_period)
            filters += f" AND extraction->>'posting_period' ILIKE ${len(params)}"
        if location:
            params.append(f"%{location}%")
            filters += f" AND extraction->>'store_location' ILIKE ${len(params)}"

        rows = await self._pool.fetch(
            f"""SELECT
                    id::text                                AS document_id,
                    filename,
                    extraction->>'posting_period'           AS posting_period,
                    extraction->>'store_location'           AS location,
                    extraction->>'journal_ref'              AS journal_ref,
                    extraction->'ledger_entries'            AS ledger_entries
                FROM documents
                WHERE {filters}
                ORDER BY extraction->>'posting_period' DESC NULLS LAST, uploaded_at DESC
                LIMIT 50""",
            *params,
        )

        # If account_code filter requested, post-filter in Python (JSONB array element filter)
        result = []
        for r in rows:
            entries = r["ledger_entries"] or []
            if account_code:
                entries = [
                    e for e in entries
                    if str(e.get("account_code", "")).startswith(account_code)
                    or account_code.lower() in str(e.get("account_name", "")).lower()
                ]
                if not entries:
                    continue
            result.append({
                "document_id": r["document_id"],
                "filename": r["filename"],
                "posting_period": r["posting_period"],
                "location": r["location"],
                "journal_ref": r["journal_ref"],
                "entries": entries,
                "entry_count": len(entries),
            })
        return result

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
