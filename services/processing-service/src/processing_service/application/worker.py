"""Processing worker — orchestrates parse → extract → index pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from allergo_shared.domain.entities import DocumentChunk
from allergo_shared.domain.enums import DocumentType, JobEventType
from allergo_shared.domain.exceptions import AllergoError
from allergo_shared.domain.interfaces.queue import MessageQueuePort, QueueMessage
from allergo_shared.domain.interfaces.storage import BlobStoragePort
from allergo_shared.infrastructure.logging import get_logger

from processing_service.infrastructure.chunker import chunk_text
from processing_service.infrastructure.config import Settings
from processing_service.infrastructure.db_updater import DocumentStatusUpdater
from processing_service.infrastructure.llm_extractor import LLMExtractor
from processing_service.infrastructure.parser import ParseResult, parse_document

logger = get_logger(__name__)

RAW_TEXT_CONTAINER = "raw-text"
RAW_DOCUMENTS_CONTAINER = "raw-documents"


class ProcessingWorker:
    """Subscribes to Service Bus, processes each document through the full pipeline."""

    def __init__(
        self,
        queue: MessageQueuePort,
        storage: BlobStoragePort,
        extractor: LLMExtractor,
        indexer_fn: Callable[[list[DocumentChunk]], Coroutine[Any, Any, None]],
        db_updater: DocumentStatusUpdater,
        settings: Settings,
    ) -> None:
        self._queue = queue
        self._storage = storage
        self._extractor = extractor
        self._indexer_fn = indexer_fn
        self._db_updater = db_updater
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=settings.worker_concurrency)

    async def run(self) -> None:
        logger.info("processing_worker_started")
        # subscribe() returns an AsyncIterator directly — do NOT await it.
        async for message in self._queue.subscribe(
            self._settings.servicebus_topic_document_events,
            self._settings.servicebus_subscription_processing,
        ):
            asyncio.create_task(self._handle_message(message))

    async def _handle_message(self, message: QueueMessage) -> None:
        event = message.body
        event_type = event.get("event_type")

        if event_type != JobEventType.DOCUMENT_UPLOADED:
            await message.complete()
            return

        document_id: str = event["document_id"]
        tenant_id: str = event["tenant_id"]
        blob_path: str = event["blob_path"]
        content_type: str = event.get("content_type", "application/pdf")
        filename: str = event.get("filename", "unknown")

        logger.info("processing_started", document_id=document_id, tenant_id=tenant_id)

        try:
            await self._process(
                document_id=document_id,
                tenant_id=tenant_id,
                blob_path=blob_path,
                content_type=content_type,
                filename=filename,
            )
            await message.complete()
        except AllergoError as exc:
            logger.error("processing_failed", document_id=document_id, error=exc.message)
            await self._db_updater.mark_failed(document_id, tenant_id, exc.message)
            if message.delivery_count >= 3:
                await message.dead_letter(reason=exc.message)
            else:
                await message.abandon()
        except Exception as exc:
            logger.error(
                "unexpected_processing_error",
                document_id=document_id,
                error=str(exc),
                exc_info=True,
            )
            await self._db_updater.mark_failed(document_id, tenant_id, str(exc))
            await message.dead_letter(reason=str(exc))

    async def _process(
        self,
        document_id: str,
        tenant_id: str,
        blob_path: str,
        content_type: str,
        filename: str,
    ) -> None:
        # 1. Download from blob
        await self._db_updater.mark_parsing(document_id, tenant_id)
        raw_data = await self._storage.download(RAW_DOCUMENTS_CONTAINER, blob_path)

        # 2. Parse (synchronous CPU-bound — run in thread pool)
        doc_type = _content_type_to_doc_type(content_type)
        loop = asyncio.get_running_loop()
        parse_result: ParseResult = await loop.run_in_executor(
            self._executor,
            parse_document,
            raw_data,
            doc_type,
            filename,
        )

        # 3. Store raw text in blob
        text_blob_name = f"{tenant_id}/{document_id}/raw_text.txt"
        await self._storage.upload(
            RAW_TEXT_CONTAINER,
            text_blob_name,
            parse_result.text.encode("utf-8"),
            "text/plain",
        )
        await self._db_updater.mark_parsed(
            document_id, tenant_id, text_blob_name, parse_result.page_count
        )

        # 4. LLM extraction
        await self._db_updater.mark_extracting(document_id, tenant_id)
        extraction = await self._extractor.extract(parse_result.text, document_id)
        await self._db_updater.mark_extracted(document_id, tenant_id, extraction)

        # 5. Chunk + embed + index
        await self._db_updater.mark_indexing(document_id, tenant_id)
        chunks = chunk_text(
            parse_result.text,
            document_id,
            tenant_id,
            self._settings.chunk_size_tokens,
            self._settings.chunk_overlap_tokens,
            filename=filename,
        )
        await self._indexer_fn(chunks)
        await self._db_updater.mark_ready(document_id, tenant_id)

        logger.info(
            "processing_complete",
            document_id=document_id,
            chunks=len(chunks),
            pages=parse_result.page_count,
        )


def _content_type_to_doc_type(content_type: str) -> DocumentType:
    mapping: dict[str, DocumentType] = {
        "application/pdf": DocumentType.PDF,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.DOCX,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentType.XLSX,
        "text/plain": DocumentType.TXT,
        "text/html": DocumentType.HTML,
        "image/png": DocumentType.IMAGE,
        "image/jpeg": DocumentType.IMAGE,
        "image/tiff": DocumentType.IMAGE,
    }
    return mapping.get(content_type, DocumentType.UNKNOWN)
