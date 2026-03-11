"""FastAPI dependency providers for the ingest service."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from allergo_shared.infrastructure.auth import make_auth_dependency, make_noop_auth_dependency
from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
from allergo_shared.infrastructure.azure.service_bus import AzureServiceBus
from fastapi import Depends, Request

from ingest_service.application.use_cases.upload_document import UploadDocumentUseCase
from ingest_service.infrastructure.config import get_settings
from ingest_service.infrastructure.db.repository import PostgresDocumentRepository


def _get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool  # type: ignore[no-any-return]


def _get_blob(request: Request) -> AzureBlobStorage:
    return request.app.state.blob  # type: ignore[no-any-return]


def _get_queue(request: Request) -> AzureServiceBus:
    return request.app.state.queue  # type: ignore[no-any-return]


def get_repository(pool: Annotated[asyncpg.Pool, Depends(_get_pool)]) -> PostgresDocumentRepository:
    return PostgresDocumentRepository(pool)


def get_upload_use_case(
    blob: Annotated[AzureBlobStorage, Depends(_get_blob)],
    queue: Annotated[AzureServiceBus, Depends(_get_queue)],
    repository: Annotated[PostgresDocumentRepository, Depends(get_repository)],
) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(storage=blob, queue=queue, repository=repository)


def get_email_config_service(
    request: Request,
    pool: Annotated[asyncpg.Pool, Depends(_get_pool)],
):  # type: ignore[return]
    """Return an EmailConfigService wired to the DB pool and the live manager."""
    from ingest_service.application.use_cases.email_config_service import EmailConfigService
    from ingest_service.infrastructure.db.email_config_repository import (
        PostgresEmailConfigRepository,
    )
    from ingest_service.infrastructure.email_poller_manager import EmailPollerManager

    cfg = get_settings()
    repo = PostgresEmailConfigRepository(pool, enc_key=cfg.db_encryption_key)
    manager: EmailPollerManager = request.app.state.email_poller_manager
    return EmailConfigService(repository=repo, poller_manager=manager)


def _build_auth_dependency():  # type: ignore[return]
    cfg = get_settings()
    if not cfg.auth_enabled:
        return make_noop_auth_dependency()
    return make_auth_dependency(cfg.auth_jwks_uri, cfg.auth_audience, cfg.auth_issuer)


get_current_user = _build_auth_dependency()
