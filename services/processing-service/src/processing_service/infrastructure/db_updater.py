"""DB status updater — writes document status transitions to PostgreSQL."""

from __future__ import annotations

from datetime import datetime

import asyncpg

from allergo_shared.domain.entities import ExtractionResult
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)


class DocumentStatusUpdater:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def mark_parsing(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="parsing")

    async def mark_parsed(
        self,
        document_id: str,
        tenant_id: str,
        raw_text_path: str,
        page_count: int,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = 'parsed', raw_text_path = $3, page_count = $4, updated_at = $5
                   WHERE id = $1 AND tenant_id = $2""",
                document_id, tenant_id, raw_text_path, page_count, datetime.utcnow(),
            )

    async def mark_extracting(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="extracting")

    async def mark_extracted(
        self, document_id: str, tenant_id: str, extraction: ExtractionResult
    ) -> None:
        from processing_service.infrastructure.llm_extractor import CONFIDENCE_REVIEW_THRESHOLD
        needs_review = (
            extraction.confidence_score < CONFIDENCE_REVIEW_THRESHOLD
            or extraction.approval_required
        )
        review_status = "pending_review" if needs_review else "not_required"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = 'extracted',
                       extraction = $3,
                       needs_review = $4,
                       review_status = $5,
                       updated_at = $6
                   WHERE id = $1 AND tenant_id = $2""",
                document_id,
                tenant_id,
                extraction.model_dump_json(),
                needs_review,
                review_status,
                datetime.utcnow(),
            )

    async def mark_indexing(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="indexing")

    async def mark_ready(self, document_id: str, tenant_id: str) -> None:
        await self._update(document_id, tenant_id, status="ready")

    async def mark_failed(self, document_id: str, tenant_id: str, error: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = 'failed', error_message = $3, updated_at = $4
                   WHERE id = $1 AND tenant_id = $2""",
                document_id, tenant_id, error, datetime.utcnow(),
            )

    async def evaluate_alerts(
        self, document_id: str, tenant_id: str, extraction: "ExtractionResult"
    ) -> None:
        """Evaluate all enabled alert rules for this tenant against a newly extracted document.

        Inserts alert_events rows for every rule whose condition fires.
        Designed to be called after mark_extracted — failures are logged but never re-raise.
        """
        try:
            async with self._pool.acquire() as conn:
                rules = await conn.fetch(
                    """SELECT rule_id, trigger_type, threshold_value, days_before, document_category
                       FROM alert_rules
                       WHERE tenant_id = $1 AND enabled = true""",
                    tenant_id,
                )
                for rule in rules:
                    cat_filter = rule["document_category"]
                    if cat_filter and extraction.document_category != cat_filter:
                        continue
                    fired, message = _check_rule(rule, extraction)
                    if fired:
                        await conn.execute(
                            """INSERT INTO alert_events
                               (tenant_id, rule_id, document_id, trigger_type, message, metadata)
                               VALUES ($1, $2, $3, $4, $5, $6)""",
                            tenant_id,
                            rule["rule_id"],
                            document_id,
                            rule["trigger_type"],
                            message,
                            {
                                "vendor_name": extraction.vendor_name,
                                "total_amount": extraction.total_amount,
                                "document_category": extraction.document_category,
                                "confidence_score": extraction.confidence_score,
                                "legal_risk_flag": extraction.legal_risk_flag,
                                "contract_end_date": extraction.contract_end_date,
                            },
                        )
                        logger.info(
                            "alert_fired",
                            rule_id=str(rule["rule_id"]),
                            trigger_type=rule["trigger_type"],
                            document_id=document_id,
                        )
        except Exception:
            logger.exception("alert_evaluation_failed", document_id=document_id)

    async def _update(self, document_id: str, tenant_id: str, status: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE documents
                   SET status = $3, updated_at = $4
                   WHERE id = $1 AND tenant_id = $2""",
                document_id, tenant_id, status, datetime.utcnow(),
            )


def _check_rule(rule: dict, extraction: "ExtractionResult") -> tuple[bool, str]:  # type: ignore[name-defined]
    """Return (fired, message) for a single alert rule against an extraction result."""
    from datetime import date

    trigger = rule["trigger_type"]

    if trigger == "legal_risk":
        if extraction.legal_risk_flag:
            return True, (
                f"Legal risk flag detected in document "
                f"(vendor: {extraction.vendor_name or 'unknown'})."
            )

    elif trigger == "low_confidence":
        threshold = float(rule["threshold_value"] or 0.70)
        if extraction.confidence_score < threshold:
            return True, (
                f"Low extraction confidence ({extraction.confidence_score:.0%}) "
                f"for {extraction.document_category or 'document'} "
                f"(vendor: {extraction.vendor_name or 'unknown'})."
            )

    elif trigger == "invoice_amount_threshold":
        threshold = float(rule["threshold_value"] or 0)
        amount_str = extraction.total_amount or ""
        # Extract numeric part — strip currency symbols/commas
        import re
        nums = re.findall(r"[\d,]+\.?\d*", amount_str.replace("\u00a0", "").replace(" ", ""))
        if nums:
            try:
                amount = float(nums[0].replace(",", ""))
                if amount >= threshold:
                    return True, (
                        f"Invoice {extraction.invoice_number or ''} total "
                        f"{extraction.total_amount} exceeds threshold "
                        f"NOK {threshold:,.0f} "
                        f"(vendor: {extraction.vendor_name or 'unknown'})."
                    )
            except ValueError:
                pass

    elif trigger == "contract_expiring":
        days = int(rule["days_before"] or 30)
        end_date_str = extraction.contract_end_date
        if end_date_str:
            try:
                end = date.fromisoformat(end_date_str)
                delta = (end - date.today()).days
                if 0 <= delta <= days:
                    return True, (
                        f"Contract expiring in {delta} day(s) on {end_date_str} "
                        f"(vendor: {extraction.vendor_name or 'unknown'}, "
                        f"value: {extraction.contract_value or 'N/A'})."
                    )
            except ValueError:
                pass

    elif trigger == "invoice_overdue":
        due_date_str = extraction.due_date
        if due_date_str and extraction.document_category == "invoice":
            try:
                due = date.fromisoformat(due_date_str)
                if due < date.today():
                    return True, (
                        f"Invoice {extraction.invoice_number or ''} overdue "
                        f"since {due_date_str} "
                        f"(vendor: {extraction.vendor_name or 'unknown'}, "
                        f"amount: {extraction.total_amount or 'N/A'})."
                    )
            except ValueError:
                pass

    return False, ""
