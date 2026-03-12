"""Reprocess endpoint — re-triggers the full parse → extract → index pipeline.

POST /api/v1/reprocess/{document_id}

Looks up the document in the DB, resets its status to 'uploaded', and
publishes a document.uploaded Service Bus event so the processing-service
re-runs the full pipeline (parse → LLM extraction → AI Search indexing).

Use this to backfill new extraction fields (e.g. annual_recurring_fee,
renewal_status) on documents that were processed before those fields existed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import asyncpg
from allergo_shared.domain.enums import JobEventType
from allergo_shared.infrastructure.azure.service_bus import AzureServiceBus
from allergo_shared.infrastructure.logging import get_logger
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ingest_service.presentation.dependencies import (
    _get_pool,
    _get_queue,
    get_current_user,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/reprocess", tags=["reprocess"])


class ReprocessResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    message: str


@router.post(
    "/{document_id}",
    response_model=ReprocessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-trigger the full processing pipeline for an existing document",
    description=(
        "Resets the document status to 'uploaded' and publishes a document.uploaded "
        "event so the processing-service re-runs parse → LLM extraction → AI Search "
        "indexing. Useful for backfilling new extraction fields."
    ),
)
async def reprocess_document(
    document_id: str,
    pool: Annotated[asyncpg.Pool, Depends(_get_pool)],
    queue: Annotated[AzureServiceBus, Depends(_get_queue)],
    _current_user: Annotated[object, Depends(get_current_user)],
) -> ReprocessResponse:
    """Re-trigger full pipeline for the given document_id."""

    # ── 1. Fetch document from DB ─────────────────────────────────────────────
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, tenant_id, filename, blob_path, content_type, status
               FROM documents
               WHERE id = $1::uuid""",
            document_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    tenant_id: str = str(row["tenant_id"])
    filename: str = row["filename"]
    blob_path: str = row["blob_path"]
    content_type: str = row["content_type"] or "application/octet-stream"

    logger.info(
        "reprocess_requested",
        document_id=document_id,
        tenant_id=tenant_id,
        filename=filename,
        current_status=row["status"],
    )

    # ── 2. Reset status to 'uploaded' ─────────────────────────────────────────
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE documents
               SET status = 'uploaded',
                   error_message = NULL,
                   updated_at = $2
               WHERE id = $1::uuid""",
            document_id,
            now,
        )

    # ── 3. Publish document.uploaded event ────────────────────────────────────
    await queue.publish(
        "document-events",
        {
            "event_type": JobEventType.DOCUMENT_UPLOADED,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "blob_path": blob_path,
            "filename": filename,
            "content_type": content_type,
            "timestamp": now.isoformat(),
        },
        correlation_id=document_id,
    )

    logger.info(
        "reprocess_event_published",
        document_id=document_id,
        tenant_id=tenant_id,
        blob_path=blob_path,
    )

    return ReprocessResponse(
        document_id=document_id,
        tenant_id=tenant_id,
        filename=filename,
        message="Reprocessing triggered. The document will be re-parsed, re-extracted, and re-indexed.",
    )
