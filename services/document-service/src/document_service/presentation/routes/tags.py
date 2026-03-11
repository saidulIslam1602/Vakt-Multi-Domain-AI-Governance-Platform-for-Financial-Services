"""Document tagging routes — add/replace/remove free-form labels on documents."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/documents", tags=["tags"])


class TagsPayload(BaseModel):
    tags: list[str] = Field(description="Full replacement list of tags for this document.")


class TagsResponse(BaseModel):
    document_id: str
    tags: list[str]


@router.put(
    "/{document_id}/tags",
    response_model=TagsResponse,
    summary="Replace all tags on a document",
)
async def set_tags(
    document_id: str,
    body: TagsPayload,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> TagsResponse:
    """Replace the entire tag list for a document.  Pass an empty list to clear all tags."""
    # Normalise: lowercase, strip whitespace, deduplicate
    clean_tags = list({t.strip().lower() for t in body.tags if t.strip()})
    result = await pool.execute(
        """UPDATE documents
           SET tags = $3::text[], updated_at = NOW()
           WHERE id = $1 AND tenant_id = $2""",
        document_id,
        str(current_user.tenant_id),
        clean_tags,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return TagsResponse(document_id=document_id, tags=clean_tags)


@router.get(
    "/{document_id}/tags",
    response_model=TagsResponse,
    summary="Get tags for a document",
)
async def get_tags(
    document_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> TagsResponse:
    row = await pool.fetchrow(
        "SELECT id, tags FROM documents WHERE id = $1 AND tenant_id = $2",
        document_id,
        str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return TagsResponse(document_id=document_id, tags=list(row["tags"] or []))
