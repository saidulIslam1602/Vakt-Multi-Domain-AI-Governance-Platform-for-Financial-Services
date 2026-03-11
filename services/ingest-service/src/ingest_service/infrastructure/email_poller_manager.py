"""Manages the lifecycle of per-tenant email pollers.

Instead of a single hard-coded poller started at deploy time, the manager
maintains one ``EmailPoller`` asyncio.Task per enabled ``EmailIngestConfig``
row in the database.  Tenants can register / update / delete their IMAP
configuration at runtime through the API, and the manager reacts immediately —
no service restart required.

Public API
──────────
• ``start()``               — load all enabled configs on startup, launch pollers
• ``stop()``                — gracefully stop all running pollers on shutdown
• ``start_tenant(cfg, pw)`` — start poller for a single tenant
• ``stop_tenant(tid)``      — stop + remove poller for a tenant
• ``restart_tenant(cfg,pw)``— stop old poller and start new one (config changed)
• ``get_status()``          — snapshot of running pollers for the API status endpoint
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import asyncpg
from allergo_shared.domain.email_config import EmailIngestConfig
from allergo_shared.domain.interfaces.email_config_repository import IEmailConfigRepository
from allergo_shared.infrastructure.logging import get_logger

from ingest_service.application.use_cases.ingest_email_attachments import (
    IngestEmailAttachmentsUseCase,
)
from ingest_service.application.use_cases.upload_document import UploadDocumentUseCase
from ingest_service.infrastructure.db.repository import PostgresDocumentRepository
from ingest_service.infrastructure.email_filter import EmailFilter
from ingest_service.infrastructure.email_poller import EmailPoller

if TYPE_CHECKING:
    from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
    from allergo_shared.infrastructure.azure.service_bus import AzureServiceBus

logger = get_logger(__name__)


class EmailPollerManager:
    """Owns the full lifecycle of per-tenant IMAP pollers.

    Parameters
    ──────────
    repository
        Provides ``get_all_enabled()`` on startup and ``decrypt_password()``
        whenever a poller is (re-)started.  The decrypted password is held
        only in-memory inside the running ``EmailPoller`` task and is never
        logged.
    pool
        Shared asyncpg connection pool — passed through to each poller so
        deduplication queries and ingest-log writes share the same pool.
    blob
        Azure Blob Storage client — passed to the upload use case.
    queue
        Azure Service Bus client — passed to the upload use case.
    """

    def __init__(
        self,
        *,
        repository: IEmailConfigRepository,
        pool: asyncpg.Pool,
        blob: AzureBlobStorage,
        queue: AzureServiceBus,
    ) -> None:
        self._repo = repository
        self._pool = pool
        self._blob = blob
        self._queue = queue
        # tenant_id → running EmailPoller
        self._pollers: dict[str, EmailPoller] = {}
        self._lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Load all enabled configs from the DB and launch their pollers.

        Called once from the FastAPI lifespan on startup.
        """
        configs = await self._repo.get_all_enabled()
        logger.info("email_poller_manager_starting", enabled_count=len(configs))

        for config in configs:
            try:
                plain_pw = await self._repo.decrypt_password(config.tenant_id)
                await self.start_tenant(config, plain_pw)
            except Exception:
                logger.exception(
                    "email_poller_manager_start_failed",
                    tenant_id=config.tenant_id,
                )

    async def stop(self) -> None:
        """Gracefully stop all running pollers.

        Called once from the FastAPI lifespan on shutdown.
        """
        async with self._lock:
            tenant_ids = list(self._pollers.keys())

        for tenant_id in tenant_ids:
            await self.stop_tenant(tenant_id)

        logger.info("email_poller_manager_stopped")

    # ── Per-tenant control ────────────────────────────────────────────────────

    async def start_tenant(self, config: EmailIngestConfig, plain_password: str) -> None:
        """Start the poller for ``config.tenant_id``.

        If a poller is already running for this tenant it is stopped first
        (idempotent restart).
        """
        await self.stop_tenant(config.tenant_id)

        poller = self._build_poller(config, plain_password)
        async with self._lock:
            self._pollers[config.tenant_id] = poller

        poller.start()
        await self._repo.update_status(config.tenant_id, "running", None)
        logger.info(
            "email_poller_manager_started_tenant",
            tenant_id=config.tenant_id,
            host=config.imap_host,
        )

    async def stop_tenant(self, tenant_id: str) -> None:
        """Stop the running poller for ``tenant_id`` (no-op if not running)."""
        async with self._lock:
            poller = self._pollers.pop(tenant_id, None)

        if poller is not None:
            await poller.stop()
            logger.info("email_poller_manager_stopped_tenant", tenant_id=tenant_id)

    async def restart_tenant(self, config: EmailIngestConfig, plain_password: str) -> None:
        """Stop the old poller and start a new one with updated settings."""
        await self.start_tenant(config, plain_password)  # start_tenant already stops first

    # ── Status snapshot ───────────────────────────────────────────────────────

    def get_status(self) -> list[dict]:
        """Return a snapshot of all managed pollers (used by the status endpoint)."""
        snapshot = []
        for tenant_id, poller in self._pollers.items():
            task: asyncio.Task | None = getattr(poller, "_task", None)
            snapshot.append(
                {
                    "tenant_id": tenant_id,
                    "host": getattr(poller, "_host", ""),
                    "mailbox": getattr(poller, "_mailbox", ""),
                    "interval_sec": getattr(poller, "_interval", 0),
                    "task_running": (
                        task is not None and not task.done()
                    ),
                }
            )
        return snapshot

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_poller(self, config: EmailIngestConfig, plain_password: str) -> EmailPoller:
        """Construct an ``EmailPoller`` wired to the shared infrastructure."""
        doc_repo = PostgresDocumentRepository(self._pool)
        upload_uc = UploadDocumentUseCase(
            storage=self._blob,
            queue=self._queue,
            repository=doc_repo,
        )
        ingest_uc = IngestEmailAttachmentsUseCase(upload_use_case=upload_uc)
        email_filter = EmailFilter.from_config(config)

        return EmailPoller(
            imap_host=config.imap_host,
            imap_port=config.imap_port,
            imap_username=config.imap_username,
            imap_password=plain_password,
            imap_mailbox=config.imap_mailbox,
            poll_interval_sec=config.poll_interval_sec,
            use_ssl=config.use_ssl,
            tenant_id=config.tenant_id,
            pool=self._pool,
            use_case=ingest_uc,
            email_filter=email_filter,
        )
