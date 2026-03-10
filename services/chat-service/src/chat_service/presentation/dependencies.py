"""FastAPI dependency providers for the chat service."""

from __future__ import annotations

from fastapi import Request

from allergo_shared.infrastructure.auth import make_auth_dependency, make_noop_auth_dependency
from chat_service.application.rag import RagUseCase


def get_rag_use_case(request: Request) -> RagUseCase:
    return request.app.state.rag  # type: ignore[no-any-return]


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
