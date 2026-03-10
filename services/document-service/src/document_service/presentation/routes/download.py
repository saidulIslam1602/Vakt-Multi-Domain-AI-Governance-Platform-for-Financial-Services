"""Secure time-limited download URL endpoint for CFO document access."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from allergo_shared.infrastructure.auth import AuthenticatedUser
from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
from document_service.presentation.dependencies import get_blob, get_current_user, get_pool

router = APIRouter(prefix="/documents", tags=["download"])


class DownloadUrlResponse(BaseModel):
    document_id: str
    filename: str
    url: str
    expires_in_seconds: int


@router.get("/{document_id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(
    document_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    blob: Annotated[AzureBlobStorage, Depends(get_blob)],
    expiry_hours: int = Query(default=1, ge=1, le=24),
) -> DownloadUrlResponse:
    """Generate a short-lived SAS URL so the CFO can download the original document.

    The URL is ephemeral (1 h by default, max 24 h) and signed with a
    user-delegation key from Managed Identity — no static account key needed.
    """
    row = await pool.fetchrow(
        "SELECT filename, blob_path FROM documents WHERE id = $1 AND tenant_id = $2",
        document_id, str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    blob_path: str = row["blob_path"]
    # blob_path format: "{tenant_id}/{document_id}/{filename}"
    parts = blob_path.split("/", 1)
    container = parts[0] if len(parts) == 2 else "documents"
    blob_name = parts[1] if len(parts) == 2 else blob_path

    sas_url = await blob.generate_sas_url(
        container=container,
        blob_name=blob_name,
        expiry_hours=expiry_hours,
    )
    return DownloadUrlResponse(
        document_id=document_id,
        filename=row["filename"],
        url=sas_url,
        expires_in_seconds=expiry_hours * 3600,
    )
