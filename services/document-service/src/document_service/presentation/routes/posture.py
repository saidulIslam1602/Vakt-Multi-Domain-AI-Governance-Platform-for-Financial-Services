"""Infrastructure posture — policy/IaC findings (inspect-only path toward governance workflows)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/posture", tags=["posture"])


class InfraFindingItem(BaseModel):
    id: str
    severity: str
    rule_id: str
    title: str
    file_path: str | None
    line_start: int | None
    line_end: int | None
    policy_pack_ref: str | None
    remediation_hint: str | None
    source_scan_id: str | None
    created_at: datetime


class InfraFindingDetail(InfraFindingItem):
    detail_json: dict = Field(default_factory=dict)


@router.get("/findings", response_model=list[InfraFindingItem])
async def list_infra_findings(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    severity: str | None = Query(default=None, description="Filter by severity, e.g. HIGH"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[InfraFindingItem]:
    tenant = str(current_user.tenant_id)
    params: list = [tenant]
    where = "tenant_id = $1"
    if severity:
        params.append(severity.upper())
        where += f" AND UPPER(severity) = ${len(params)}"

    rows = await pool.fetch(
        f"""SELECT id, severity, rule_id, title, file_path, line_start, line_end,
                   policy_pack_ref, remediation_hint, source_scan_id, created_at
            FROM infra_findings
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
        *params,
        limit,
        offset,
    )
    return [
        InfraFindingItem(
            id=str(r["id"]),
            severity=r["severity"],
            rule_id=r["rule_id"],
            title=r["title"],
            file_path=r["file_path"],
            line_start=r["line_start"],
            line_end=r["line_end"],
            policy_pack_ref=r["policy_pack_ref"],
            remediation_hint=r["remediation_hint"],
            source_scan_id=r["source_scan_id"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/findings/{finding_id}", response_model=InfraFindingDetail)
async def get_infra_finding(
    finding_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> InfraFindingDetail:
    tenant = str(current_user.tenant_id)
    row = await pool.fetchrow(
        """SELECT id, severity, rule_id, title, file_path, line_start, line_end,
                  policy_pack_ref, remediation_hint, source_scan_id, created_at, detail_json
           FROM infra_findings
           WHERE id = $1 AND tenant_id = $2""",
        finding_id,
        tenant,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")
    detail = row["detail_json"]
    if detail is None:
        detail = {}
    elif not isinstance(detail, dict):
        detail = dict(detail)
    return InfraFindingDetail(
        id=str(row["id"]),
        severity=row["severity"],
        rule_id=row["rule_id"],
        title=row["title"],
        file_path=row["file_path"],
        line_start=row["line_start"],
        line_end=row["line_end"],
        policy_pack_ref=row["policy_pack_ref"],
        remediation_hint=row["remediation_hint"],
        source_scan_id=row["source_scan_id"],
        created_at=row["created_at"],
        detail_json=detail,
    )
