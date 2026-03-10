"""FastAPI dependency providers for the search service."""

from __future__ import annotations

from fastapi import Request

from allergo_shared.infrastructure.auth import make_auth_dependency, make_noop_auth_dependency
from search_service.infrastructure.config import get_settings
from search_service.application.search import SearchUseCase


def get_search_use_case(request: Request) -> SearchUseCase:
    return request.app.state.search_use_case  # type: ignore[no-any-return]


def _build_auth_dependency():  # type: ignore[return]
    cfg = get_settings()
    if not cfg.auth_enabled:
        return make_noop_auth_dependency()
    return make_auth_dependency(cfg.auth_jwks_uri, cfg.auth_audience, cfg.auth_issuer)


get_current_user = _build_auth_dependency()
