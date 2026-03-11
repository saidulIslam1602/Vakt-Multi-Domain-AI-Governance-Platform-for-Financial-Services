"""Async email notifier for alert events.

Sends plain-text + HTML notification emails via SMTP (aiosmtplib).
Called by the contract renewal scanner and evaluate_alerts() whenever
a rule's channels list includes "email".

Configuration (via env vars → Settings):
  SMTP_HOST          SMTP server hostname        (default: localhost)
  SMTP_PORT          SMTP server port            (default: 587)
  SMTP_USERNAME      SMTP login username         (default: "")
  SMTP_PASSWORD      SMTP login password         (default: "")
  SMTP_FROM_ADDRESS  From: header address        (default: noreply@allergo.no)
  SMTP_TO_ADDRESS    Recipient address           (required when email channel enabled)
  SMTP_USE_TLS       Use STARTTLS                (default: true)
"""

from __future__ import annotations

import textwrap
from datetime import date
from email.message import EmailMessage

from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)


async def send_alert_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    smtp_from: str,
    smtp_to: str,
    use_tls: bool,
    subject: str,
    body_text: str,
    body_html: str,
) -> None:
    """Send a single alert email.  Errors are logged and swallowed — never raises."""
    try:
        import aiosmtplib  # type: ignore[import]

        msg = EmailMessage()
        msg["From"] = smtp_from
        msg["To"] = smtp_to
        msg["Subject"] = subject
        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_username or None,
            password=smtp_password or None,
            start_tls=use_tls,
        )
        logger.info("alert_email_sent", to=smtp_to, subject=subject)
    except Exception:
        logger.exception("alert_email_failed", to=smtp_to, subject=subject)


# ── Contract-renewal specific email builder ───────────────────────────────────

def build_contract_renewal_email(
    *,
    vendor_name: str,
    contract_end_date: str,
    days_remaining: int,
    contract_value: str | None,
    document_id: str,
    renewal_clause: str | None,
    governing_law: str | None,
    milestone: str,
) -> tuple[str, str, str]:
    """Return (subject, plain_text, html) for a contract renewal notification."""

    urgency_label = _urgency_label(days_remaining)
    today_str = date.today().isoformat()

    subject = (
        f"[{urgency_label}] Contract renewal required — "
        f"{vendor_name} expires {contract_end_date} ({days_remaining}d remaining)"
    )

    renewal_note = (
        f"\nRenewal clause: {renewal_clause}" if renewal_clause
        else "\nNo renewal clause extracted — manual review recommended."
    )
    law_note = f"\nGoverning law: {governing_law}" if governing_law else ""
    value_note = f"\nContract value: {contract_value}" if contract_value else ""

    plain = textwrap.dedent(f"""\
        Allergo Nordic — Contract Renewal Alert
        ========================================
        Urgency   : {urgency_label}
        Generated : {today_str}

        A contract is approaching its expiry date and requires action.

        Vendor          : {vendor_name}
        Contract end    : {contract_end_date}
        Days remaining  : {days_remaining}{value_note}{renewal_note}{law_note}

        Document ID     : {document_id}

        ── What to do ────────────────────────────────────────────
        1. Log in to Allergo Nordic and open the document.
        2. Review the renewal / termination clause.
        3. Initiate renewal discussions with the vendor BEFORE the
           expiry date to avoid automatic roll-over or service gap.
        ──────────────────────────────────────────────────────────

        This is an automated notification from Allergo Nordic.
        You can manage your alert rules at /alerts.
    """)

    color = _urgency_color(days_remaining)
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Contract Renewal Alert</title></head>
<body style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:8px;
              border:1px solid #e2e8f0;overflow:hidden;">

    <!-- Header -->
    <div style="background:{color};padding:20px 24px;">
      <h1 style="margin:0;color:#fff;font-size:18px;font-weight:700;">
        ⚠️ Contract Renewal Required — {urgency_label}
      </h1>
      <p style="margin:4px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">
        Generated {today_str} by Allergo Nordic
      </p>
    </div>

    <!-- Body -->
    <div style="padding:24px;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr><td style="padding:6px 0;color:#64748b;width:40%;">Vendor</td>
            <td style="padding:6px 0;font-weight:600;color:#0f172a;">{vendor_name}</td></tr>
        <tr><td style="padding:6px 0;color:#64748b;">Contract end date</td>
            <td style="padding:6px 0;font-weight:600;color:{color};">{contract_end_date}</td></tr>
        <tr><td style="padding:6px 0;color:#64748b;">Days remaining</td>
            <td style="padding:6px 0;font-weight:700;color:{color};">{days_remaining} days</td></tr>
        {"<tr><td style='padding:6px 0;color:#64748b;'>Contract value</td>"
          f"<td style='padding:6px 0;color:#0f172a;'>{contract_value}</td></tr>" if contract_value else ""}
        <tr><td style="padding:6px 0;color:#64748b;">Document ID</td>
            <td style="padding:6px 0;font-family:monospace;font-size:12px;color:#64748b;">
              {document_id}</td></tr>
      </table>

      {"<div style='margin:16px 0;padding:12px;background:#fef9c3;border-left:3px solid #eab308;"
       "border-radius:4px;font-size:13px;color:#713f12;'>"
       f"<strong>Renewal clause:</strong> {renewal_clause}</div>" if renewal_clause else
       "<div style='margin:16px 0;padding:12px;background:#fee2e2;border-left:3px solid #ef4444;"
       "border-radius:4px;font-size:13px;color:#7f1d1d;'>"
       "⚠️ No renewal clause was extracted — manual review is strongly recommended.</div>"}

      <!-- Action steps -->
      <div style="margin-top:20px;padding:16px;background:#f1f5f9;border-radius:6px;">
        <p style="margin:0 0 8px;font-weight:600;font-size:13px;color:#334155;">
          Recommended actions:
        </p>
        <ol style="margin:0;padding-left:20px;font-size:13px;color:#475569;line-height:1.7;">
          <li>Open the contract in Allergo Nordic to review all terms.</li>
          <li>Contact <strong>{vendor_name}</strong> to initiate renewal negotiations.</li>
          <li>Confirm or update the contract end date once renewed.</li>
        </ol>
      </div>
    </div>

    <!-- Footer -->
    <div style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;
                font-size:11px;color:#94a3b8;">
      Automated alert from Allergo Nordic · Manage rules at <em>/alerts</em>
    </div>
  </div>
</body>
</html>"""

    return subject, plain, html


def _urgency_label(days: int) -> str:
    if days <= 7:
        return "CRITICAL"
    if days <= 14:
        return "URGENT"
    if days <= 30:
        return "HIGH"
    return "NOTICE"


def _urgency_color(days: int) -> str:
    if days <= 7:
        return "#dc2626"   # red-600
    if days <= 14:
        return "#ea580c"   # orange-600
    if days <= 30:
        return "#d97706"   # amber-600
    return "#2563eb"       # blue-600
