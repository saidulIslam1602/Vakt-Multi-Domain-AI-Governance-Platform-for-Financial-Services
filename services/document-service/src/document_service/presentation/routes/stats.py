"""CFO dashboard statistics endpoint."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends
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
    total_amount_sum: str | None


@router.get("/", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> DashboardStats:
    """Return aggregate counts for the CFO dashboard.

    All counts are scoped to the caller's tenant.
    """
    row = await pool.fetchrow(
        """SELECT
               COUNT(*)                                           AS total_documents,
               COUNT(*) FILTER (WHERE review_status = 'pending_review') AS pending_review,
               COUNT(*) FILTER (WHERE review_status = 'approved')        AS approved,
               COUNT(*) FILTER (WHERE review_status = 'rejected')        AS rejected,
               COUNT(*) FILTER (WHERE status = 'failed')                 AS failed
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
        total_amount_sum=None,  # future: SUM() with currency normalisation
    )
