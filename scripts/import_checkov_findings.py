#!/usr/bin/env python3
"""Import Checkov scan results into the infra_findings table.

Usage
-----
# After downloading the CI artifact, or pointing at a local file:
python scripts/import_checkov_findings.py \\
    --input checkov-results.json \\
    --tenant dev-tenant \\
    --source-scan-id "$(git rev-parse HEAD)"

Environment
-----------
DATABASE_URL   asyncpg-compatible postgres URL, e.g.
               postgresql://user:pass@localhost:5432/allergo
SOURCE_SCAN_ID Optional fallback scan identifier (overridden by --source-scan-id)
TENANT_ID      Optional fallback tenant (overridden by --tenant)

Notes
-----
- Severity is normalised to uppercase: CRITICAL / HIGH / MEDIUM / LOW / INFORMATIONAL.
- The script is idempotent: it generates a deterministic UUID from
  (tenant_id, rule_id, file_path, line_start) so re-runs don't create duplicate rows.
- On conflict (duplicate id) the existing row is left unchanged (DO NOTHING).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


def _severity(raw: str | None) -> str:
    if not raw:
        return "MEDIUM"
    mapped = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW",
        "info": "INFORMATIONAL",
        "informational": "INFORMATIONAL",
    }
    return mapped.get(raw.lower(), raw.upper())


def _deterministic_uuid(tenant_id: str, rule_id: str, file_path: str, line_start: int | None) -> str:
    """Stable UUID derived from (tenant, rule, file, line) so re-runs are idempotent."""
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace URL
    name = f"{tenant_id}:{rule_id}:{file_path}:{line_start}"
    return str(uuid.uuid5(namespace, name))


def _extract_failed_checks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Support both Checkov v2 (check_type/results) and v3 (list of check_type objects)."""
    results = data.get("results", {})
    if isinstance(results, dict):
        return results.get("failed_checks", [])
    # Wrapped format: list of {"check_type": ..., "results": {...}}
    if isinstance(data, list):
        checks = []
        for entry in data:
            checks.extend(entry.get("results", {}).get("failed_checks", []))
        return checks
    return []


def _build_rows(
    checks: list[dict[str, Any]],
    tenant_id: str,
    source_scan_id: str,
) -> list[tuple]:
    rows = []
    for c in checks:
        rule_id: str = c.get("check_id") or "UNKNOWN"
        title: str = c.get("check_name") or rule_id
        file_path: str | None = c.get("file_path") or c.get("repo_file_path")
        line_range: list[int] = c.get("file_line_range") or []
        line_start: int | None = line_range[0] if len(line_range) > 0 else None
        line_end: int | None = line_range[1] if len(line_range) > 1 else None
        severity: str = _severity(c.get("severity"))
        guideline: str | None = c.get("guideline")
        bc_check_id: str | None = c.get("bc_check_id")

        detail_json: dict[str, Any] = {
            "check_id": rule_id,
            "resource": c.get("resource"),
            "check_address": c.get("check_address"),
        }
        if guideline:
            detail_json["guideline"] = guideline
        if bc_check_id:
            detail_json["bc_check_id"] = bc_check_id
        if c.get("details"):
            detail_json["details"] = c["details"]

        remediation_hint: str | None = (
            f"See: {guideline}" if guideline else None
        )
        policy_pack_ref = "checkov@3.x / Azurerm"

        row_id = _deterministic_uuid(tenant_id, rule_id, file_path or "", line_start)

        rows.append((
            row_id,
            tenant_id,
            severity,
            rule_id,
            title,
            file_path,
            line_start,
            line_end,
            policy_pack_ref,
            remediation_hint,
            json.dumps(detail_json),
            source_scan_id,
        ))
    return rows


async def _import(
    database_url: str,
    rows: list[tuple],
) -> int:
    try:
        import asyncpg
    except ImportError:
        print("ERROR: asyncpg is not installed. Run: pip install asyncpg", file=sys.stderr)
        sys.exit(1)

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    inserted = 0
    async with pool.acquire() as conn:
        for row in rows:
            result = await conn.execute(
                """INSERT INTO infra_findings (
                       id, tenant_id, severity, rule_id, title, file_path,
                       line_start, line_end, policy_pack_ref, remediation_hint,
                       detail_json, source_scan_id
                   )
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12)
                   ON CONFLICT (id) DO NOTHING""",
                *row,
            )
            if result != "INSERT 0 0":
                inserted += 1
    await pool.close()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Checkov results into infra_findings")
    parser.add_argument("--input", required=True, help="Path to checkov-results.json")
    parser.add_argument(
        "--tenant",
        default=os.environ.get("TENANT_ID", "dev-tenant"),
        help="Tenant ID to associate findings with (default: dev-tenant)",
    )
    parser.add_argument(
        "--source-scan-id",
        default=os.environ.get("SOURCE_SCAN_ID", "local"),
        help="Identifier for this scan (git SHA, CI run id, etc.)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL connection URL (falls back to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print rows without writing to DB",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with input_path.open() as fh:
        data = json.load(fh)

    checks = _extract_failed_checks(data)
    if not checks:
        print("No failed checks found in input — nothing to import.")
        return

    rows = _build_rows(checks, args.tenant, args.source_scan_id)
    print(f"Parsed {len(rows)} finding(s) from {len(checks)} failed check(s).")

    if args.dry_run:
        for row in rows:
            print(f"  [{row[2]}] {row[3]} — {row[4]} ({row[5]}:{row[6]})")
        return

    if not args.database_url:
        print(
            "ERROR: --database-url is required (or set DATABASE_URL). "
            "Use --dry-run to inspect without a DB connection.",
            file=sys.stderr,
        )
        sys.exit(1)

    inserted = asyncio.run(_import(args.database_url, rows))
    print(f"Inserted {inserted} new finding(s) ({len(rows) - inserted} duplicate(s) skipped).")


if __name__ == "__main__":
    main()
