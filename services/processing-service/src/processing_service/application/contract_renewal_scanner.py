"""Contract renewal scanner — proactive daily alert engine.

This scheduler runs once per day (default: 08:00 UTC) and scans every
``ready`` contract in the database against all enabled ``contract_expiring``
alert rules for each tenant.

Why this is needed
──────────────────
The existing ``evaluate_alerts()`` in ``db_updater.py`` only fires when a
document is *first* processed.  A contract uploaded months ago whose expiry
is now approaching will never trigger again without this scanner.

Milestone system
────────────────
Rather than sending one notification at a fixed offset, the scanner sends
alerts at multiple milestones as the deadline draws closer:

  Milestone  Fires when days_remaining <=  days_remaining >=
  ─────────  ──────────────────────────  ──────────────────
  60d        60                          31
  30d        30                          15
  14d        14                          8
  7d          7                           1
  0d          0 (expired today)          —

Each (rule_id, document_id, milestone) combination fires exactly ONCE,
enforced by the ``scheduled_alert_log`` table (migration 008).

The scanner honours every rule's ``days_before`` field as the outermost
window — milestones beyond that window are skipped.

Email delivery
──────────────
If a rule's ``channels`` array contains ``"email"`` AND SMTP is configured,
a rich HTML+text email is sent for every firing milestone.
"""

from __future__ import annotations

import json
from datetime import date

import asyncpg

from allergo_shared.infrastructure.logging import get_logger
from processing_service.infrastructure.config import Settings
from processing_service.infrastructure.email_notifier import (
    build_contract_renewal_email,
    send_alert_email,
)

logger = get_logger(__name__)

# Milestones: (label, upper_bound_days_remaining, lower_bound_days_remaining)
# The scanner fires a milestone when:
#   lower_bound <= days_remaining <= upper_bound
# A milestone is skipped entirely if its upper_bound > rule.days_before.
_MILESTONES: list[tuple[str, int, int]] = [
    ("60d", 60, 31),
    ("30d", 30, 15),
    ("14d", 14, 8),
    ("7d",   7,  1),
    ("0d",   0,  0),   # expired today
]


class ContractRenewalScanner:
    """Daily scanner for contract expiry alerts.

    Instantiated once in ``__main__.py`` and scheduled via APScheduler.
    """

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self._pool = pool
        self._cfg = settings

    # ── Public entry point ────────────────────────────────────────────────────

    async def run_scan(self) -> None:
        """Scan all tenants for expiring contracts and fire due alerts."""
        logger.info("contract_renewal_scan_started")
        try:
            await self._scan()
        except Exception:
            logger.exception("contract_renewal_scan_failed")
        logger.info("contract_renewal_scan_finished")

    # ── Internal scan logic ───────────────────────────────────────────────────

    async def _scan(self) -> None:
        async with self._pool.acquire() as conn:
            # Load all enabled contract_expiring rules (all tenants)
            rules = await conn.fetch(
                """SELECT rule_id, tenant_id, name, days_before, channels
                   FROM   alert_rules
                   WHERE  trigger_type = 'contract_expiring'
                   AND    enabled = true"""
            )

            if not rules:
                logger.info("contract_renewal_scan_no_rules")
                return

            for rule in rules:
                await self._process_rule(conn, rule)

    async def _process_rule(self, conn: asyncpg.Connection, rule: asyncpg.Record) -> None:
        rule_id    = str(rule["rule_id"])
        tenant_id  = rule["tenant_id"]
        days_before = int(rule["days_before"] or 60)   # default outer window: 60 days
        channels   = list(rule["channels"] or [])

        today = date.today()

        # Find every ready contract for this tenant that has a contract_end_date
        # within the rule's outer window (days_before days from today).
        contracts = await conn.fetch(
            """SELECT
                 id::text                                    AS document_id,
                 extraction->>'vendor_name'                  AS vendor_name,
                 extraction->>'contract_end_date'            AS contract_end_date,
                 extraction->>'contract_value'               AS contract_value,
                 extraction->>'renewal_clause'               AS renewal_clause,
                 extraction->>'governing_law'                AS governing_law,
                 extraction->>'contract_start_date'          AS contract_start_date
               FROM documents
               WHERE tenant_id          = $1
                 AND status             = 'ready'
                 AND extraction->>'document_category' IN ('contract', 'Contract')
                 AND extraction->>'contract_end_date' IS NOT NULL
                 AND (extraction->>'contract_end_date')::date
                       BETWEEN CURRENT_DATE AND (CURRENT_DATE + $2 * INTERVAL '1 day')
            """,
            tenant_id,
            days_before,
        )

        for contract in contracts:
            await self._evaluate_contract(
                conn=conn,
                rule_id=rule_id,
                rule_name=rule["name"],
                tenant_id=tenant_id,
                channels=channels,
                days_before=days_before,
                contract=contract,
                today=today,
            )

    async def _evaluate_contract(
        self,
        *,
        conn: asyncpg.Connection,
        rule_id: str,
        rule_name: str,
        tenant_id: str,
        channels: list[str],
        days_before: int,
        contract: asyncpg.Record,
        today: date,
    ) -> None:
        document_id      = contract["document_id"]
        end_date_str     = contract["contract_end_date"]
        vendor_name      = contract["vendor_name"] or "Unknown vendor"
        contract_value   = contract["contract_value"]
        renewal_clause   = contract["renewal_clause"]
        governing_law    = contract["governing_law"]

        try:
            end_date = date.fromisoformat(end_date_str)
        except (ValueError, TypeError):
            logger.warning(
                "contract_renewal_invalid_date",
                document_id=document_id,
                contract_end_date=end_date_str,
            )
            return

        days_remaining = (end_date - today).days

        for milestone_label, upper, lower in _MILESTONES:
            # Skip milestones that fall outside this rule's configured window
            if upper > days_before:
                continue

            # Is today within this milestone's firing window?
            if not (lower <= days_remaining <= upper):
                continue

            # Deduplication — skip if this milestone already fired
            already_fired = await conn.fetchval(
                """SELECT 1 FROM scheduled_alert_log
                   WHERE rule_id    = $1
                     AND document_id = $2::uuid
                     AND milestone  = $3""",
                rule_id,
                document_id,
                milestone_label,
            )
            if already_fired:
                continue

            # Build human-readable message
            if days_remaining == 0:
                message = (
                    f"Contract with {vendor_name} EXPIRED TODAY ({end_date_str}). "
                    f"Immediate action required."
                    + (f" Contract value: {contract_value}." if contract_value else "")
                )
            else:
                message = (
                    f"Contract renewal required — {vendor_name} expires in "
                    f"{days_remaining} day(s) on {end_date_str}."
                    + (f" Contract value: {contract_value}." if contract_value else "")
                    + (f" Renewal clause: {renewal_clause}." if renewal_clause else
                       " No renewal clause extracted — manual review recommended.")
                )

            metadata = {
                "vendor_name":        vendor_name,
                "contract_end_date":  end_date_str,
                "days_remaining":     days_remaining,
                "contract_value":     contract_value,
                "renewal_clause":     renewal_clause,
                "governing_law":      governing_law,
                "milestone":          milestone_label,
                "rule_name":          rule_name,
                "document_category":  "contract",
            }

            # Insert alert_event into the in-app feed
            await conn.execute(
                """INSERT INTO alert_events
                     (tenant_id, rule_id, document_id, trigger_type, message, metadata)
                   VALUES ($1, $2::uuid, $3::uuid, 'contract_expiring', $4, $5)""",
                tenant_id,
                rule_id,
                document_id,
                message,
                json.dumps(metadata),
            )

            # Mark milestone as fired — prevents re-firing on the next daily run
            await conn.execute(
                """INSERT INTO scheduled_alert_log
                     (tenant_id, rule_id, document_id, milestone)
                   VALUES ($1, $2::uuid, $3::uuid, $4)
                   ON CONFLICT (rule_id, document_id, milestone) DO NOTHING""",
                tenant_id,
                rule_id,
                document_id,
                milestone_label,
            )

            logger.info(
                "contract_renewal_alert_fired",
                rule_id=rule_id,
                document_id=document_id,
                vendor=vendor_name,
                days_remaining=days_remaining,
                milestone=milestone_label,
            )

            # Email delivery if the rule's channels include "email"
            if "email" in channels and self._cfg.smtp_to_address:
                subject, plain, html = build_contract_renewal_email(
                    vendor_name=vendor_name,
                    contract_end_date=end_date_str,
                    days_remaining=days_remaining,
                    contract_value=contract_value,
                    document_id=document_id,
                    renewal_clause=renewal_clause,
                    governing_law=governing_law,
                    milestone=milestone_label,
                )
                await send_alert_email(
                    smtp_host=self._cfg.smtp_host,
                    smtp_port=self._cfg.smtp_port,
                    smtp_username=self._cfg.smtp_username,
                    smtp_password=self._cfg.smtp_password,
                    smtp_from=self._cfg.smtp_from_address,
                    smtp_to=self._cfg.smtp_to_address,
                    use_tls=self._cfg.smtp_use_tls,
                    subject=subject,
                    body_text=plain,
                    body_html=html,
                )
