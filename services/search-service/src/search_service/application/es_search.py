"""Elasticsearch-backed search use case for local development.

Provides the same interface as :class:`SearchUseCase` but queries
Elasticsearch instead of Azure AI Search.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

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


class ElasticsearchSearchUseCase:
    """Search use case that runs against a local Elasticsearch instance."""

    def __init__(
        self,
        endpoint: str,
        index_name: str,
        openai_client: AsyncAzureOpenAI,
        embedding_deployment: str,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._index_name = index_name
        self._openai_client = openai_client
        self._embedding_deployment = embedding_deployment

    async def hybrid_search(
        self,
        query: str,
        tenant_id: str,
        top: int = 10,
        document_ids: list[str] | None = None,
    ) -> SearchResponse:
        """Hybrid search using Elasticsearch knn + full-text BM25."""
        import aiohttp

        embedding = await self._embed(query)

        # Build Elasticsearch query combining knn vector search + BM25 text match
        must_filters: list[dict[str, Any]] = [
            {"term": {"tenant_id": tenant_id}},
        ]
        if document_ids:
            must_filters.append({"terms": {"document_id": document_ids}})

        # ES 8.x knn query with filter
        body: dict[str, Any] = {
            "size": top,
            "query": {
                "bool": {
                    "must": [
                        {"multi_match": {"query": query, "fields": ["text"]}}
                    ],
                    "filter": must_filters,
                }
            },
            "knn": {
                "field": "embedding",
                "query_vector": embedding,
                "k": top,
                "num_candidates": max(top * 5, 100),
                "filter": must_filters,
            },
            "highlight": {
                "fields": {"text": {}}
            },
        }

        url = f"{self._endpoint}/{self._index_name}/_search"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=json.dumps(body),
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    result = await resp.json()
        except Exception as exc:
            from allergo_shared.domain.exceptions import IndexingError
            raise IndexingError(f"Elasticsearch search failed: {exc}") from exc

        hits: list[SearchHit] = []
        for hit in result.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            hl = hit.get("highlight", {}).get("text", [])
            hits.append(
                SearchHit(
                    id=hit["_id"],
                    document_id=src.get("document_id", ""),
                    tenant_id=src.get("tenant_id", ""),
                    chunk_index=src.get("chunk_index", 0),
                    text=src.get("text", ""),
                    score=hit.get("_score", 0.0),
                    highlights=hl,
                )
            )

        total = result.get("hits", {}).get("total", {}).get("value", len(hits))
        logger.info("es_search_complete", query=query, hits=len(hits), tenant_id=tenant_id)
        return SearchResponse(query=query, hits=hits, total=total, search_mode="hybrid_es")

    async def _embed(self, text: str) -> list[float]:
        response = await self._openai_client.embeddings.create(
            model=self._embedding_deployment,
            input=[text],
        )
        return response.data[0].embedding
