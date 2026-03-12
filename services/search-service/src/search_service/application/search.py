"""Search use cases — full-text, semantic, and hybrid search."""

from __future__ import annotations

from dataclasses import dataclass, field

from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AsyncAzureOpenAI

from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchHit:
    id: str
    document_id: str
    tenant_id: str
    chunk_index: int
    text: str
    score: float
    highlights: list[str] = field(default_factory=list)


@dataclass
class SearchResponse:
    query: str
    hits: list[SearchHit]
    total: int
    search_mode: str


class SearchUseCase:
    def __init__(
        self,
        search_client: SearchClient,
        openai_client: AsyncAzureOpenAI,
        embedding_deployment: str,
    ) -> None:
        self._search_client = search_client
        self._openai_client = openai_client
        self._embedding_deployment = embedding_deployment

    async def hybrid_search(
        self,
        query: str,
        tenant_id: str,
        top: int = 10,
        document_ids: list[str] | None = None,
    ) -> SearchResponse:
        """Hybrid search: full-text (BM25) + vector (semantic) with RRF fusion."""
        embedding = await self._embed(query)

        vector_query = VectorizedQuery(
            vector=embedding,
            k_nearest_neighbors=top,
            fields="embedding",
        )

        filter_expr = f"tenant_id eq '{tenant_id}'"
        if document_ids:
            ids_filter = " or ".join(f"document_id eq '{d}'" for d in document_ids)
            filter_expr = f"({filter_expr}) and ({ids_filter})"

        results = await self._search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=filter_expr,
            top=top,
            highlight_fields="text",
        )

        hits: list[SearchHit] = []
        async for result in results:
            highlights: list[str] = []
            if result.get("@search.highlights"):
                highlights = result["@search.highlights"].get("text", [])
            hits.append(
                SearchHit(
                    id=result["id"],
                    document_id=result["document_id"],
                    tenant_id=result["tenant_id"],
                    chunk_index=result["chunk_index"],
                    text=result["text"],
                    score=result["@search.score"],
                    highlights=highlights,
                )
            )

        logger.info("search_complete", query=query, hits=len(hits), tenant_id=tenant_id)
        return SearchResponse(query=query, hits=hits, total=len(hits), search_mode="hybrid")

    async def _embed(self, text: str) -> list[float]:
        response = await self._openai_client.embeddings.create(
            model=self._embedding_deployment,
            input=[text],
        )
        return response.data[0].embedding
