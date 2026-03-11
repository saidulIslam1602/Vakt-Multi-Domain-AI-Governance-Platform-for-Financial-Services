"""FastAPI dependency providers for the chat service."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from allergo_shared.infrastructure.auth import make_auth_dependency, make_noop_auth_dependency
from chat_service.application.rag import RagUseCase


def get_rag_use_case(request: Request) -> Any:  # RagUseCase | ElasticsearchRagUseCase
    """Return the RAG use-case stored in app.state during lifespan startup.

    Returns Any to allow both RagUseCase (Azure AI Search) and
    ElasticsearchRagUseCase (local dev) without a runtime import cycle.
    Both classes expose the same public interface: answer(), answer_stream(),
    and _parse_suggestions().
    """
    return request.app.state.rag


def _build_auth_dependency():  # type: ignore[return]
    import os
    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() != "false"
    if not auth_enabled:
        return make_noop_auth_dependency()
    jwks_uri = os.environ["AUTH_JWKS_URI"]
    audience = os.environ["AUTH_AUDIENCE"]
    issuer = os.environ["AUTH_ISSUER"]
    return make_auth_dependency(jwks_uri, audience, issuer)


get_current_user = _build_auth_dependency()
