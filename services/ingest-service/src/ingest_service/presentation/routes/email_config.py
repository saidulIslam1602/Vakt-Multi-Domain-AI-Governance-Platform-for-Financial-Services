"""API routes: per-tenant email ingestion configuration.

Endpoints
─────────
GET    /email-config          — get current tenant's config (password masked)
POST   /email-config          — register a new IMAP inbox (201)
PATCH  /email-config          — sparse update (only provided fields)
DELETE /email-config          — remove config and stop the poller (204)
POST   /email-config/test     — validate IMAP credentials (no DB write)
GET    /email-config/status   — live poller status from the manager

All endpoints require a valid JWT (same as document endpoints).
The tenant_id is derived from the authenticated user's claims — tenants
can only access / modify their own email config.
"""

from __future__ import annotations

from typing import Annotated

from allergo_shared.infrastructure.auth import AuthenticatedUser
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ingest_service.application.use_cases.email_config_service import (
    ConflictError,
    EmailConfigService,
    NotFoundError,
)
from ingest_service.presentation.dependencies import get_current_user, get_email_config_service

router = APIRouter(prefix="/email-config", tags=["email-config"])


# ── Request / response schemas ────────────────────────────────────────────────

class EmailConfigCreateRequest(BaseModel):
    imap_host: str = Field(..., min_length=1, description="IMAP server hostname")
    imap_port: int = Field(993, ge=1, le=65535)
    imap_username: str = Field(..., min_length=1)
    imap_password: str = Field(..., min_length=1)
    imap_mailbox: str = Field("INBOX", min_length=1)
    use_ssl: bool = True
    poll_interval_sec: int = Field(300, ge=60)
    enabled: bool = True
    allowed_senders: str = ""
    blocked_senders: str = ""
    required_subject_kw: str = ""
    blocked_subject_kw: str = ""
    min_attachment_bytes: int = Field(1024, ge=0)
    max_attachment_bytes: int = Field(52_428_800, ge=1)


class EmailConfigPatchRequest(BaseModel):
    """All fields optional for a sparse PATCH."""

    imap_host: str | None = None
    imap_port: int | None = Field(None, ge=1, le=65535)
    imap_username: str | None = None
    imap_password: str | None = None
    imap_mailbox: str | None = None
    use_ssl: bool | None = None
    poll_interval_sec: int | None = Field(None, ge=60)
    enabled: bool | None = None
    allowed_senders: str | None = None
    blocked_senders: str | None = None
    required_subject_kw: str | None = None
    blocked_subject_kw: str | None = None
    min_attachment_bytes: int | None = Field(None, ge=0)
    max_attachment_bytes: int | None = Field(None, ge=1)


class EmailConfigTestRequest(BaseModel):
    imap_host: str = Field(..., min_length=1)
    imap_port: int = Field(993, ge=1, le=65535)
    imap_username: str = Field(..., min_length=1)
    imap_password: str = Field(..., min_length=1)
    imap_mailbox: str = "INBOX"
    use_ssl: bool = True


# ── GET /email-config ─────────────────────────────────────────────────────────

@router.get(
    "",
    summary="Get the current tenant's email ingestion config",
    response_model=dict,
)
async def get_email_config(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmailConfigService, Depends(get_email_config_service)],
) -> dict:
    try:
        return await service.get(str(current_user.tenant_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /email-config ────────────────────────────────────────────────────────

@router.post(
    "",
    summary="Register a new IMAP inbox for document ingestion",
    status_code=status.HTTP_201_CREATED,
    response_model=dict,
)
async def create_email_config(
    body: EmailConfigCreateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmailConfigService, Depends(get_email_config_service)],
) -> dict:
    try:
        return await service.create(
            str(current_user.tenant_id),
            imap_host=body.imap_host,
            imap_port=body.imap_port,
            imap_username=body.imap_username,
            plain_password=body.imap_password,
            imap_mailbox=body.imap_mailbox,
            use_ssl=body.use_ssl,
            poll_interval_sec=body.poll_interval_sec,
            enabled=body.enabled,
            allowed_senders=body.allowed_senders,
            blocked_senders=body.blocked_senders,
            required_subject_kw=body.required_subject_kw,
            blocked_subject_kw=body.blocked_subject_kw,
            min_attachment_bytes=body.min_attachment_bytes,
            max_attachment_bytes=body.max_attachment_bytes,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# ── PATCH /email-config ───────────────────────────────────────────────────────

@router.patch(
    "",
    summary="Update the current tenant's email ingestion config (sparse)",
    response_model=dict,
)
async def patch_email_config(
    body: EmailConfigPatchRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmailConfigService, Depends(get_email_config_service)],
) -> dict:
    try:
        return await service.update(
            str(current_user.tenant_id),
            imap_host=body.imap_host,
            imap_port=body.imap_port,
            imap_username=body.imap_username,
            plain_password=body.imap_password,
            imap_mailbox=body.imap_mailbox,
            use_ssl=body.use_ssl,
            poll_interval_sec=body.poll_interval_sec,
            enabled=body.enabled,
            allowed_senders=body.allowed_senders,
            blocked_senders=body.blocked_senders,
            required_subject_kw=body.required_subject_kw,
            blocked_subject_kw=body.blocked_subject_kw,
            min_attachment_bytes=body.min_attachment_bytes,
            max_attachment_bytes=body.max_attachment_bytes,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# ── DELETE /email-config ──────────────────────────────────────────────────────

@router.delete(
    "",
    summary="Remove the current tenant's email ingestion config",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_email_config(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmailConfigService, Depends(get_email_config_service)],
) -> None:
    try:
        await service.delete(str(current_user.tenant_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /email-config/test ───────────────────────────────────────────────────

@router.post(
    "/test",
    summary="Test IMAP credentials without saving (no DB write)",
    response_model=dict,
)
async def test_email_connection(
    body: EmailConfigTestRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[EmailConfigService, Depends(get_email_config_service)],
) -> dict:
    return await service.test_connection(
        imap_host=body.imap_host,
        imap_port=body.imap_port,
        imap_username=body.imap_username,
        plain_password=body.imap_password,
        imap_mailbox=body.imap_mailbox,
        use_ssl=body.use_ssl,
    )


# ── GET /email-config/status ──────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Live poller status for the current tenant",
    response_model=dict,
)
async def get_poller_status(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> dict:
    """Returns the live poller status from the manager held in app.state."""
    from ingest_service.infrastructure.email_poller_manager import EmailPollerManager

    manager: EmailPollerManager | None = getattr(request.app.state, "email_poller_manager", None)
    if manager is None:
        return {"tenant_id": str(current_user.tenant_id), "task_running": False}

    all_statuses = manager.get_status()
    tenant_id = str(current_user.tenant_id)
    for entry in all_statuses:
        if entry["tenant_id"] == tenant_id:
            return entry

    return {"tenant_id": tenant_id, "task_running": False}
