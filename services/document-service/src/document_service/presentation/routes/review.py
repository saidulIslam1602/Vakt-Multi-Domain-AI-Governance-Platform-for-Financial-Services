"""Review-queue routes — CFO workflow to approve or reject flagged documents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.infrastructure.audit import append_audit_event
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/review", tags=["review"])

ReviewStatus = Literal["pending_review", "approved", "rejected", "not_required"]


class ReviewItem(BaseModel):
    document_id: str
    filename: str
    review_status: str
    needs_review: bool
    confidence_score: float | None
    total_amount: str | None
    vendor_name: str | None
    document_category: str | None
    uploaded_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None


class ReviewDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=512)


@router.get("/queue", response_model=list[ReviewItem])
async def get_review_queue(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    review_status: ReviewStatus | None = Query(default="pending_review"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ReviewItem]:
    """Return documents that require CFO review, newest first.

    By default returns only pending_review items. Pass ?review_status=approved
    to see already-approved documents etc.
    """
    params: list = [str(current_user.tenant_id)]
    where = "tenant_id = $1"

    if review_status:
        params.append(review_status)
        where += f" AND review_status = ${len(params)}"
    else:
        where += " AND needs_review = true"

    rows = await pool.fetch(
        f"""SELECT id, filename, review_status, needs_review,
                   extraction->>'confidence_score' AS confidence_score,
                   extraction->>'total_amount'     AS total_amount,
                   extraction->>'vendor_name'      AS vendor_name,
                   extraction->>'document_category' AS document_category,
                   uploaded_at, reviewed_by, reviewed_at
            FROM documents
            WHERE {where}
            ORDER BY uploaded_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
        *params, limit, offset,
    )
    return [
        ReviewItem(
            document_id=str(r["id"]),
            filename=r["filename"],
            review_status=r["review_status"] or "not_required",
            needs_review=bool(r["needs_review"]),
            confidence_score=float(r["confidence_score"]) if r["confidence_score"] else None,
            total_amount=r.get("total_amount"),
            vendor_name=r.get("vendor_name"),
            document_category=r.get("document_category"),
            uploaded_at=r["uploaded_at"],
            reviewed_by=r.get("reviewed_by"),
            reviewed_at=r.get("reviewed_at"),
        )
        for r in rows
    ]


@router.patch("/queue/{document_id}", status_code=status.HTTP_200_OK)
async def submit_review_decision(
    document_id: str,
    body: ReviewDecision,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict:
    """CFO submits approve or reject decision on a flagged document."""
    result = await pool.execute(
        """UPDATE documents
           SET review_status = $3,
               needs_review = false,
               reviewed_by = $4,
               reviewed_at = $5
           WHERE id = $1 AND tenant_id = $2 AND review_status = 'pending_review'""",
        document_id,
        str(current_user.tenant_id),
        body.decision,
        current_user.sub,
        datetime.now(timezone.utc),
    )
    # asyncpg returns "UPDATE N" string; check the row count
    if result == "UPDATE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or already reviewed.",
        )
    await append_audit_event(
        pool,
        tenant_id=str(current_user.tenant_id),
        actor=current_user.sub,
        action=f"document_review.{body.decision}",
        resource_type="document",
        resource_id=document_id,
        metadata={
            "reason": body.reason,
            "review_status": body.decision,
        },
    )
    return {"document_id": document_id, "review_status": body.decision}
