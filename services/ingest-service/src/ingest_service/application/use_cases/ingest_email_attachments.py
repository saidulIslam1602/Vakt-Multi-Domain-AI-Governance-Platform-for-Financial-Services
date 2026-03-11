"""Use case: ingest a single email attachment into the document pipeline.

Called by EmailPoller for every valid attachment found in an incoming email.
Responsibilities:
  1. Deduplication check — skip if (tenant_id, message_id, filename) already
     exists in email_ingest_log.
  2. Delegate to UploadDocumentUseCase — reuses the exact same validation,
     blob upload, DB insert, and Service Bus publish logic as the HTTP upload.
  3. Write an email_ingest_log row — success or failure, always auditable.

This use case deliberately owns NO IMAP logic — it only knows about the
already-extracted bytes and metadata. This keeps it fully testable without
a real mailbox.
"""

from __future__ import annotations

import asyncpg

from allergo_shared.domain.exceptions import ValidationError
from allergo_shared.infrastructure.logging import get_logger

from ingest_service.application.use_cases.upload_document import UploadDocumentUseCase

logger = get_logger(__name__)


class IngestEmailAttachmentsUseCase:
    """Orchestrates email attachment → upload pipeline with deduplication."""

    def __init__(self, upload_use_case: UploadDocumentUseCase) -> None:
        self._upload = upload_use_case

    async def ingest_one(
        self,
        *,
        message_id: str,
        attachment_filename: str,
        content_type: str,
        data: bytes,
        sender: str,
        subject: str,
        tenant_id: str,
        pool: asyncpg.Pool,
    ) -> bool:
        """Ingest one attachment. Returns True if successfully queued, False otherwise."""

        # ── 1. Deduplication check ────────────────────────────────────────────
        async with pool.acquire() as conn:
            already_done = await conn.fetchval(
                """SELECT 1 FROM email_ingest_log
                   WHERE tenant_id           = $1
                     AND message_id          = $2
                     AND attachment_filename = $3""",
                tenant_id,
                message_id,
                attachment_filename,
            )

        if already_done:
            logger.debug(
                "email_attachment_already_ingested",
                message_id=message_id,
                filename=attachment_filename,
            )
            return False

        # ── 2. Upload through the standard pipeline ───────────────────────────
        document_id: str | None = None
        error_msg: str | None = None

        try:
            document = await self._upload.execute(
                filename=attachment_filename,
                data=data,
                content_type=content_type,
                tenant_id=tenant_id,
            )
            document_id = str(document.id)
            logger.info(
                "email_attachment_ingested",
                document_id=document_id,
                filename=attachment_filename,
                sender=sender,
                subject=subject,
                size_bytes=len(data),
            )
        except ValidationError as exc:
            error_msg = exc.message
            logger.warning(
                "email_attachment_validation_failed",
                filename=attachment_filename,
                message_id=message_id,
                error=exc.message,
            )
        except Exception as exc:
            error_msg = str(exc)
            logger.exception(
                "email_attachment_ingest_failed",
                filename=attachment_filename,
                message_id=message_id,
            )

        # ── 3. Always write audit log (success or failure) ────────────────────
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO email_ingest_log
                     (tenant_id, message_id, attachment_filename,
                      document_id, sender, subject, error)
                   VALUES ($1, $2, $3, $4::uuid, $5, $6, $7)
                   ON CONFLICT (tenant_id, message_id, attachment_filename)
                   DO NOTHING""",
                tenant_id,
                message_id,
                attachment_filename,
                document_id,   # None → NULL if upload failed
                sender[:512] if sender else None,
                subject[:512] if subject else None,
                error_msg,
            )

        return document_id is not None
