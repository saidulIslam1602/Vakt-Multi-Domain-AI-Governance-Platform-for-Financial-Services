"""Use case: upload a document, store in blob, publish job to Service Bus."""

from __future__ import annotations

import mimetypes
from datetime import datetime

from allergo_shared.domain.entities import Document
from allergo_shared.domain.enums import DocumentStatus, DocumentType, JobEventType
from allergo_shared.domain.exceptions import ValidationError
from allergo_shared.domain.interfaces.queue import MessageQueuePort
from allergo_shared.domain.interfaces.storage import BlobStoragePort
from allergo_shared.domain.value_objects import DocumentId, TenantId
from allergo_shared.infrastructure.logging import get_logger

from ingest_service.domain.interfaces.document_repository import DocumentRepository

logger = get_logger(__name__)

ALLOWED_CONTENT_TYPES = {
    "application/pdf": DocumentType.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.DOCX,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentType.XLSX,
    "text/plain": DocumentType.TXT,
    "text/html": DocumentType.HTML,
    "image/png": DocumentType.IMAGE,
    "image/jpeg": DocumentType.IMAGE,
    "image/tiff": DocumentType.IMAGE,
}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
BLOB_CONTAINER = "raw-documents"
TOPIC_NAME = "document-events"


class UploadDocumentUseCase:
    """Validates, stores, and enqueues a new document for processing."""

    def __init__(
        self,
        storage: BlobStoragePort,
        queue: MessageQueuePort,
        repository: DocumentRepository,
    ) -> None:
        self._storage = storage
        self._queue = queue
        self._repository = repository

    async def execute(
        self,
        *,
        filename: str,
        data: bytes,
        content_type: str | None,
        tenant_id: str,
    ) -> Document:
        resolved_type = self._resolve_content_type(filename, content_type)
        if resolved_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError(
                f"Unsupported file type '{resolved_type}'. "
                f"Allowed: {', '.join(ALLOWED_CONTENT_TYPES.keys())}"
            )
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"File size {len(data)} bytes exceeds maximum of {MAX_FILE_SIZE_BYTES} bytes."
            )

        document_id = DocumentId.generate()
        blob_name = f"{tenant_id}/{document_id}/{filename}"
        now = datetime.utcnow()

        document = Document(
            id=document_id,
            tenant_id=TenantId(value=tenant_id),
            filename=filename,
            document_type=ALLOWED_CONTENT_TYPES[resolved_type],
            status=DocumentStatus.UPLOADED,
            blob_path=blob_name,
            uploaded_at=now,
            updated_at=now,
            size_bytes=len(data),
            content_type=resolved_type,
        )

        await self._storage.upload(BLOB_CONTAINER, blob_name, data, resolved_type)
        await self._repository.save(document)
        await self._queue.publish(
            TOPIC_NAME,
            {
                "event_type": JobEventType.DOCUMENT_UPLOADED,
                "document_id": str(document_id),
                "tenant_id": tenant_id,
                "blob_path": blob_name,
                "filename": filename,
                "content_type": resolved_type,
                "timestamp": now.isoformat(),
            },
            correlation_id=str(document_id),
        )

        logger.info(
            "document_uploaded",
            document_id=str(document_id),
            tenant_id=tenant_id,
            filename=filename,
            size_bytes=len(data),
        )
        return document

    @staticmethod
    def _resolve_content_type(filename: str, provided: str | None) -> str:
        if provided and provided != "application/octet-stream":
            return provided
        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"
