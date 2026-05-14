"""Append-only audit logging for governance events."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import asyncpg


def _payload_hash(metadata: dict[str, Any]) -> str:
    canonical = json.dumps(metadata, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def append_audit_event(
    pool: asyncpg.Pool,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata: dict[str, Any],
) -> None:
    await pool.execute(
        """INSERT INTO audit_events (
               tenant_id, actor, action, resource_type, resource_id,
               payload_hash, metadata_json
           )
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        tenant_id,
        actor,
        action,
        resource_type,
        resource_id,
        _payload_hash(metadata),
        metadata,
    )
