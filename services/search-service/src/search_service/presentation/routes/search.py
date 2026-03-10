"""Search API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from allergo_shared.infrastructure.auth import AuthenticatedUser
from search_service.application.search import SearchHit, SearchUseCase
from search_service.presentation.dependencies import get_current_user, get_search_use_case

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    top: int = 10
    document_ids: list[str] | None = None


class SearchHitResponse(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    highlights: list[str]


class SearchResultResponse(BaseModel):
    query: str
    hits: list[SearchHitResponse]
    total: int
    search_mode: str


def _map_hit(h: SearchHit) -> SearchHitResponse:
    return SearchHitResponse(
        chunk_id=h.id,
        document_id=h.document_id,
        text=h.text,
        score=h.score,
        highlights=h.highlights,
    )


@router.post("/", response_model=SearchResultResponse, summary="Hybrid search over documents")
async def search(
    body: SearchRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[SearchUseCase, Depends(get_search_use_case)],
) -> SearchResultResponse:
    result = await use_case.hybrid_search(
        query=body.query,
        tenant_id=str(current_user.tenant_id),
        top=min(body.top, 50),
        document_ids=body.document_ids,
    )
    return SearchResultResponse(
        query=result.query,
        hits=[_map_hit(h) for h in result.hits],
        total=result.total,
        search_mode=result.search_mode,
    )
