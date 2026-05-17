"""Asyncpg-backed reader for the banking compliance domain.

Queries the three tables introduced in migration 014_banking_compliance.sql:
  - transaction_records  — demo transaction data with risk scoring
  - compliance_flags     — AML/KYC flags pending human review
  - sar_drafts           — SAR narrative drafts pending approval

All queries are tenant-scoped and fully parameterised.  No ORM — direct
asyncpg to keep latency predictable on hot paths and remain consistent
with FinancialDbReader's approach.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)


class BankingDbReader:
    """Read/write access for the banking compliance tables.

    The instance holds a reference to a shared asyncpg pool; it does not
    own the pool lifecycle — that is managed by the chat-service lifespan.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── AML flag queries ──────────────────────────────────────────────────────

    async def get_aml_flags(
        self,
        tenant_id: str,
        risk_level: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return open compliance flags, optionally filtered by minimum risk level."""
        risk_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

        query = """
            SELECT
                id::text,
                transaction_id,
                flag_reason,
                evidence_json,
                risk_level,
                status,
                created_by,
                created_at::text,
                reviewed_by,
                reviewed_at::text
            FROM compliance_flags
            WHERE tenant_id = $1
              AND status = 'open'
            ORDER BY
                CASE risk_level
                    WHEN 'CRITICAL' THEN 4
                    WHEN 'HIGH'     THEN 3
                    WHEN 'MEDIUM'   THEN 2
                    ELSE 1
                END DESC,
                created_at DESC
            LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, limit)

        records = [dict(r) for r in rows]

        # Apply risk_level filter in Python — simpler than dynamic SQL
        if risk_level and risk_level in risk_order:
            min_rank = risk_order[risk_level]
            records = [r for r in records if risk_order.get(r.get("risk_level", "LOW"), 1) >= min_rank]

        logger.debug("aml_flags_fetched", tenant_id=tenant_id, count=len(records))
        return records

    # ── KYC queries ───────────────────────────────────────────────────────────

    async def get_kyc_pending(
        self,
        tenant_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return customers with expired or pending KYC status."""
        query = """
            SELECT
                id::text,
                counterparty           AS customer_id,
                kyc_status,
                risk_score,
                pep_flag,
                timestamp::text        AS last_transaction_at
            FROM transaction_records
            WHERE tenant_id = $1
              AND kyc_status IN ('expired', 'pending')
            GROUP BY id, counterparty, kyc_status, risk_score, pep_flag, timestamp
            ORDER BY risk_score DESC, timestamp DESC
            LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, limit)
        return [dict(r) for r in rows]

    # ── SAR candidate queries ─────────────────────────────────────────────────

    async def get_sar_candidates(
        self,
        tenant_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return transactions above the CTR threshold (NOK 100,000) or with elevated risk scores.

        These are candidates for SAR review — not automatic SAR filings.
        """
        params: list[Any] = [tenant_id, 100_000.0]
        conditions = ["tenant_id = $1", "(amount_nok >= $2 OR risk_score >= 70)"]
        idx = 3

        if date_from:
            conditions.append(f"timestamp >= ${idx}::date")
            params.append(date_from)
            idx += 1
        if date_to:
            conditions.append(f"timestamp <= ${idx}::date")
            params.append(date_to)
            idx += 1

        params.append(limit)
        where = " AND ".join(conditions)
        query = f"""
            SELECT
                id::text,
                amount_nok,
                counterparty,
                timestamp::text,
                risk_score,
                kyc_status,
                pep_flag,
                CASE
                    WHEN amount_nok >= 100000 THEN 'ctr_threshold_breach'
                    WHEN risk_score >= 85     THEN 'high_risk_score'
                    WHEN pep_flag = true      THEN 'pep_counterparty'
                    ELSE 'elevated_risk'
                END AS candidate_reason
            FROM transaction_records
            WHERE {where}
            ORDER BY risk_score DESC, amount_nok DESC
            LIMIT ${idx}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    # ── Risk score summary ────────────────────────────────────────────────────

    async def get_risk_score_summary(self, tenant_id: str) -> dict[str, Any]:
        """Aggregate risk score distribution across the transaction portfolio."""
        query = """
            SELECT
                COUNT(*)                                                    AS total_transactions,
                COUNT(*) FILTER (WHERE risk_score >= 85)                   AS critical_risk_count,
                COUNT(*) FILTER (WHERE risk_score >= 70 AND risk_score < 85) AS high_risk_count,
                COUNT(*) FILTER (WHERE risk_score >= 40 AND risk_score < 70) AS medium_risk_count,
                COUNT(*) FILTER (WHERE risk_score < 40)                    AS low_risk_count,
                COUNT(*) FILTER (WHERE pep_flag = true)                    AS pep_flagged_count,
                COUNT(*) FILTER (WHERE kyc_status IN ('expired', 'pending')) AS kyc_issues_count,
                ROUND(AVG(risk_score)::numeric, 2)                         AS avg_risk_score,
                COUNT(*) FILTER (WHERE amount_nok >= 100000)               AS above_ctr_threshold_count
            FROM transaction_records
            WHERE tenant_id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, tenant_id)
        return dict(row) if row else {}

    # ── Regulatory calendar ───────────────────────────────────────────────────

    async def get_regulatory_calendar(self, tenant_id: str) -> list[dict[str, Any]]:
        """Return upcoming Finanstilsynet reporting deadlines from the compliance_flags table.

        In production this would query a dedicated regulatory_deadlines table.
        For demo purposes, derives deadlines from open flags by reporting obligation type.
        """
        # Return static regulatory deadlines relevant to Norwegian AML compliance.
        # In a production system these would be tenant-specific and stored in a DB table.
        from datetime import date, timedelta

        today = date.today()
        return [
            {
                "obligation": "Monthly AML statistical report",
                "regulator": "Finanstilsynet",
                "legal_basis": "Norwegian AML Act §31",
                "due_date": (today.replace(day=1) + timedelta(days=32)).replace(day=5).isoformat(),
                "status": "upcoming",
            },
            {
                "obligation": "Annual KYC refresh — high-risk customers",
                "regulator": "Finanstilsynet",
                "legal_basis": "Norwegian AML Act §24",
                "due_date": today.replace(month=12, day=31).isoformat(),
                "status": "upcoming",
            },
            {
                "obligation": "PSD2 SCA exemption threshold review",
                "regulator": "Finanstilsynet",
                "legal_basis": "PSD2 Art. 98 RTS",
                "due_date": (today + timedelta(days=90)).isoformat(),
                "status": "upcoming",
            },
            {
                "obligation": "FATF risk-based assessment update",
                "regulator": "FATF / EBA",
                "legal_basis": "FATF Recommendation 1",
                "due_date": today.replace(month=6, day=30).isoformat()
                if today.month <= 6
                else today.replace(month=12, day=31).isoformat(),
                "status": "upcoming",
            },
        ]

    # ── PEP screening ─────────────────────────────────────────────────────────

    async def get_pep_screening_results(
        self,
        tenant_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return transactions with PEP-flagged counterparties pending review."""
        query = """
            SELECT
                id::text,
                counterparty,
                amount_nok,
                timestamp::text,
                risk_score,
                kyc_status
            FROM transaction_records
            WHERE tenant_id = $1
              AND pep_flag = true
            ORDER BY risk_score DESC, amount_nok DESC
            LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, limit)
        return [dict(r) for r in rows]

    # ── Write operations ──────────────────────────────────────────────────────

    async def create_compliance_flag(
        self,
        tenant_id: str,
        transaction_id: str,
        flag_reason: str,
        evidence_json: dict[str, Any],
        created_by: str,
    ) -> str:
        """Insert a compliance flag record and return the new flag ID."""
        import json

        flag_id = str(uuid.uuid4())
        query = """
            INSERT INTO compliance_flags
                (id, tenant_id, transaction_id, flag_reason, evidence_json, status, created_by)
            VALUES
                ($1, $2, $3, $4, $5::jsonb, 'open', $6)
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                flag_id,
                tenant_id,
                transaction_id,
                flag_reason,
                json.dumps(evidence_json),
                created_by,
            )
        logger.info("compliance_flag_created", flag_id=flag_id, tenant_id=tenant_id)
        return flag_id

    async def create_sar_draft(
        self,
        tenant_id: str,
        narrative_md: str,
        source_flag_ids: list[str],
        reporting_obligation: str = "discretionary",
    ) -> str:
        """Insert a SAR draft record and return the new draft ID."""
        import json

        draft_id = str(uuid.uuid4())
        query = """
            INSERT INTO sar_drafts
                (id, tenant_id, narrative_md, source_flag_ids, reporting_obligation, status)
            VALUES
                ($1, $2, $3, $4::jsonb, $5, 'pending_review')
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                draft_id,
                tenant_id,
                narrative_md,
                json.dumps(source_flag_ids),
                reporting_obligation,
            )
        logger.info("sar_draft_created", draft_id=draft_id, tenant_id=tenant_id)
        return draft_id
