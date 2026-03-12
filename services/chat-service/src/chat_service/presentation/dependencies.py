"""FastAPI dependency providers for the chat service."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from allergo_shared.infrastructure.auth import make_auth_dependency, make_noop_auth_dependency
from chat_service.presentation.config import get_settings


def get_rag_use_case(request: Request) -> Any:  # RagUseCase | ElasticsearchRagUseCase
    """Return the RAG use-case stored in app.state during lifespan startup.

    Returns Any to allow both RagUseCase (Azure AI Search) and
    ElasticsearchRagUseCase (local dev) without a runtime import cycle.
    Both classes expose the same public interface: answer(), answer_stream(),
    and _parse_suggestions().
    """
    return request.app.state.rag


def _build_auth_dependency() -> Any:  # type: ignore[return]
    """Build the auth dependency from Settings (same pattern as document-service).

    Settings.auth_jwks_uri defaults to "" and auth_enabled defaults to True,
    so if AUTH_ENABLED=false is set the noop path is taken without any
    KeyError — fixing the crash-loop on Azure Container Apps.
    """
    cfg = get_settings()
    if not cfg.auth_enabled:
        return make_noop_auth_dependency()
    return make_auth_dependency(cfg.auth_jwks_uri, cfg.auth_audience, cfg.auth_issuer)


get_current_user = _build_auth_dependency()
