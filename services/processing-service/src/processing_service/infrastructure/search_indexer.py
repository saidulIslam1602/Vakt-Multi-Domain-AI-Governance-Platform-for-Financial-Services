"""Azure AI Search indexer — uploads document chunks with embeddings."""

from __future__ import annotations


from typing import Any

from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    SearchableField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AsyncAzureOpenAI

from allergo_shared.domain.entities import DocumentChunk
from allergo_shared.domain.exceptions import IndexingError
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)

EMBEDDING_DIMENSIONS = 3072  # text-embedding-3-large


async def ensure_index(index_client: SearchIndexClient, index_name: str) -> None:
    """Create the Azure AI Search index if it does not exist."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="document_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="tenant_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
        SimpleField(name="filename", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True),
        SearchableField(name="text", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="hnsw-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
        profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-algo")],
    )
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="text")]
                ),
            )
        ]
    )
    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )
    try:
        await index_client.create_or_update_index(index)
        logger.info("search_index_ensured", index=index_name)
    except Exception as exc:
        raise IndexingError(f"Failed to create/update search index: {exc}") from exc


async def index_chunks(
    search_client: SearchClient,
    openai_client: AsyncAzureOpenAI,
    embedding_deployment: str,
    chunks: list[DocumentChunk],
    batch_size: int = 32,
) -> None:
    """Embed and upload chunks in batches to Azure AI Search."""
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

        documents: list[dict[str, Any]] = []
        for chunk, embedding in zip(batch, embeddings, strict=True):
            documents.append(
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "tenant_id": chunk.tenant_id,
                    "chunk_index": chunk.chunk_index,
                    "filename": chunk.metadata.get("filename", ""),
                    "page_number": chunk.page_number,
                    "text": chunk.text,
                    "embedding": embedding,
                }
            )

        try:
            await search_client.upload_documents(documents=documents)
        except Exception as exc:
            raise IndexingError(f"Failed to upload documents to search index: {exc}") from exc

        logger.info("chunks_indexed", count=len(batch), offset=i)
