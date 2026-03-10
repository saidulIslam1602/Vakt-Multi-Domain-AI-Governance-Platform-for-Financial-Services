"""Document metadata CRUD routes."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from allergo_shared.domain.enums import DocumentStatus, DocumentType
from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/documents", tags=["documents"])


class ExtractionPatch(BaseModel):
    dates: list[str] | None = None
    parties: list[str] | None = None
    amounts: list[str] | None = None
    key_terms: list[str] | None = None
    summary: str | None = None


class DocumentDetailResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    status: DocumentStatus
    document_type: DocumentType
    page_count: int | None
    size_bytes: int | None
    uploaded_at: datetime
    updated_at: datetime
    error_message: str | None
    extraction: dict | None


class DocumentListItem(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus
    document_type: DocumentType
    uploaded_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
) -> DocumentListResponse:
    tenant_id = str(current_user.tenant_id)
    params: list = [tenant_id]
    where = "tenant_id = $1"

    if status_filter:
        params.append(str(status_filter))
        where += f" AND status = ${len(params)}"

    rows = await pool.fetch(
        f"SELECT * FROM documents WHERE {where} ORDER BY uploaded_at DESC"
        f" LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
        *params,
        limit,
        offset,
    )
    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM documents WHERE {where}", *params
    )
    items = [
        DocumentListItem(
            document_id=str(r["id"]),
            filename=r["filename"],
            status=DocumentStatus(r["status"]),
            document_type=DocumentType(r["document_type"]),
            uploaded_at=r["uploaded_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
    return DocumentListResponse(items=items, total=total or 0, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> DocumentDetailResponse:
    row = await pool.fetchrow(
        "SELECT * FROM documents WHERE id = $1 AND tenant_id = $2",
        document_id,
        str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return _row_to_response(row)


@router.patch("/{document_id}/extraction", response_model=DocumentDetailResponse)
async def update_extraction(
    document_id: str,
    patch: ExtractionPatch,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> DocumentDetailResponse:
    tenant_id = str(current_user.tenant_id)
    row = await pool.fetchrow(
        "SELECT * FROM documents WHERE id = $1 AND tenant_id = $2",
        document_id,
        tenant_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    existing: dict = {}
    if row["extraction"]:
        existing = (
            json.loads(row["extraction"])
            if isinstance(row["extraction"], str)
            else dict(row["extraction"])
        )

    existing.update(patch.model_dump(exclude_none=True))

    await pool.execute(
        "UPDATE documents SET extraction = $1, updated_at = $2 WHERE id = $3 AND tenant_id = $4",
        json.dumps(existing),
        datetime.utcnow(),
        document_id,
        tenant_id,
    )
    updated = await pool.fetchrow(
        "SELECT * FROM documents WHERE id = $1 AND tenant_id = $2",
        document_id,
        tenant_id,
    )
    return _row_to_response(updated)  # type: ignore[arg-type]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> None:
    result = await pool.execute(
        "DELETE FROM documents WHERE id = $1 AND tenant_id = $2",
        document_id,
        str(current_user.tenant_id),
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")


def _row_to_response(row: asyncpg.Record) -> DocumentDetailResponse:
    extraction = None
    if row["extraction"]:
        extraction = (
            json.loads(row["extraction"])
            if isinstance(row["extraction"], str)
            else dict(row["extraction"])
        )
    return DocumentDetailResponse(
        document_id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        filename=row["filename"],
        status=DocumentStatus(row["status"]),
        document_type=DocumentType(row["document_type"]),
        page_count=row.get("page_count"),
        size_bytes=row.get("size_bytes"),
        uploaded_at=row["uploaded_at"],
        updated_at=row["updated_at"],
        error_message=row.get("error_message"),
        extraction=extraction,
    )
