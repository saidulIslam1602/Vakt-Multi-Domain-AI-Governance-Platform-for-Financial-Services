"""Posture governance — workflow runs, change proposals, HITL approve/reject.

Extends /posture with write paths:
  POST   /posture/runs                          — create agent_workflow_run
  GET    /posture/runs                          — list runs (tenant-scoped)
  GET    /posture/runs/{run_id}                 — single run
  POST   /posture/runs/{run_id}/proposals       — attach change_proposal to run
  POST   /posture/runs/{run_id}/context-snapshot — build + store infra context bundle
  GET    /posture/proposals/{id}                — single proposal
  POST   /posture/proposals/{id}/validate       — Pydantic validation gate
  POST   /posture/proposals/{id}/approve        — HITL approve → audit event
  POST   /posture/proposals/{id}/reject         — HITL reject  → audit event
  POST   /posture/proposals/{id}/export         — PR title/body + patch file export
  GET    /posture/snapshots/{snapshot_id}       — read a context snapshot
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from allergo_shared.infrastructure.auth import AuthenticatedUser
from document_service.domain.infra_context import build_context_bundle
from document_service.infrastructure.audit import append_audit_event
from document_service.presentation.dependencies import get_current_user, get_pool

router = APIRouter(prefix="/posture", tags=["proposals"])


# ── Literal type for workflow states ─────────────────────────────────────────

WorkflowState = Literal[
    "gathering_context",
    "proposing",
    "validating",
    "pending_approval",
    "approved",
    "rejected",
    "failed_validation",
    "context_frozen",
]


# ── Request / response models ─────────────────────────────────────────────────


class RunCreate(BaseModel):
    session_type: str = Field(default="infra_remediation", max_length=64)
    max_tool_rounds: int = Field(default=6, ge=1, le=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunItem(BaseModel):
    id: str
    tenant_id: str
    session_type: str
    workflow_state: str
    created_by: str
    tool_rounds_used: int
    max_tool_rounds: int
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProposalCreate(BaseModel):
    unified_diff: str = Field(min_length=1)
    rationale_md: str = Field(default="", max_length=8192)
    resource_addresses: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class ProposalValidateBody(BaseModel):
    unified_diff: str = Field(min_length=1)
    rationale_md: str = Field(min_length=1)
    resource_addresses: list[str] = Field(min_length=1)
    risk_level: str = Field(pattern="^(low|medium|high|critical)$")


class ProposalItem(BaseModel):
    id: str
    run_id: str
    unified_diff: str
    rationale_md: str
    resource_addresses: list[str]
    risk_level: str | None
    validation_errors: dict[str, Any] | None
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


class DecisionBody(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class ContextSnapshotItem(BaseModel):
    id: str
    run_id: str | None
    bundle_json: dict[str, Any]
    created_at: datetime


class ExportResponse(BaseModel):
    pr_title: str
    pr_body: str
    patch_filename: str
    patch_content: str
    git_apply_instructions: str


# ── Runs ──────────────────────────────────────────────────────────────────────


@router.post("/runs", response_model=RunItem, status_code=status.HTTP_201_CREATED)
async def create_run(
    body: RunCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> RunItem:
    """Create a new agent workflow run in 'gathering_context' state."""
    tenant = str(current_user.tenant_id)
    row = await pool.fetchrow(
        """INSERT INTO agent_workflow_runs (
               tenant_id, session_type, workflow_state, created_by,
               tool_rounds_used, max_tool_rounds, metadata_json
           )
           VALUES ($1, $2, 'gathering_context', $3, 0, $4, $5)
           RETURNING id, tenant_id, session_type, workflow_state, created_by,
                     tool_rounds_used, max_tool_rounds, metadata_json,
                     created_at, updated_at""",
        tenant,
        body.session_type,
        current_user.sub,
        body.max_tool_rounds,
        body.metadata,
    )
    return _row_to_run(row)


@router.get("/runs", response_model=list[RunItem])
async def list_runs(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
    workflow_state: str | None = Query(default=None, description="Filter by workflow state"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[RunItem]:
    tenant = str(current_user.tenant_id)
    params: list[Any] = [tenant]
    where = "tenant_id = $1"
    if workflow_state:
        params.append(workflow_state)
        where += f" AND workflow_state = ${len(params)}"
    rows = await pool.fetch(
        f"""SELECT id, tenant_id, session_type, workflow_state, created_by,
                   tool_rounds_used, max_tool_rounds, metadata_json, created_at, updated_at
            FROM agent_workflow_runs
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}""",
        *params,
        limit,
        offset,
    )
    return [_row_to_run(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunItem)
async def get_run(
    run_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> RunItem:
    row = await pool.fetchrow(
        """SELECT id, tenant_id, session_type, workflow_state, created_by,
                  tool_rounds_used, max_tool_rounds, metadata_json, created_at, updated_at
           FROM agent_workflow_runs
           WHERE id = $1 AND tenant_id = $2""",
        run_id,
        str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return _row_to_run(row)


# ── Proposals ─────────────────────────────────────────────────────────────────


@router.post(
    "/runs/{run_id}/proposals",
    response_model=ProposalItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_proposal(
    run_id: UUID,
    body: ProposalCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ProposalItem:
    """Attach a change proposal (diff + rationale) to an existing run.

    Each run may have at most one proposal (enforced by DB UNIQUE constraint).
    """
    tenant = str(current_user.tenant_id)
    run_row = await pool.fetchrow(
        "SELECT id FROM agent_workflow_runs WHERE id = $1 AND tenant_id = $2",
        run_id,
        tenant,
    )
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    await pool.execute(
        "UPDATE agent_workflow_runs SET workflow_state = 'proposing', updated_at = NOW() WHERE id = $1",
        run_id,
    )

    try:
        row = await pool.fetchrow(
            """INSERT INTO change_proposals (
                   run_id, tenant_id, unified_diff, rationale_md, resource_addresses, risk_level
               )
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING id, run_id, unified_diff, rationale_md, resource_addresses, risk_level,
                         validation_errors, decided_by, decided_at, created_at""",
            run_id,
            tenant,
            body.unified_diff,
            body.rationale_md,
            body.resource_addresses,
            body.risk_level,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A proposal already exists for this run. Each run may have at most one proposal.",
        )
    return _row_to_proposal(row)


@router.get("/proposals/{proposal_id}", response_model=ProposalItem)
async def get_proposal(
    proposal_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ProposalItem:
    row = await pool.fetchrow(
        """SELECT id, run_id, unified_diff, rationale_md, resource_addresses, risk_level,
                  validation_errors, decided_by, decided_at, created_at
           FROM change_proposals
           WHERE id = $1 AND tenant_id = $2""",
        proposal_id,
        str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")
    return _row_to_proposal(row)


@router.post("/proposals/{proposal_id}/validate", response_model=ProposalItem)
async def validate_proposal(
    proposal_id: UUID,
    body: ProposalValidateBody,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ProposalItem:
    """Validate proposal payload.

    On success: transitions run to 'pending_approval'.
    On failure: transitions run to 'failed_validation' and records validation_errors.
    """
    tenant = str(current_user.tenant_id)
    row = await pool.fetchrow(
        "SELECT id, run_id FROM change_proposals WHERE id = $1 AND tenant_id = $2",
        proposal_id,
        tenant,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")

    errors: dict[str, str] = {}
    diff = body.unified_diff.strip()
    if not any(diff.startswith(prefix) for prefix in ("---", "diff", "@@", "+")):
        errors["unified_diff"] = (
            "Must be a valid unified diff (first line should start with ---, diff, @@, or +)"
        )
    if not body.rationale_md.strip():
        errors["rationale_md"] = "Rationale must not be empty"
    if not body.resource_addresses:
        errors["resource_addresses"] = "At least one resource address is required"

    if errors:
        await pool.execute(
            "UPDATE agent_workflow_runs SET workflow_state = 'failed_validation', updated_at = NOW() WHERE id = $1",
            row["run_id"],
        )
        await pool.execute(
            "UPDATE change_proposals SET validation_errors = $1, updated_at = NOW() WHERE id = $2",
            errors,
            proposal_id,
        )
    else:
        await pool.execute(
            "UPDATE agent_workflow_runs SET workflow_state = 'pending_approval', updated_at = NOW() WHERE id = $1",
            row["run_id"],
        )
        await pool.execute(
            "UPDATE change_proposals SET validation_errors = NULL, updated_at = NOW() WHERE id = $1",
            proposal_id,
        )

    updated = await pool.fetchrow(
        """SELECT id, run_id, unified_diff, rationale_md, resource_addresses, risk_level,
                  validation_errors, decided_by, decided_at, created_at
           FROM change_proposals WHERE id = $1""",
        proposal_id,
    )
    return _row_to_proposal(updated)


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalItem)
async def approve_proposal(
    proposal_id: UUID,
    body: DecisionBody,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ProposalItem:
    """Approve a change proposal → run transitions to 'approved', audit event written."""
    return await _decide_proposal(proposal_id, "approved", body, current_user, pool)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalItem)
async def reject_proposal(
    proposal_id: UUID,
    body: DecisionBody,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ProposalItem:
    """Reject a change proposal → run transitions to 'rejected', audit event written."""
    return await _decide_proposal(proposal_id, "rejected", body, current_user, pool)


@router.post("/proposals/{proposal_id}/export", response_model=ExportResponse)
async def export_proposal(
    proposal_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ExportResponse:
    """Export a proposal as a PR-ready artifact: title, body, patch file, and git apply instructions."""
    row = await pool.fetchrow(
        """SELECT cp.id, cp.run_id, cp.unified_diff, cp.rationale_md, cp.resource_addresses,
                  cp.risk_level, cp.decided_by, awr.session_type, awr.workflow_state
           FROM change_proposals cp
           JOIN agent_workflow_runs awr ON awr.id = cp.run_id
           WHERE cp.id = $1 AND cp.tenant_id = $2""",
        proposal_id,
        str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")

    addrs = row["resource_addresses"] or []
    if not isinstance(addrs, list):
        addrs = list(addrs)

    risk = row["risk_level"] or "medium"
    resource_list = "\n".join(f"- `{a}`" for a in addrs) if addrs else "- *(not specified)*"

    pr_title = f"fix(infra): remediate {len(addrs)} resource(s) — risk:{risk}"
    pr_body = f"""## Infra Remediation Proposal

**Risk level:** `{risk}`
**Session type:** `{row["session_type"]}`
**Proposal ID:** `{proposal_id}`

### Resources addressed

{resource_list}

### Rationale

{row["rationale_md"] or "*No rationale provided.*"}

### Changes

```diff
{row["unified_diff"]}
```

---
*Generated by Allergo Nordic governance platform. Review diff before applying.*
"""
    patch_filename = f"remediation-{str(proposal_id)[:8]}.patch"
    git_instructions = f"""# Apply this patch locally
git checkout -b infra/remediation-{str(proposal_id)[:8]}
git apply {patch_filename}
git add -A
git commit -m "{pr_title}"
# Then open a PR against main
"""

    return ExportResponse(
        pr_title=pr_title,
        pr_body=pr_body,
        patch_filename=patch_filename,
        patch_content=row["unified_diff"],
        git_apply_instructions=git_instructions,
    )


# ── Context snapshots ─────────────────────────────────────────────────────────


@router.post(
    "/runs/{run_id}/context-snapshot",
    response_model=ContextSnapshotItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_context_snapshot(
    run_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ContextSnapshotItem:
    """Build a versioned infra context bundle and store it, then transition run to 'context_frozen'."""
    tenant = str(current_user.tenant_id)
    run_row = await pool.fetchrow(
        "SELECT id FROM agent_workflow_runs WHERE id = $1 AND tenant_id = $2",
        run_id,
        tenant,
    )
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    bundle = await build_context_bundle(pool=pool, run_id=run_id, tenant_id=tenant)
    snap_row = await pool.fetchrow(
        """INSERT INTO infra_context_snapshots (tenant_id, run_id, bundle_json)
           VALUES ($1, $2, $3)
           RETURNING id, run_id, bundle_json, created_at""",
        tenant,
        run_id,
        bundle,
    )
    await pool.execute(
        "UPDATE agent_workflow_runs SET workflow_state = 'context_frozen', updated_at = NOW() WHERE id = $1",
        run_id,
    )
    return _row_to_snapshot(snap_row)


@router.get("/snapshots/{snapshot_id}", response_model=ContextSnapshotItem)
async def get_context_snapshot(
    snapshot_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> ContextSnapshotItem:
    row = await pool.fetchrow(
        "SELECT id, run_id, bundle_json, created_at FROM infra_context_snapshots WHERE id = $1 AND tenant_id = $2",
        snapshot_id,
        str(current_user.tenant_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found.")
    return _row_to_snapshot(row)


# ── Shared decision helper ────────────────────────────────────────────────────


async def _decide_proposal(
    proposal_id: UUID,
    decision: Literal["approved", "rejected"],
    body: DecisionBody,
    current_user: AuthenticatedUser,
    pool: asyncpg.Pool,
) -> ProposalItem:
    tenant = str(current_user.tenant_id)
    now = datetime.now(timezone.utc)

    row = await pool.fetchrow(
        "SELECT id, run_id FROM change_proposals WHERE id = $1 AND tenant_id = $2",
        proposal_id,
        tenant,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")

    await pool.execute(
        "UPDATE change_proposals SET decided_by = $2, decided_at = $3, updated_at = NOW() WHERE id = $1",
        proposal_id,
        current_user.sub,
        now,
    )
    new_state = "approved" if decision == "approved" else "rejected"
    await pool.execute(
        "UPDATE agent_workflow_runs SET workflow_state = $2, updated_at = NOW() WHERE id = $1",
        row["run_id"],
        new_state,
    )

    await append_audit_event(
        pool,
        tenant_id=tenant,
        actor=current_user.sub,
        action=f"posture.proposal.{decision}",
        resource_type="change_proposal",
        resource_id=str(proposal_id),
        metadata={
            "run_id": str(row["run_id"]),
            "decision": decision,
            "reason": body.reason,
        },
    )

    updated = await pool.fetchrow(
        """SELECT id, run_id, unified_diff, rationale_md, resource_addresses, risk_level,
                  validation_errors, decided_by, decided_at, created_at
           FROM change_proposals WHERE id = $1""",
        proposal_id,
    )
    return _row_to_proposal(updated)


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _row_to_run(row: Any) -> RunItem:
    md = row["metadata_json"]
    if md is None:
        md = {}
    elif not isinstance(md, dict):
        md = dict(md)
    return RunItem(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        session_type=row["session_type"],
        workflow_state=row["workflow_state"],
        created_by=row["created_by"],
        tool_rounds_used=row["tool_rounds_used"],
        max_tool_rounds=row["max_tool_rounds"],
        metadata_json=md,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_proposal(row: Any) -> ProposalItem:
    errs = row["validation_errors"]
    if errs is not None and not isinstance(errs, dict):
        errs = dict(errs)
    addrs = row["resource_addresses"]
    if addrs is None:
        addrs = []
    elif not isinstance(addrs, list):
        addrs = list(addrs)
    return ProposalItem(
        id=str(row["id"]),
        run_id=str(row["run_id"]),
        unified_diff=row["unified_diff"],
        rationale_md=row["rationale_md"] or "",
        resource_addresses=addrs,
        risk_level=row["risk_level"],
        validation_errors=errs,
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        created_at=row["created_at"],
    )


def _row_to_snapshot(row: Any) -> ContextSnapshotItem:
    bundle = row["bundle_json"]
    if bundle is None:
        bundle = {}
    elif not isinstance(bundle, dict):
        bundle = dict(bundle)
    return ContextSnapshotItem(
        id=str(row["id"]),
        run_id=str(row["run_id"]) if row["run_id"] else None,
        bundle_json=bundle,
        created_at=row["created_at"],
    )
