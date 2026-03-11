"""Webhook management routes — CFO/admin configures outbound notifications."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Annotated

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl

from allergo_shared.infrastructure.auth import AuthenticatedUser
from allergo_shared.infrastructure.logging import get_logger
from document_service.presentation.dependencies import get_current_user, get_pool

logger = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SUPPORTED_EVENTS = frozenset(
    {
        "document.uploaded",
        "document.ready",
        "document.failed",
        "document.review_required",
        "document.approved",
        "document.rejected",
    }
)


class WebhookCreate(BaseModel):
    name: str = Field(max_length=256)
    url: HttpUrl
    events: list[str] = Field(min_length=1)

    def validate_events(self) -> None:
        unknown = set(self.events) - SUPPORTED_EVENTS
        if unknown:
            raise ValueError(f"Unknown event types: {unknown}. Supported: {SUPPORTED_EVENTS}")


class WebhookResponse(BaseModel):
    webhook_id: str
    name: str
    url: str
    events: list[str]
    enabled: bool
    created_at: datetime


class WebhookUpdate(BaseModel):
    enabled: bool | None = None
    events: list[str] | None = None


@router.post("/", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> WebhookResponse:
    """Register a new outbound webhook endpoint for this tenant."""
    body.validate_events()
    signing_secret = secrets.token_hex(32)
    row = await pool.fetchrow(
        """INSERT INTO webhooks (tenant_id, name, url, secret, events)
           VALUES ($1, $2, $3, $4, $5)
           RETURNING id, name, url, events, enabled, created_at""",
        str(current_user.tenant_id),
        body.name,
        str(body.url),
        signing_secret,
        body.events,
    )
    # Return the secret ONCE at creation — never again
    return WebhookResponse(
        webhook_id=str(row["id"]),
        name=row["name"],
        url=row["url"],
        events=list(row["events"]),
        enabled=row["enabled"],
        created_at=row["created_at"],
    )


@router.get("/", response_model=list[WebhookResponse])
async def list_webhooks(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> list[WebhookResponse]:
    rows = await pool.fetch(
        "SELECT id, name, url, events, enabled, created_at FROM webhooks WHERE tenant_id = $1",
        str(current_user.tenant_id),
    )
    return [
        WebhookResponse(
            webhook_id=str(r["id"]),
            name=r["name"],
            url=r["url"],
            events=list(r["events"]),
            enabled=r["enabled"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> WebhookResponse:
    row = await pool.fetchrow(
        "SELECT * FROM webhooks WHERE id = $1 AND tenant_id = $2",
        webhook_id, str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")
    enabled = body.enabled if body.enabled is not None else row["enabled"]
    events = body.events if body.events is not None else list(row["events"])
    updated = await pool.fetchrow(
        """UPDATE webhooks SET enabled = $3, events = $4, updated_at = now()
           WHERE id = $1 AND tenant_id = $2
           RETURNING id, name, url, events, enabled, created_at""",
        webhook_id, str(current_user.tenant_id), enabled, events,
    )
    return WebhookResponse(
        webhook_id=str(updated["id"]),
        name=updated["name"],
        url=updated["url"],
        events=list(updated["events"]),
        enabled=updated["enabled"],
        created_at=updated["created_at"],
    )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> None:
    result = await pool.execute(
        "DELETE FROM webhooks WHERE id = $1 AND tenant_id = $2",
        webhook_id, str(current_user.tenant_id),
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found.")


# ── Internal delivery helper ─────────────────────────────────────────────────

def _sign_payload(secret: str, payload: bytes) -> str:
    """Return HMAC-SHA256 hex signature (same format as GitHub webhooks)."""
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def dispatch_webhook_event(
    pool: asyncpg.Pool,
    tenant_id: str,
    event_type: str,
    document_id: str | None,
    payload: dict,
) -> None:
    """Fire outbound webhooks for an event. Safe to run as a background task."""
    rows = await pool.fetch(
        "SELECT id, url, secret FROM webhooks WHERE tenant_id = $1 AND enabled = true AND $2 = ANY(events)",
        tenant_id, event_type,
    )
    if not rows:
        return

    envelope = {
        "event": event_type,
        "tenant_id": tenant_id,
        "document_id": document_id,
        "timestamp": int(time.time()),
        "data": payload,
    }
    body = json.dumps(envelope).encode()

    async with httpx.AsyncClient(timeout=10.0) as client:
        for row in rows:
            signature = _sign_payload(row["secret"], body)
            try:
                resp = await client.post(
                    row["url"],
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Allergo-Signature": signature,
                        "X-Allergo-Event": event_type,
                    },
                )
                success = resp.is_success
            except Exception as exc:
                logger.warning("webhook_delivery_failed", webhook_id=str(row["id"]), error=str(exc))
                success = False
                resp = None

            await pool.execute(
                """INSERT INTO webhook_deliveries
                   (webhook_id, event_type, document_id, payload, status_code, response_body, success)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                row["id"],
                event_type,
                document_id,
                json.dumps(payload),
                resp.status_code if resp else None,
                resp.text[:2000] if resp else None,
                success,
            )
