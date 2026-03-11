"""CSV export endpoint — download all document metadata as a spreadsheet."""

from __future__ import annotations

import csv
import io
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/documents", tags=["export"])

_CSV_FIELDS = [
    "document_id", "filename", "status", "document_type",
    "document_category", "vendor_name", "total_amount", "currency",
    "invoice_number", "invoice_date", "due_date",
    "contract_start_date", "contract_end_date", "contract_value",
    "cost_center", "gl_account", "store_location", "department",
    "legal_risk_flag", "report_type", "report_period",
    "confidence_score", "review_status", "uploaded_at", "tags",
]


@router.get(
    "/export.csv",
    summary="Export all documents as CSV",
    response_class=StreamingResponse,
)
async def export_csv(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    document_category: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
) -> StreamingResponse:
    """Stream all document metadata for the tenant as a UTF-8 CSV file.

    Optional filters: ?document_category=invoice&review_status=pending_review
    """
    tid = str(current_user.tenant_id)
    params: list = [tid]
    where = "tenant_id = $1"
    if document_category:
        params.append(document_category)
        where += f" AND extraction->>'document_category' = ${len(params)}"
    if review_status:
        params.append(review_status)
        where += f" AND review_status = ${len(params)}"

    rows = await pool.fetch(
        f"""SELECT
               id, filename, status, document_type,
               extraction->>'document_category'  AS document_category,
               extraction->>'vendor_name'         AS vendor_name,
               extraction->>'total_amount'        AS total_amount,
               extraction->>'currency'            AS currency,
               extraction->>'invoice_number'      AS invoice_number,
               extraction->>'invoice_date'        AS invoice_date,
               extraction->>'due_date'            AS due_date,
               extraction->>'contract_start_date' AS contract_start_date,
               extraction->>'contract_end_date'   AS contract_end_date,
               extraction->>'contract_value'      AS contract_value,
               extraction->>'cost_center'         AS cost_center,
               extraction->>'gl_account'          AS gl_account,
               extraction->>'store_location'      AS store_location,
               extraction->>'department'          AS department,
               extraction->>'legal_risk_flag'     AS legal_risk_flag,
               extraction->>'report_type'         AS report_type,
               extraction->>'report_period'       AS report_period,
               extraction->>'confidence_score'    AS confidence_score,
               review_status,
               uploaded_at,
               tags
           FROM documents
           WHERE {where}
           ORDER BY uploaded_at DESC""",
        *params,
    )

    def _generate():  # type: ignore[return]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()
        for row in rows:
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writerow({
                "document_id": str(row["id"]),
                "filename": row["filename"],
                "status": row["status"],
                "document_type": row["document_type"],
                "document_category": row["document_category"] or "",
                "vendor_name": row["vendor_name"] or "",
                "total_amount": row["total_amount"] or "",
                "currency": row["currency"] or "",
                "invoice_number": row["invoice_number"] or "",
                "invoice_date": row["invoice_date"] or "",
                "due_date": row["due_date"] or "",
                "contract_start_date": row["contract_start_date"] or "",
                "contract_end_date": row["contract_end_date"] or "",
                "contract_value": row["contract_value"] or "",
                "cost_center": row["cost_center"] or "",
                "gl_account": row["gl_account"] or "",
                "store_location": row["store_location"] or "",
                "department": row["department"] or "",
                "legal_risk_flag": row["legal_risk_flag"] or "",
                "report_type": row["report_type"] or "",
                "report_period": row["report_period"] or "",
                "confidence_score": row["confidence_score"] or "",
                "review_status": row["review_status"] or "",
                "uploaded_at": row["uploaded_at"].isoformat() if row["uploaded_at"] else "",
                "tags": "|".join(row["tags"] or []),
            })
            yield buf.getvalue()

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=allergo-documents.csv"},
    )
