"""Elasticsearch indexer for local development.

When AZURE_SEARCH_ENDPOINT points to an Elasticsearch instance (local dev
via docker-compose) instead of Azure AI Search, this adapter is used
automatically.  It provides the same interface as the Azure AI Search
indexer (``ensure_index`` + ``index_chunks``).

Embeddings are still generated via Azure OpenAI; only the storage layer
differs.
"""

from __future__ import annotations

import json
from typing import Any

from allergo_shared.domain.entities import DocumentChunk
from allergo_shared.domain.exceptions import IndexingError
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)


def _is_elasticsearch(endpoint: str) -> bool:
    lower = endpoint.lower()
    return (
        ":9200" in lower
        or "elasticsearch" in lower
        or "localhost:9200" in lower
        or "127.0.0.1:9200" in lower
    )


async def ensure_es_index(endpoint: str, index_name: str) -> None:
    """Create the Elasticsearch index with a knn-vector mapping if it doesn't exist."""
    import aiohttp  # type: ignore[import]

    mapping: dict[str, Any] = {
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "tenant_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "filename": {"type": "keyword"},
                "page_number": {"type": "integer"},
                "text": {"type": "text"},
                # Dense vector for knn search (3072 dims = text-embedding-3-large)
                "embedding": {
                    "type": "dense_vector",
                    "dims": 3072,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        }
    }

    url = f"{endpoint.rstrip('/')}/{index_name}"
    try:
        async with aiohttp.ClientSession() as session:
            # Check if index exists
            async with session.head(url) as resp:
                if resp.status == 200:
                    logger.info("es_index_exists", index=index_name)
                    return
            # Create index
            async with session.put(
                url,
                data=json.dumps(mapping),
                headers={"Content-Type": "application/json"},
            ) as resp:
                body = await resp.text()
                if resp.status not in (200, 201):
                    raise IndexingError(
                        f"Failed to create ES index '{index_name}': {resp.status} {body}"
                    )
        logger.info("es_index_created", index=index_name)
    except IndexingError:
        raise
    except Exception as exc:
        raise IndexingError(f"Failed to ensure ES index '{index_name}': {exc}") from exc


async def index_chunks_es(
    endpoint: str,
    index_name: str,
    openai_client: Any,
    embedding_deployment: str,
    chunks: list[DocumentChunk],
    batch_size: int = 32,
) -> None:
    """Embed chunks with Azure OpenAI and bulk-index into Elasticsearch."""
    import aiohttp  # type: ignore[import]

    bulk_url = f"{endpoint.rstrip('/')}/_bulk"

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]

        try:
            response = await openai_client.embeddings.create(
                model=embedding_deployment,
                input=texts,
            )
            embeddings = [item.embedding for item in response.data]
        except Exception as exc:
            raise IndexingError(f"Embedding API call failed: {exc}") from exc

        # Build NDJSON bulk body
        lines: list[str] = []
        for chunk, embedding in zip(batch, embeddings, strict=True):
            action = {
                "index": {
                    "_index": index_name,
                    "_id": chunk.id,
                }
            }
            doc = {
                "document_id": chunk.document_id,
                "tenant_id": chunk.tenant_id,
                "chunk_index": chunk.chunk_index,
                "filename": chunk.metadata.get("filename", ""),
                "page_number": chunk.page_number,
                "text": chunk.text,
                "embedding": embedding,
            }
            lines.append(json.dumps(action))
            lines.append(json.dumps(doc))

        body = "\n".join(lines) + "\n"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    bulk_url,
                    data=body,
                    headers={"Content-Type": "application/x-ndjson"},
                ) as resp:
                    result = await resp.json()
                    if result.get("errors"):
                        # Log but do not abort — partial failures are acceptable
                        logger.warning(
                            "es_bulk_partial_errors",
                            index=index_name,
                            offset=i,
                            items_with_errors=[
                                it
                                for it in result.get("items", [])
                                if "error" in (it.get("index") or {})
                            ],
                        )
        except IndexingError:
            raise
        except Exception as exc:
            raise IndexingError(f"Failed to bulk-index chunks into ES: {exc}") from exc

        logger.info("es_chunks_indexed", count=len(batch), offset=i)
