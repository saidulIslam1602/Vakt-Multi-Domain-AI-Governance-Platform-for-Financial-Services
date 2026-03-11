"""Document upload and listing routes."""

from __future__ import annotations

import io
import mimetypes
import zipfile
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel

from allergo_shared.domain.exceptions import ValidationError
from allergo_shared.infrastructure.auth import AuthenticatedUser

from ingest_service.application.use_cases.upload_document import UploadDocumentUseCase
from ingest_service.infrastructure.config import get_settings
from ingest_service.infrastructure.db.repository import PostgresDocumentRepository
from ingest_service.presentation.dependencies import (
    get_current_user,
    get_repository,
    get_upload_use_case,
)
from ingest_service.presentation.schemas import (
    BulkUploadItem,
    BulkUploadResponse,
    DocumentListResponse,
    DocumentResponse,
    UploadResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _map_doc(doc) -> DocumentResponse:  # type: ignore[no-untyped-def]
    return DocumentResponse(
        document_id=str(doc.id),
        tenant_id=str(doc.tenant_id),
        filename=doc.filename,
        status=doc.status,
        document_type=doc.document_type,
        blob_path=doc.blob_path,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        error_message=doc.error_message,
        uploaded_at=doc.uploaded_at,
        updated_at=doc.updated_at,
    )


@router.post(
    "/",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document for processing",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document file (PDF, DOCX, XLSX, TXT, image)")],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[UploadDocumentUseCase, Depends(get_upload_use_case)],
) -> UploadResponse:
    data = await file.read()
    try:
        document = await use_case.execute(
            filename=file.filename or "unnamed",
            data=data,
            content_type=file.content_type,
            tenant_id=str(current_user.tenant_id),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)

    return UploadResponse(
        document_id=str(document.id),
        filename=document.filename,
        status=document.status,
        document_type=document.document_type,
        size_bytes=document.size_bytes,
        uploaded_at=document.uploaded_at,
    )


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List documents for the authenticated tenant",
)
async def list_documents(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    repository: Annotated[PostgresDocumentRepository, Depends(get_repository)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    docs = await repository.list_by_tenant(
        tenant_id=str(current_user.tenant_id),
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[_map_doc(d) for d in docs],
        total=len(docs),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/bulk",
    response_model=BulkUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a ZIP file containing multiple documents",
)
async def bulk_upload(
    file: Annotated[UploadFile, File(description="ZIP archive of documents (PDF, DOCX, XLSX, TXT, images)")],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[UploadDocumentUseCase, Depends(get_upload_use_case)],
) -> BulkUploadResponse:
    """Extract all files from a ZIP archive and enqueue each for processing.

    Files with unsupported extensions are skipped gracefully — the rest are
    queued normally. Returns a per-file status report.
    """
    data = await file.read()
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is not a valid ZIP archive.",
        )

    results: list[BulkUploadItem] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [m for m in zf.infolist() if not m.filename.endswith("/")]  # skip dirs
        for member in members:
            filename = member.filename.split("/")[-1]  # strip path prefix
            if not filename:
                continue
            try:
                file_bytes = zf.read(member.filename)
                # Guess content type from extension
                content_type, _ = mimetypes.guess_type(filename)
                document = await use_case.execute(
                    filename=filename,
                    data=file_bytes,
                    content_type=content_type,
                    tenant_id=str(current_user.tenant_id),
                )
                results.append(BulkUploadItem(
                    filename=filename,
                    document_id=str(document.id),
                    status="queued",
                ))
            except ValidationError as exc:
                results.append(BulkUploadItem(
                    filename=filename,
                    status="skipped",
                    error=exc.message,
                ))
            except Exception as exc:
                results.append(BulkUploadItem(
                    filename=filename,
                    status="error",
                    error=str(exc),
                ))

    return BulkUploadResponse(
        total_files=len(results),
        queued=sum(1 for r in results if r.status == "queued"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        errors=sum(1 for r in results if r.status == "error"),
        results=results,
    )


# ── Email ingest status ───────────────────────────────────────────────────────

class EmailIngestStatusResponse(BaseModel):
    enabled: bool
    imap_host: str
    imap_mailbox: str
    last_poll_at: str | None
    ingested_today: int
    errors_today: int


@router.get(
    "/email-status",
    response_model=EmailIngestStatusResponse,
    summary="Email ingestion poller status",
    description=(
        "Returns the current state of the IMAP email poller. "
        "Always safe to call — returns enabled=false when the feature is off."
    ),
)
async def email_ingest_status(
    _: Annotated[AuthenticatedUser, Depends(get_current_user)],
    request: Request,
) -> EmailIngestStatusResponse:
    cfg = get_settings()

    if not cfg.email_ingest_enabled:
        return EmailIngestStatusResponse(
            enabled=False,
            imap_host=cfg.imap_host,
            imap_mailbox=cfg.imap_mailbox,
            last_poll_at=None,
            ingested_today=0,
            errors_today=0,
        )

    pool = request.app.state.pool
    today = date.today()

    row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE error IS NULL)       AS ingested_today,
            COUNT(*) FILTER (WHERE error IS NOT NULL)   AS errors_today,
            MAX(ingested_at)                             AS last_poll_at
        FROM email_ingest_log
        WHERE ingested_at::date = $1
        """,
        today,
    )

    return EmailIngestStatusResponse(
        enabled=True,
        imap_host=cfg.imap_host,
        imap_mailbox=cfg.imap_mailbox,
        last_poll_at=row["last_poll_at"].isoformat() if row["last_poll_at"] else None,
        ingested_today=int(row["ingested_today"] or 0),
        errors_today=int(row["errors_today"] or 0),
    )


# ── NOTE: /{document_id} MUST be declared AFTER all static paths like
# /bulk, /email-status so FastAPI matches specifics before the wildcard param.
@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get a document by ID",
)
async def get_document(
    document_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    repository: Annotated[PostgresDocumentRepository, Depends(get_repository)],
) -> DocumentResponse:
    doc = await repository.get_by_id(document_id, str(current_user.tenant_id))
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return _map_doc(doc)
