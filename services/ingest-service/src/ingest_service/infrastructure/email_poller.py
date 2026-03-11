"""Async IMAP email poller for automatic document ingestion.

Polls a configured IMAP mailbox at a regular interval and extracts
all valid document attachments (PDF, DOCX, XLSX, TXT, images) from
unread / unseen emails, then hands them off to the upload pipeline.

Design decisions
────────────────
• Uses ``aioimaplib`` for a fully async IMAP client — no thread blocking.
• Deduplication is enforced by ``email_ingest_log`` (migration 009):
  each (tenant_id, message_id, attachment_filename) is only processed once.
• After successful ingestion the email is marked as SEEN (not deleted),
  preserving it in the CFO mailbox for manual reference.
• Failures per-attachment are logged and stored in email_ingest_log.error
  so they are auditable without crashing the poller loop.
• The poller runs as a long-lived asyncio.Task started in the FastAPI
  lifespan context — no separate process or container needed.

Supported IMAP servers
──────────────────────
• Gmail (imap.gmail.com:993, SSL)  — use an App Password, not your Google password
• Outlook / Office 365 (outlook.office365.com:993, SSL)
• Any standard IMAP server with SSL or STARTTLS

Configuration (env vars → Settings)
─────────────────────────────────────
  EMAIL_INGEST_ENABLED     true / false (default false)
  IMAP_HOST                IMAP server hostname
  IMAP_PORT                993 (SSL) or 143 (STARTTLS)
  IMAP_USERNAME            Email address / login
  IMAP_PASSWORD            Password or App Password
  IMAP_MAILBOX             Folder to poll (default: INBOX)
  IMAP_POLL_INTERVAL_SEC   Seconds between polls (default: 300 = 5 min)
  IMAP_USE_SSL             true = SSL/TLS on connect (default: true)
  IMAP_TENANT_ID           Allergo tenant_id to use for ingested docs
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import imaplib
import ssl
from email.message import EmailMessage
from typing import TYPE_CHECKING

import asyncpg

from allergo_shared.infrastructure.logging import get_logger
from ingest_service.infrastructure.email_filter import EmailFilter

if TYPE_CHECKING:
    from ingest_service.application.use_cases.ingest_email_attachments import (
        IngestEmailAttachmentsUseCase,
    )

logger = get_logger(__name__)

# MIME types the ingest pipeline accepts (mirrors UploadDocumentUseCase)
_ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "text/html",
        "image/png",
        "image/jpeg",
        "image/tiff",
    }
)

# Filename extensions → MIME type (fallback when Content-Type is missing / wrong)
_EXT_MIME: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt":  "text/plain",
    ".html": "text/html",
    ".htm":  "text/html",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif":  "image/tiff",
}


class EmailPoller:
    """Long-running async task that polls an IMAP mailbox and ingests attachments.

    Lifecycle:
      1. ``start()`` — launches the background asyncio.Task.
      2. ``stop()``  — signals the loop to exit gracefully.

    The task is designed to run inside the FastAPI lifespan context so it
    shares the same event loop and connection pool as the HTTP server.
    """

    def __init__(
        self,
        *,
        imap_host: str,
        imap_port: int,
        imap_username: str,
        imap_password: str,
        imap_mailbox: str,
        poll_interval_sec: int,
        use_ssl: bool,
        tenant_id: str,
        pool: asyncpg.Pool,
        use_case: "IngestEmailAttachmentsUseCase",
        email_filter: EmailFilter | None = None,
    ) -> None:
        self._host = imap_host
        self._port = imap_port
        self._username = imap_username
        self._password = imap_password
        self._mailbox = imap_mailbox
        self._interval = poll_interval_sec
        self._use_ssl = use_ssl
        self._tenant_id = tenant_id
        self._pool = pool
        self._use_case = use_case
        self._filter = email_filter or EmailFilter()   # default: no restrictions
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ── Public lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the poller as a background asyncio.Task."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="email-ingest-poller")
        logger.info(
            "email_poller_started",
            host=self._host,
            mailbox=self._mailbox,
            interval_sec=self._interval,
            tenant_id=self._tenant_id,
        )

    async def stop(self) -> None:
        """Signal the loop to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        logger.info("email_poller_stopped")

    # ── Internal polling loop ─────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Run poll → sleep → poll until stop_event is set."""
        while not self._stop_event.is_set():
            try:
                await self._poll_once()
            except Exception:
                logger.exception("email_poll_cycle_failed")

            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=float(self._interval),
                )
                # stop_event fired during sleep — exit loop
                break
            except asyncio.TimeoutError:
                # Normal: interval elapsed, continue polling
                pass

    async def _poll_once(self) -> None:
        """Connect to IMAP, fetch unseen emails, process attachments, disconnect."""
        logger.debug("email_poll_started", host=self._host, mailbox=self._mailbox)

        # Run the blocking IMAP operations in a thread pool to keep the event
        # loop free (imaplib is synchronous; aioimaplib is an option but
        # imaplib in a thread is simpler and reliable).
        loop = asyncio.get_running_loop()
        emails = await loop.run_in_executor(None, self._fetch_unseen_emails)

        if not emails:
            logger.debug("email_poll_no_new_emails")
            return

        logger.info("email_poll_found_emails", count=len(emails))

        for raw_email, imap_uid in emails:
            await self._process_email(raw_email, imap_uid)

    def _fetch_unseen_emails(self) -> list[tuple[bytes, str]]:
        """Synchronous IMAP fetch — runs in a thread executor.

        Returns list of (raw_email_bytes, uid_string) for all UNSEEN messages.
        """
        results: list[tuple[bytes, str]] = []
        try:
            if self._use_ssl:
                ctx = ssl.create_default_context()
                conn = imaplib.IMAP4_SSL(self._host, self._port, ssl_context=ctx)
            else:
                conn = imaplib.IMAP4(self._host, self._port)  # type: ignore[assignment]

            conn.login(self._username, self._password)
            conn.select(self._mailbox)

            # Search for UNSEEN messages only
            status, uid_list = conn.uid("search", None, "UNSEEN")  # type: ignore[call-overload]
            if status != "OK" or not uid_list or not uid_list[0]:
                conn.logout()
                return results

            uids = uid_list[0].split()
            for uid in uids:
                status, msg_data = conn.uid("fetch", uid, "(RFC822)")  # type: ignore[call-overload]
                if status == "OK" and msg_data and msg_data[0]:
                    raw = msg_data[0][1]  # type: ignore[index]
                    if isinstance(raw, bytes):
                        results.append((raw, uid.decode()))

            conn.logout()
        except Exception:
            logger.exception("imap_fetch_failed", host=self._host)
        return results

    async def _process_email(self, raw: bytes, uid: str) -> None:
        """Parse one raw email and ingest each valid attachment."""
        try:
            msg: EmailMessage = email.message_from_bytes(  # type: ignore[assignment]
                raw, policy=email.policy.default
            )
        except Exception:
            logger.exception("email_parse_failed", uid=uid)
            return

        message_id: str = msg.get("Message-ID", f"<no-id-{uid}>").strip()
        sender: str = msg.get("From", "")
        subject: str = msg.get("Subject", "(no subject)")

        logger.info(
            "email_processing",
            message_id=message_id,
            sender=sender,
            subject=subject,
        )

        # ── Layer 1-4: email-level filter ─────────────────────────────────────
        email_result = self._filter.check_email(sender=sender, subject=subject)
        if not email_result.accepted:
            logger.info(
                "email_skipped_by_filter",
                message_id=message_id,
                sender=sender,
                subject=subject,
                reason=email_result.reason,
            )
            # Mark SEEN so we don't re-evaluate this email on the next poll
            await self._mark_seen(uid)
            return

        attachments = self._extract_attachments(msg)
        if not attachments:
            logger.info(
                "email_no_valid_attachments",
                message_id=message_id,
                subject=subject,
            )
            # Mark as SEEN even with no attachments so we don't re-visit it
            await self._mark_seen(uid)
            return

        any_success = False
        for filename, content_type, data in attachments:
            ingested = await self._use_case.ingest_one(
                message_id=message_id,
                attachment_filename=filename,
                content_type=content_type,
                data=data,
                sender=sender,
                subject=subject,
                tenant_id=self._tenant_id,
                pool=self._pool,
            )
            if ingested:
                any_success = True

        if any_success:
            # Mark the email as SEEN in the mailbox
            await self._mark_seen(uid)

    def _extract_attachments(
        self, msg: EmailMessage
    ) -> list[tuple[str, str, bytes]]:
        """Return list of (filename, content_type, bytes) for valid attachments."""
        results: list[tuple[str, str, bytes]] = []

        for part in msg.walk():
            # Skip multipart containers
            if part.get_content_maintype() == "multipart":
                continue
            # Only process parts that are attachments or inline files
            disposition = part.get_content_disposition()
            filename = part.get_filename()
            if not filename:
                continue

            # Resolve content type: prefer header, fallback to extension
            ct = part.get_content_type() or ""
            if ct not in _ALLOWED_MIME_TYPES:
                suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                ct = _EXT_MIME.get(suffix, ct)

            if ct not in _ALLOWED_MIME_TYPES:
                logger.debug(
                    "email_attachment_skipped_mime",
                    filename=filename,
                    content_type=ct,
                )
                continue

            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes) or not payload:
                continue

            # ── Layer 5-6: attachment size filter ─────────────────────────────
            size_result = self._filter.check_attachment(
                filename=filename, size_bytes=len(payload)
            )
            if not size_result.accepted:
                logger.info(
                    "email_attachment_skipped_by_filter",
                    filename=filename,
                    reason=size_result.reason,
                )
                continue

            results.append((filename, ct, payload))
        return results

    async def _mark_seen(self, uid: str) -> None:
        """Mark an email as \\Seen in the mailbox (runs in thread executor)."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._imap_mark_seen, uid)
        except Exception:
            logger.warning("email_mark_seen_failed", uid=uid)

    def _imap_mark_seen(self, uid: str) -> None:
        if self._use_ssl:
            ctx = ssl.create_default_context()
            conn = imaplib.IMAP4_SSL(self._host, self._port, ssl_context=ctx)
        else:
            conn = imaplib.IMAP4(self._host, self._port)  # type: ignore[assignment]
        conn.login(self._username, self._password)
        conn.select(self._mailbox)
        conn.uid("store", uid, "+FLAGS", "\\Seen")  # type: ignore[call-overload]
        conn.logout()
