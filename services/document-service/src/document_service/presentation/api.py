"""FastAPI application factory for the document service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import asyncpg
from azure.identity.aio import DefaultAzureCredential
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
from allergo_shared.infrastructure.health import make_health_router
from allergo_shared.infrastructure.logging import configure_logging
from document_service.presentation.config import get_settings
from document_service.presentation.routes.alerts import router as alerts_router
from document_service.presentation.routes.documents import router as documents_router
from document_service.presentation.routes.download import router as download_router
from document_service.presentation.routes.export import router as export_router
from document_service.presentation.routes.history import router as history_router
from document_service.presentation.routes.review import router as review_router
from document_service.presentation.routes.stats import router as stats_router
from document_service.presentation.routes.tags import router as tags_router
from document_service.presentation.routes.webhooks import router as webhooks_router


def create_app() -> FastAPI:
    cfg = get_settings()
    configure_logging(cfg.service_name, cfg.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=10)
        credential = DefaultAzureCredential()
        blob = AzureBlobStorage(
            account_url=cfg.azure_storage_account_url,
            credential=credential,
        )
        application.state.pool = pool
        application.state.blob = blob
        yield
        await pool.close()
        await credential.close()

    app = FastAPI(
        title="Allergo Nordic — Document Service",
        description="Document metadata CRUD, review-queue, audit trail, download, and webhook APIs.",
        version=cfg.service_version,
        lifespan=lifespan,
        docs_url="/docs" if cfg.environment != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(make_health_router(cfg.service_name, cfg.service_version))
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(download_router, prefix="/api/v1")
    app.include_router(export_router, prefix="/api/v1")
    app.include_router(history_router, prefix="/api/v1")
    app.include_router(review_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.include_router(tags_router, prefix="/api/v1")
    app.include_router(webhooks_router, prefix="/api/v1")
    return app


def _get_app() -> FastAPI:
    return create_app()
