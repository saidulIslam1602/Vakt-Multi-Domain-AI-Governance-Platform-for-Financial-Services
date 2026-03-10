"""Text chunker — splits text into overlapping token-bounded chunks for embedding."""

from __future__ import annotations

import tiktoken

from allergo_shared.domain.entities import DocumentChunk


def chunk_text(
    text: str,
    document_id: str,
    tenant_id: str,
    chunk_size: int = 512,
    overlap: int = 64,
    encoding_name: str = "cl100k_base",
) -> list[DocumentChunk]:
    """Split text into overlapping chunks of at most `chunk_size` tokens."""
    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)

    if not tokens:
        return []

    chunks: list[DocumentChunk] = []
    step = max(1, chunk_size - overlap)
    chunk_index = 0

    for start in range(0, len(tokens), step):
        chunk_tokens = tokens[start : start + chunk_size]
        chunk_text_str = enc.decode(chunk_tokens).strip()
        if not chunk_text_str:
            continue
        chunks.append(
            DocumentChunk(
                id=f"{document_id}_chunk_{chunk_index}",
                document_id=document_id,
                tenant_id=tenant_id,
                chunk_index=chunk_index,
                text=chunk_text_str,
            )
        )
        chunk_index += 1

    return chunks
