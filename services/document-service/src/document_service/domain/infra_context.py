"""Infra context bundle builder for M4.

Merges findings, pipeline_runs, and plan summary fixture into a versioned
bundle_json that is stored in infra_context_snapshots and read back by the
chat agent tool get_infra_context_bundle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

# Path to the fixture plan summary — resolved relative to this file so it works
# regardless of CWD. Falls back gracefully when the fixture is absent.
_FIXTURE_DIR = Path(__file__).parent.parent.parent.parent.parent.parent.parent / "fixtures"
_PLAN_FIXTURE = _FIXTURE_DIR / "terraform-plan-sample.json"


def _load_plan_fixture() -> dict[str, Any]:
    """Load terraform-plan-sample.json from fixtures/, returning {} if absent."""
    try:
        if _PLAN_FIXTURE.exists():
            with _PLAN_FIXTURE.open() as fh:
                return json.load(fh)
    except Exception:
        pass
    return {}


async def build_context_bundle(
    pool: asyncpg.Pool,
    run_id: UUID,
    tenant_id: str,
) -> dict[str, Any]:
    """Build a versioned context bundle for a workflow run.

    Merges:
    - recent infra_findings (up to 50) for the tenant
    - the most recent pipeline_run for the tenant
    - terraform plan summary from fixture JSON
    - metadata about the run itself

    Returns a plain dict suitable for JSONB storage.
    """
    # Findings
    finding_rows = await pool.fetch(
        """SELECT id, severity, rule_id, title, file_path, line_start, line_end,
                  policy_pack_ref, remediation_hint, source_scan_id, created_at
           FROM infra_findings
           WHERE tenant_id = $1
           ORDER BY created_at DESC
           LIMIT 50""",
        tenant_id,
    )
    findings = [
        {
            "id": str(r["id"]),
            "severity": r["severity"],
            "rule_id": r["rule_id"],
            "title": r["title"],
            "file_path": r["file_path"],
            "line_start": r["line_start"],
            "policy_pack_ref": r["policy_pack_ref"],
            "remediation_hint": r["remediation_hint"],
            "source_scan_id": r["source_scan_id"],
        }
        for r in finding_rows
    ]

    # Most recent pipeline run
    pipeline_row = await pool.fetchrow(
        """SELECT id, workflow, conclusion, sha, triggered_at, metadata_json
           FROM pipeline_runs
           WHERE tenant_id = $1
           ORDER BY triggered_at DESC
           LIMIT 1""",
        tenant_id,
    )
    pipeline_summary: dict[str, Any] | None = None
    if pipeline_row:
        meta = pipeline_row["metadata_json"]
        if meta is not None and not isinstance(meta, dict):
            meta = dict(meta)
        pipeline_summary = {
            "id": str(pipeline_row["id"]),
            "workflow": pipeline_row["workflow"],
            "conclusion": pipeline_row["conclusion"],
            "sha": pipeline_row["sha"],
            "triggered_at": pipeline_row["triggered_at"].isoformat()
            if pipeline_row["triggered_at"]
            else None,
            "metadata": meta or {},
        }

    # Terraform plan from fixture
    plan_data = _load_plan_fixture()
    plan_summary: dict[str, Any] = {}
    if plan_data:
        changes = plan_data.get("resource_changes", [])
        plan_summary = {
            "source": "fixture",
            "resource_changes_count": len(changes),
            "actions_summary": _summarise_plan_actions(changes),
            "format_version": plan_data.get("format_version"),
            "terraform_version": plan_data.get("terraform_version"),
        }

    return {
        "schema_version": "1",
        "run_id": str(run_id),
        "tenant_id": tenant_id,
        "findings": findings,
        "findings_count": len(findings),
        "pipeline_run": pipeline_summary,
        "terraform_plan_summary": plan_summary,
        "policy_pack_refs": list({f["policy_pack_ref"] for f in findings if f["policy_pack_ref"]}),
    }


def _summarise_plan_actions(resource_changes: list[dict[str, Any]]) -> dict[str, int]:
    """Count create/update/delete/no-op actions from plan resource_changes."""
    counts: dict[str, int] = {"create": 0, "update": 0, "delete": 0, "no-op": 0, "other": 0}
    for rc in resource_changes:
        actions: list[str] = rc.get("change", {}).get("actions", [])
        if not actions or actions == ["no-op"]:
            counts["no-op"] += 1
        elif "delete" in actions and "create" in actions:
            counts["create"] += 1  # replace = delete+create
        elif "delete" in actions:
            counts["delete"] += 1
        elif "create" in actions:
            counts["create"] += 1
        elif "update" in actions:
            counts["update"] += 1
        else:
            counts["other"] += 1
    return {k: v for k, v in counts.items() if v > 0}
