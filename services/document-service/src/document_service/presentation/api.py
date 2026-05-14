"""FastAPI application factory for the document service."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allergo_shared.infrastructure.rate_limit import RateLimitMiddleware

from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
from allergo_shared.infrastructure.health import make_health_router
from allergo_shared.infrastructure.logging import configure_logging
from document_service.presentation.config import get_settings
from document_service.presentation.routes.alerts import router as alerts_router
from document_service.presentation.routes.audit_api import router as audit_api_router
from document_service.presentation.routes.documents import router as documents_router
from document_service.presentation.routes.download import router as download_router
from document_service.presentation.routes.export import router as export_router
from document_service.presentation.routes.history import router as history_router
from document_service.presentation.routes.posture import router as posture_router
from document_service.presentation.routes.posture_proposals import router as posture_proposals_router
from document_service.presentation.routes.review import router as review_router
from document_service.presentation.routes.stats import router as stats_router
from document_service.presentation.routes.tags import router as tags_router
from document_service.presentation.routes.webhooks import router as webhooks_router


def create_app() -> FastAPI:
    cfg = get_settings()
    configure_logging(cfg.service_name, cfg.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        async def _init_conn(conn: asyncpg.Connection) -> None:
            # Register JSONB codec so Python dicts are automatically encoded/decoded.
            # Required for asyncpg >= 0.27 when passing dict values to JSONB columns.
            await conn.set_type_codec(
                "jsonb",
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog",
            )

        pool = await asyncpg.create_pool(
            cfg.database_url, min_size=2, max_size=10, init=_init_conn
        )
        blob = AzureBlobStorage(account_url=cfg.azure_storage_account_url)
        application.state.pool = pool
        application.state.blob = blob
        yield
        await pool.close()
        await blob.close()

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
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=120,
        burst_multiplier=2.0,
        enabled=cfg.environment != "local",
    )
    app.include_router(make_health_router(cfg.service_name, cfg.service_version))
    app.include_router(alerts_router, prefix="/api/v1")
    app.include_router(audit_api_router, prefix="/api/v1")
    # export_router MUST be registered before documents_router — FastAPI matches
    # routes in registration order and /documents/{id} would otherwise swallow
    # the literal path /documents/export.csv.
    app.include_router(export_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(download_router, prefix="/api/v1")
    app.include_router(history_router, prefix="/api/v1")
    app.include_router(review_router, prefix="/api/v1")
    app.include_router(posture_router, prefix="/api/v1")
    app.include_router(posture_proposals_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.include_router(tags_router, prefix="/api/v1")
    app.include_router(webhooks_router, prefix="/api/v1")
    return app


def _get_app() -> FastAPI:
    return create_app()
