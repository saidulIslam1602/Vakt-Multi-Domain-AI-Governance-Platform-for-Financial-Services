"""PostgreSQL document repository — asyncpg-backed implementation."""

from __future__ import annotations

import json
from datetime import datetime

import asyncpg

from allergo_shared.domain.entities import Document, ExtractionResult
from allergo_shared.domain.enums import DocumentStatus, DocumentType
from allergo_shared.domain.value_objects import DocumentId, TenantId

from ingest_service.domain.interfaces.document_repository import DocumentRepository

_INSERT_SQL = """
INSERT INTO documents (
    id, tenant_id, filename, document_type, status,
    blob_path, raw_text_path, error_message,
    uploaded_at, updated_at, page_count, size_bytes, content_type
) VALUES (
    $1, $2, $3, $4, $5,
    $6, $7, $8,
    $9, $10, $11, $12, $13
)
ON CONFLICT (id) DO UPDATE SET
    status = EXCLUDED.status,
    raw_text_path = EXCLUDED.raw_text_path,
    error_message = EXCLUDED.error_message,
    updated_at = EXCLUDED.updated_at,
    page_count = EXCLUDED.page_count
"""

_SELECT_BY_ID_SQL = """
SELECT * FROM documents WHERE id = $1 AND tenant_id = $2
"""

_SELECT_BY_TENANT_SQL = """
SELECT * FROM documents WHERE tenant_id = $1 ORDER BY uploaded_at DESC LIMIT $2 OFFSET $3
"""


class PostgresDocumentRepository(DocumentRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, document: Document) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_SQL,
                str(document.id),
                str(document.tenant_id),
                document.filename,
                str(document.document_type),
                str(document.status),
                document.blob_path,
                document.raw_text_path,
                document.error_message,
                document.uploaded_at,
                document.updated_at,
                document.page_count,
                document.size_bytes,
                document.content_type,
            )

    async def get_by_id(self, document_id: str, tenant_id: str) -> Document | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_BY_ID_SQL, document_id, tenant_id)
        if row is None:
            return None
        return _row_to_document(dict(row))

    async def list_by_tenant(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SELECT_BY_TENANT_SQL, tenant_id, limit, offset)
        return [_row_to_document(dict(r)) for r in rows]


def _row_to_document(row: dict) -> Document:
    return Document(
        id=DocumentId(value=row["id"]),
        tenant_id=TenantId(value=row["tenant_id"]),
        filename=row["filename"],
        document_type=DocumentType(row["document_type"]),
        status=DocumentStatus(row["status"]),
        blob_path=row["blob_path"],
        raw_text_path=row.get("raw_text_path"),
        error_message=row.get("error_message"),
        uploaded_at=row["uploaded_at"],
        updated_at=row["updated_at"],
        page_count=row.get("page_count"),
        size_bytes=row.get("size_bytes"),
        content_type=row.get("content_type"),
    )
