"""DB status updater — writes document status transitions to PostgreSQL."""

from __future__ import annotations

from datetime import datetime

import asyncpg

from allergo_shared.domain.entities import ExtractionResult
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)


class DocumentStatusUpdater:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def mark_parsing(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="parsing")

    async def mark_parsed(
        self,
        document_id: str,
        tenant_id: str,
        raw_text_path: str,
        page_count: int,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = 'parsed', raw_text_path = $3, page_count = $4, updated_at = $5
                   WHERE id = $1 AND tenant_id = $2""",
                document_id, tenant_id, raw_text_path, page_count, datetime.utcnow(),
            )

    async def mark_extracting(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="extracting")

    async def mark_extracted(
        self, document_id: str, tenant_id: str, extraction: ExtractionResult
    ) -> None:
        from processing_service.infrastructure.llm_extractor import CONFIDENCE_REVIEW_THRESHOLD
        needs_review = (
            extraction.confidence_score < CONFIDENCE_REVIEW_THRESHOLD
            or extraction.approval_required
        )
        review_status = "pending_review" if needs_review else "not_required"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = 'extracted',
                       extraction = $3,
                       needs_review = $4,
                       review_status = $5,
                       updated_at = $6
                   WHERE id = $1 AND tenant_id = $2""",
                document_id,
                tenant_id,
                extraction.model_dump_json(),
                needs_review,
                review_status,
                datetime.utcnow(),
            )

    async def mark_indexing(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="indexing")

    async def mark_ready(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="ready")

    async def mark_failed(self, document_id: str, tenant_id: str, error: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = 'failed', error_message = $3, updated_at = $4
                   WHERE id = $1 AND tenant_id = $2""",
                document_id, tenant_id, error, datetime.utcnow(),
            )

    async def _update(self, document_id: str, tenant_id: str, status: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = $3, updated_at = $4
                   WHERE id = $1 AND tenant_id = $2""",
                document_id, tenant_id, status, datetime.utcnow(),
            )
