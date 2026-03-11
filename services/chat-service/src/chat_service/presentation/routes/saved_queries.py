"""Saved chat queries — CFO can bookmark frequently-used questions."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from allergo_shared.infrastructure.auth import AuthenticatedUser
from chat_service.presentation.dependencies import get_current_user

router = APIRouter(prefix="/chat/saved", tags=["saved-queries"])


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool  # type: ignore[no-any-return]


class SavedQueryCreate(BaseModel):
    name: str = Field(max_length=256, description="Short label shown in the UI button.")
    question: str = Field(min_length=1, max_length=2000)


class SavedQueryResponse(BaseModel):
    query_id: str
    name: str
    question: str
    created_at: datetime


@router.post("/", response_model=SavedQueryResponse, status_code=status.HTTP_201_CREATED)
async def save_query(
    body: SavedQueryCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    request: Request,
) -> SavedQueryResponse:
    """Bookmark a question so it appears as a one-click button in the chat UI."""
    pool = _pool(request)
    row = await pool.fetchrow(
        """INSERT INTO saved_queries (tenant_id, name, question)
           VALUES ($1, $2, $3)
           RETURNING id, name, question, created_at""",
        str(current_user.tenant_id),
        body.name,
        body.question,
    )
    return _map(row)


@router.get("/", response_model=list[SavedQueryResponse])
async def list_saved_queries(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    request: Request,
) -> list[SavedQueryResponse]:
    pool = _pool(request)
    rows = await pool.fetch(
        """SELECT id, name, question, created_at
           FROM saved_queries
           WHERE tenant_id = $1
           ORDER BY created_at DESC""",
        str(current_user.tenant_id),
    )
    return [_map(r) for r in rows]


@router.delete("/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_query(
    query_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    request: Request,
) -> None:
    pool = _pool(request)
    result = await pool.execute(
        "DELETE FROM saved_queries WHERE id = $1 AND tenant_id = $2",
        query_id,
        str(current_user.tenant_id),
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found.")


def _map(row: asyncpg.Record) -> SavedQueryResponse:
    return SavedQueryResponse(
        query_id=str(row["id"]),
        name=row["name"],
        question=row["question"],
        created_at=row["created_at"],
    )
