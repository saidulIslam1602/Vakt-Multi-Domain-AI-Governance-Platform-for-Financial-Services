"""Extraction history (audit trail) routes — who changed what and when."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/documents", tags=["audit"])


class HistoryEntry(BaseModel):
    history_id: str
    document_id: str
    extraction: dict
    changed_by: str
    changed_at: datetime
    change_reason: str | None


@router.get("/{document_id}/history", response_model=list[HistoryEntry])
async def get_extraction_history(
    document_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> list[HistoryEntry]:
    """Return all past extraction versions for a document (newest first)."""
    # Verify document belongs to this tenant
    exists = await pool.fetchval(
        "SELECT 1 FROM documents WHERE id = $1 AND tenant_id = $2",
        document_id, str(current_user.tenant_id),
    )
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    rows = await pool.fetch(
        """SELECT id, document_id, extraction, changed_by, changed_at, change_reason
           FROM extraction_history
           WHERE document_id = $1 AND tenant_id = $2
           ORDER BY changed_at DESC""",
        document_id, str(current_user.tenant_id),
    )
    return [
        HistoryEntry(
            history_id=str(r["id"]),
            document_id=str(r["document_id"]),
            extraction=dict(r["extraction"]) if r["extraction"] else {},
            changed_by=r["changed_by"],
            changed_at=r["changed_at"],
            change_reason=r.get("change_reason"),
        )
        for r in rows
    ]
