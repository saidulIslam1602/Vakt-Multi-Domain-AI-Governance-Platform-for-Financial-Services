"""FastAPI application factory for the ingest service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import asyncpg
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from allergo_shared.domain.exceptions import AllergoError, ValidationError
from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
from allergo_shared.infrastructure.azure.service_bus import AzureServiceBus
from allergo_shared.infrastructure.health import HealthCheck, make_health_router
from allergo_shared.infrastructure.logging import configure_logging, get_logger

from ingest_service.infrastructure.config import Settings, get_settings
from ingest_service.presentation.routes.documents import router as documents_router

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    configure_logging(cfg.service_name, cfg.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        logger.info("ingest_service_starting", version=cfg.service_version)
        pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=10)
        blob = AzureBlobStorage(cfg.azure_blob_account_url)
        queue = AzureServiceBus(cfg.azure_servicebus_namespace_fqdn)
        # Store in app.state so dependency providers can retrieve them.
        application.state.pool = pool
        application.state.blob = blob
        application.state.queue = queue

        # ── Email ingestion poller (optional) ─────────────────────────────────
        email_poller = None
        if cfg.email_ingest_enabled:
            from ingest_service.application.use_cases.ingest_email_attachments import (
                IngestEmailAttachmentsUseCase,
            )
            from ingest_service.application.use_cases.upload_document import (
                UploadDocumentUseCase,
            )
            from ingest_service.infrastructure.db.repository import PostgresDocumentRepository
            from ingest_service.infrastructure.email_poller import EmailPoller

            repo = PostgresDocumentRepository(pool)
            upload_uc = UploadDocumentUseCase(storage=blob, queue=queue, repository=repo)
            ingest_uc = IngestEmailAttachmentsUseCase(upload_use_case=upload_uc)

            email_poller = EmailPoller(
                imap_host=cfg.imap_host,
                imap_port=cfg.imap_port,
                imap_username=cfg.imap_username,
                imap_password=cfg.imap_password,
                imap_mailbox=cfg.imap_mailbox,
                poll_interval_sec=cfg.imap_poll_interval_sec,
                use_ssl=cfg.imap_use_ssl,
                tenant_id=cfg.imap_tenant_id,
                pool=pool,
                use_case=ingest_uc,
            )
            email_poller.start()

        yield

        # ── Shutdown ──────────────────────────────────────────────────────────
        if email_poller is not None:
            await email_poller.stop()
        await pool.close()
        await blob.close()
        await queue.close()
        logger.info("ingest_service_stopped")

    app = FastAPI(
        title="Allergo Nordic — Ingest Service",
        description="Document upload API: validates, stores in Azure Blob, publishes to Service Bus.",
        version=cfg.service_version,
        lifespan=lifespan,
        docs_url="/docs" if cfg.environment != "production" else None,
        redoc_url="/redoc" if cfg.environment != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(AllergoError)
    async def allergo_error_handler(request: Request, exc: AllergoError) -> JSONResponse:
        logger.warning("allergo_error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": exc.code, "message": exc.message},
        )

    async def _db_health() -> bool:
        pool: asyncpg.Pool | None = getattr(app.state, "pool", None)
        if pool is None:
            return False
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True

    app.include_router(
        make_health_router(cfg.service_name, cfg.service_version, [HealthCheck("db", _db_health)])
    )
    app.include_router(documents_router, prefix="/api/v1")

    return app


# Defer Settings() read to import time only when run directly (not during test collection).
def _get_app() -> FastAPI:
    return create_app()
