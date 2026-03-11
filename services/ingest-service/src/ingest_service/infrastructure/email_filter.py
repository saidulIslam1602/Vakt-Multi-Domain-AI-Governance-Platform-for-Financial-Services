"""Email ingestion filter — decides whether an email or attachment should be ingested.

All filtering rules are pure Python with no I/O, making them fully unit-testable.

Filter layers (applied in order)
──────────────────────────────────
1. Sender allowlist   — if configured, only whitelisted addresses / domains pass
2. Sender blocklist   — explicit deny-override (evaluated even if allowlist is empty)
3. Subject blocklist  — skip newsletters, auto-replies, marketing mail, etc.
4. Subject keywords   — require certain keywords to appear (e.g. "invoice")
5. Attachment MIME    — only accept supported document types  (in email_poller)
6. Attachment size    — min / max byte limits per attachment

Every decision is returned as a ``FilterResult`` so the poller can log
the exact reason for a skip — giving the CFO an auditable trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import TYPE_CHECKING

from allergo_shared.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from allergo_shared.domain.email_config import EmailIngestConfig

logger = get_logger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class FilterResult:
    accepted: bool
    reason: str  # human-readable explanation shown in logs / audit

    @classmethod
    def ok(cls, reason: str = "accepted") -> FilterResult:
        return cls(accepted=True, reason=reason)

    @classmethod
    def reject(cls, reason: str) -> FilterResult:
        return cls(accepted=False, reason=reason)


# ── Filter configuration ──────────────────────────────────────────────────────

def _parse_csv(raw: str) -> list[str]:
    """Split a comma-separated env-var string into a cleaned list, ignoring empties."""
    return [tok.strip().lower() for tok in raw.split(",") if tok.strip()]


@dataclass
class EmailFilter:
    """Stateless filter built from ``Settings``.

    All string comparisons are case-insensitive.

    Parameters
    ──────────
    allowed_senders
        Trusted addresses (``vendor@acme.com``) or domains (``@acme.com``).
        Empty list → accept any sender.
    blocked_senders
        Always-reject addresses / domains — evaluated even when ``allowed_senders``
        is empty.  Acts as a deny-override.
    blocked_subject_keywords
        If ANY of these words/phrases appear in the subject, the email is skipped.
        Useful to drop newsletters, auto-replies, etc.
    required_subject_keywords
        ALL of these must appear in the subject for the email to be accepted.
        Useful to restrict ingestion to, e.g., ``["invoice"]`` or ``["contract"]``.
    min_attachment_bytes / max_attachment_bytes
        Per-attachment size guard.
    """

    allowed_senders: list[str] = field(default_factory=list)
    blocked_senders: list[str] = field(default_factory=list)
    blocked_subject_keywords: list[str] = field(default_factory=list)
    required_subject_keywords: list[str] = field(default_factory=list)
    min_attachment_bytes: int = 1_024
    max_attachment_bytes: int = 50 * 1_024 * 1_024

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_settings(cls, settings) -> EmailFilter:  # type: ignore[no-untyped-def]
        """Build an ``EmailFilter`` directly from a ``Settings`` instance."""
        return cls(
            allowed_senders=_parse_csv(settings.imap_allowed_senders),
            blocked_senders=_parse_csv(settings.imap_blocked_senders),
            blocked_subject_keywords=_parse_csv(settings.imap_blocked_subject_keywords),
            required_subject_keywords=_parse_csv(settings.imap_required_subject_keywords),
            min_attachment_bytes=settings.imap_min_attachment_bytes,
            max_attachment_bytes=settings.imap_max_attachment_bytes,
        )

    @classmethod
    def from_config(cls, config: EmailIngestConfig) -> EmailFilter:
        """Build an ``EmailFilter`` from a per-tenant ``EmailIngestConfig`` entity."""
        return cls(
            allowed_senders=_parse_csv(config.allowed_senders or ""),
            blocked_senders=_parse_csv(config.blocked_senders or ""),
            blocked_subject_keywords=_parse_csv(config.blocked_subject_kw or ""),
            required_subject_keywords=_parse_csv(config.required_subject_kw or ""),
            min_attachment_bytes=config.min_attachment_bytes,
            max_attachment_bytes=config.max_attachment_bytes,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def check_email(self, *, sender: str, subject: str) -> FilterResult:
        """Decide whether this email should be processed at all.

        Called once per email *before* extracting attachments.
        """
        _, addr = parseaddr(sender)           # "Name <addr@host.com>" → "addr@host.com"
        addr = addr.lower()
        subject_lower = subject.lower()

        # ── Layer 1: Sender allowlist ──────────────────────────────────────────
        if self.allowed_senders:
            if not self._sender_matches_any(addr, self.allowed_senders):
                return FilterResult.reject(
                    f"sender '{addr}' not in allowed_senders allowlist"
                )

        # ── Layer 2: Sender blocklist ──────────────────────────────────────────
        if self.blocked_senders:
            if self._sender_matches_any(addr, self.blocked_senders):
                return FilterResult.reject(
                    f"sender '{addr}' matched blocked_senders blocklist"
                )

        # ── Layer 3: Subject blocklist ─────────────────────────────────────────
        for kw in self.blocked_subject_keywords:
            if kw in subject_lower:
                return FilterResult.reject(
                    f"subject contains blocked keyword '{kw}'"
                )

        # ── Layer 4: Required subject keywords ────────────────────────────────
        for kw in self.required_subject_keywords:
            if kw not in subject_lower:
                return FilterResult.reject(
                    f"subject missing required keyword '{kw}'"
                )

        return FilterResult.ok(
            f"sender='{addr}' subject='{subject[:60]}' passed all email filters"
        )

    def check_attachment(self, *, filename: str, size_bytes: int) -> FilterResult:
        """Decide whether a specific attachment should be ingested.

        Called once per attachment after MIME type has already been validated
        by the poller's ``_extract_attachments`` method.
        """
        # ── Layer 5 (size): min guard ──────────────────────────────────────────
        if size_bytes < self.min_attachment_bytes:
            return FilterResult.reject(
                f"attachment '{filename}' too small "
                f"({size_bytes} B < {self.min_attachment_bytes} B min)"
            )

        # ── Layer 6 (size): max guard ──────────────────────────────────────────
        if size_bytes > self.max_attachment_bytes:
            return FilterResult.reject(
                f"attachment '{filename}' too large "
                f"({size_bytes} B > {self.max_attachment_bytes} B max)"
            )

        return FilterResult.ok(f"attachment '{filename}' ({size_bytes} B) accepted")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _sender_matches_any(addr: str, patterns: list[str]) -> bool:
        """Check addr against a list of exact addresses or @domain patterns."""
        for pattern in patterns:
            if pattern.startswith("@"):
                # Domain match — addr must end with @domain.tld
                if addr.endswith(pattern):
                    return True
            # Exact address match
            elif addr == pattern:
                return True
        return False
