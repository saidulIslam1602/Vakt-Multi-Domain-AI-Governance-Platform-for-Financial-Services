"""Alerting rule management and event feed routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from allergo_shared.infrastructure.auth import AuthenticatedUser
from allergo_shared.infrastructure.logging import get_logger
from document_service.presentation.dependencies import get_current_user, get_pool

logger = get_logger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])

TriggerType = Literal[
    "invoice_overdue",
    "invoice_amount_threshold",
    "contract_expiring",
    "legal_risk",
    "low_confidence",
    "pending_review_threshold",
]

VALID_CHANNELS = frozenset({"in_app", "email"})


class AlertRuleCreate(BaseModel):
    name: str = Field(max_length=256)
    trigger_type: TriggerType
    threshold_value: float | None = Field(
        default=None,
        description="Amount threshold in NOK (for invoice_amount_threshold).",
    )
    days_before: int | None = Field(
        default=None,
        description="Days lookahead for contract_expiring.",
    )
    document_category: str | None = None
    channels: list[str] = Field(default=["in_app"])

    def validate_channels(self) -> None:
        unknown = set(self.channels) - VALID_CHANNELS
        if unknown:
            raise ValueError(f"Unknown channels: {unknown}. Allowed: {VALID_CHANNELS}")


class AlertRuleResponse(BaseModel):
    rule_id: str
    name: str
    trigger_type: str
    threshold_value: float | None
    days_before: int | None
    document_category: str | None
    channels: list[str]
    enabled: bool
    created_at: datetime


class AlertEventResponse(BaseModel):
    event_id: str
    rule_id: str
    document_id: str | None
    trigger_type: str
    message: str
    metadata: dict
    acknowledged: bool
    created_at: datetime


# ── Rules CRUD ────────────────────────────────────────────────────────────────

@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: AlertRuleCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> AlertRuleResponse:
    """Create a new proactive alerting rule."""
    body.validate_channels()
    row = await pool.fetchrow(
        """INSERT INTO alert_rules
               (tenant_id, name, trigger_type, threshold_value, days_before,
                document_category, channels)
           VALUES ($1,$2,$3,$4,$5,$6,$7)
           RETURNING id, name, trigger_type, threshold_value, days_before,
                     document_category, channels, enabled, created_at""",
        str(current_user.tenant_id),
        body.name,
        body.trigger_type,
        body.threshold_value,
        body.days_before,
        body.document_category,
        body.channels,
    )
    return _map_rule(row)


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_rules(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> list[AlertRuleResponse]:
    rows = await pool.fetch(
        """SELECT id, name, trigger_type, threshold_value, days_before,
                  document_category, channels, enabled, created_at
           FROM alert_rules
           WHERE tenant_id = $1
           ORDER BY created_at DESC""",
        str(current_user.tenant_id),
    )
    return [_map_rule(r) for r in rows]


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> None:
    result = await pool.execute(
        "DELETE FROM alert_rules WHERE id = $1 AND tenant_id = $2",
        rule_id,
        str(current_user.tenant_id),
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")


@router.patch("/rules/{rule_id}/toggle", response_model=AlertRuleResponse)
async def toggle_rule(
    rule_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> AlertRuleResponse:
    row = await pool.fetchrow(
        """UPDATE alert_rules
           SET enabled = NOT enabled
           WHERE id = $1 AND tenant_id = $2
           RETURNING id, name, trigger_type, threshold_value, days_before,
                     document_category, channels, enabled, created_at""",
        rule_id,
        str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return _map_rule(row)


# ── Alert events feed ─────────────────────────────────────────────────────────

@router.get("/events", response_model=list[AlertEventResponse])
async def list_events(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
) -> list[AlertEventResponse]:
    """Return alert events newest first. Pass unread_only=true for only unacknowledged."""
    where = "tenant_id = $1"
    params: list = [str(current_user.tenant_id)]
    if unread_only:
        where += " AND acknowledged = false"
    rows = await pool.fetch(
        f"""SELECT id, rule_id, document_id, trigger_type, message, metadata,
                   acknowledged, created_at
            FROM alert_events
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT $2""",
        *params, limit,
    )
    return [_map_event(r) for r in rows]


@router.patch("/events/{event_id}/acknowledge", status_code=status.HTTP_200_OK)
async def acknowledge_event(
    event_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict:
    result = await pool.execute(
        "UPDATE alert_events SET acknowledged = true WHERE id = $1 AND tenant_id = $2",
        event_id,
        str(current_user.tenant_id),
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return {"event_id": event_id, "acknowledged": True}


@router.post("/events/acknowledge-all", status_code=status.HTTP_200_OK)
async def acknowledge_all(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> dict:
    await pool.execute(
        "UPDATE alert_events SET acknowledged = true WHERE tenant_id = $1 AND acknowledged = false",
        str(current_user.tenant_id),
    )
    return {"acknowledged": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _map_rule(row: asyncpg.Record) -> AlertRuleResponse:
    return AlertRuleResponse(
        rule_id=str(row["id"]),
        name=row["name"],
        trigger_type=row["trigger_type"],
        threshold_value=float(row["threshold_value"]) if row["threshold_value"] is not None else None,
        days_before=row["days_before"],
        document_category=row["document_category"],
        channels=list(row["channels"]),
        enabled=row["enabled"],
        created_at=row["created_at"],
    )


def _map_event(row: asyncpg.Record) -> AlertEventResponse:
    return AlertEventResponse(
        event_id=str(row["id"]),
        rule_id=str(row["rule_id"]),
        document_id=str(row["document_id"]) if row["document_id"] else None,
        trigger_type=row["trigger_type"],
        message=row["message"],
        metadata=dict(row["metadata"]) if row["metadata"] else {},
        acknowledged=row["acknowledged"],
        created_at=row["created_at"],
    )
