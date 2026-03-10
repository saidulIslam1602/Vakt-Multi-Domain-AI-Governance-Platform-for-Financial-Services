"""Document upload and listing routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from allergo_shared.domain.exceptions import ValidationError
from allergo_shared.infrastructure.auth import AuthenticatedUser

from ingest_service.application.use_cases.upload_document import UploadDocumentUseCase
from ingest_service.infrastructure.db.repository import PostgresDocumentRepository
from ingest_service.presentation.dependencies import (
    get_current_user,
    get_repository,
    get_upload_use_case,
)
from ingest_service.presentation.schemas import (
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
