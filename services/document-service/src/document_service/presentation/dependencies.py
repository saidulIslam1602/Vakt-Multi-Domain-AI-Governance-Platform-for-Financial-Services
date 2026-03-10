"""FastAPI dependency providers for the document service."""

from __future__ import annotations

import asyncpg
from fastapi import Request

from allergo_shared.infrastructure.auth import (
    make_auth_dependency,
    make_noop_auth_dependency,
)
from allergo_shared.infrastructure.azure.blob import AzureBlobStorage

from document_service.presentation.config import get_settings


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool  # type: ignore[no-any-return]


def get_blob(request: Request) -> AzureBlobStorage:
    return request.app.state.blob  # type: ignore[no-any-return]


def _build_auth_dependency():  # type: ignore[return]
    cfg = get_settings()
    if not cfg.auth_enabled:
        return make_noop_auth_dependency()
    return make_auth_dependency(cfg.auth_jwks_uri, cfg.auth_audience, cfg.auth_issuer)


get_current_user = _build_auth_dependency()
