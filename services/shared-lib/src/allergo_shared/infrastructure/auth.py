"""JWT authentication middleware shared across FastAPI services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from allergo_shared.domain.value_objects import TenantId

_bearer = HTTPBearer(auto_error=True)


class AuthenticatedUser:
    def __init__(self, sub: str, tenant_id: str, scopes: list[str]) -> None:
        self.sub = sub
        self.tenant_id = TenantId(value=tenant_id)
        self.scopes = scopes


def make_auth_dependency(
    jwks_uri: str,
    audience: str,
    issuer: str,
) -> Callable[..., AuthenticatedUser]:
    """Factory returning a FastAPI dependency for JWT validation via JWKS."""

    jwks_client = jwt.PyJWKClient(jwks_uri)

    async def _auth(
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    ) -> AuthenticatedUser:
        token = credentials.credentials
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer,
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired."
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
            ) from exc

        tenant_id = payload.get("tenant_id") or payload.get("tid") or "default"
        return AuthenticatedUser(
            sub=payload["sub"],
            tenant_id=str(tenant_id),
            scopes=payload.get("scp", "").split(),
        )

    return _auth


def make_noop_auth_dependency() -> Callable[..., AuthenticatedUser]:
    """Auth dependency that always succeeds — for local development only."""

    async def _auth() -> AuthenticatedUser:
        return AuthenticatedUser(sub="dev-user", tenant_id="dev-tenant", scopes=[])

    return _auth
