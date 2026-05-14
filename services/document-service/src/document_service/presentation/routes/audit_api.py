"""Thin HTTP endpoint for cross-service audit writes.

Used by chat-service to emit audit events (policy violations, tool cap hits)
without duplicating asyncpg logic there. Only reachable from within the
internal Docker/Container Apps network.
"""

from __future__ import annotations

from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.infrastructure.audit import append_audit_event
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventBody(BaseModel):
    actor: str
    action: str
    resource_type: str
    resource_id: str | None = None
    metadata: dict[str, Any] = {}


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def write_audit_event(
    body: AuditEventBody,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> None:
    """Append a governance audit event on behalf of another service.

    The tenant is always taken from the authenticated JWT claim — the caller
    cannot spoof a different tenant's audit trail.
    """
    await append_audit_event(
        pool,
        tenant_id=str(current_user.tenant_id),
        actor=body.actor,
        action=body.action,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        metadata=body.metadata,
    )
