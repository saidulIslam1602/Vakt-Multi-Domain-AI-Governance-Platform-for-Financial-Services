"""EmailIngestConfig domain entity.

Represents a tenant's IMAP email ingestion configuration.  The raw IMAP
password is NEVER held in plain-text beyond the request boundary — the
domain model carries either the encrypted blob (from the DB) or a sentinel
value indicating no change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal


class EmailIngestConfig:
    """Domain entity: a tenant's IMAP email ingestion configuration.

    Attributes
    ----------
    id:                  UUID primary key (str)
    tenant_id:           Allergo tenant identifier
    imap_host:           IMAP server hostname
    imap_port:           TCP port (993 = SSL, 143 = STARTTLS)
    imap_username:       Email address / login username
    imap_password_enc:   AES-encrypted password bytes from DB; None when creating
    imap_mailbox:        Folder to monitor (default INBOX)
    use_ssl:             True = SSL/TLS on connect; False = STARTTLS
    poll_interval_sec:   Seconds between poll cycles (≥ 60)
    enabled:             Soft toggle without deleting the config
    status:              Operational state reported by the running poller
    status_message:      Error detail when status == 'error'
    last_polled_at:      Timestamp of the most recent successful poll cycle
    allowed_senders:     CSV of trusted sender addresses/domains
    blocked_senders:     CSV of always-blocked sender addresses/domains
    required_subject_kw: CSV of keywords ALL of which must appear in subject
    blocked_subject_kw:  CSV of keywords ANY of which causes the email to skip
    min_attachment_bytes: Minimum attachment size in bytes
    max_attachment_bytes: Maximum attachment size in bytes
    created_at:          Creation timestamp
    updated_at:          Last-modified timestamp
    """

    # Valid status values — matches the DB CHECK constraint
    VALID_STATUSES: frozenset[str] = frozenset({"idle", "running", "error", "disabled"})

    def __init__(
        self,
        *,
        id: str,  # noqa: A002
        tenant_id: str,
        imap_host: str,
        imap_port: int = 993,
        imap_username: str,
        imap_password_enc: bytes | None = None,
        imap_mailbox: str = "INBOX",
        use_ssl: bool = True,
        poll_interval_sec: int = 300,
        enabled: bool = True,
        status: Literal["idle", "running", "error", "disabled"] = "idle",
        status_message: str | None = None,
        last_polled_at: datetime | None = None,
        allowed_senders: str = "",
        blocked_senders: str = "",
        required_subject_kw: str = "",
        blocked_subject_kw: str = "",
        min_attachment_bytes: int = 1024,
        max_attachment_bytes: int = 52_428_800,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_username = imap_username
        self.imap_password_enc = imap_password_enc
        self.imap_mailbox = imap_mailbox
        self.use_ssl = use_ssl
        self.poll_interval_sec = poll_interval_sec
        self.enabled = enabled
        self.status = status
        self.status_message = status_message
        self.last_polled_at = last_polled_at
        self.allowed_senders = allowed_senders
        self.blocked_senders = blocked_senders
        self.required_subject_kw = required_subject_kw
        self.blocked_subject_kw = blocked_subject_kw
        self.min_attachment_bytes = min_attachment_bytes
        self.max_attachment_bytes = max_attachment_bytes
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Raise ValueError for any business-rule violation."""
        if not self.imap_host.strip():
            raise ValueError("imap_host must not be empty.")
        if not (1 <= self.imap_port <= 65535):
            raise ValueError(f"imap_port {self.imap_port} is out of range 1–65535.")
        if not self.imap_username.strip():
            raise ValueError("imap_username must not be empty.")
        if self.poll_interval_sec < 60:
            raise ValueError("poll_interval_sec must be at least 60.")
        if self.min_attachment_bytes < 0:
            raise ValueError("min_attachment_bytes must be ≥ 0.")
        if self.max_attachment_bytes < 1:
            raise ValueError("max_attachment_bytes must be > 0.")
        if self.min_attachment_bytes > self.max_attachment_bytes:
            raise ValueError("min_attachment_bytes must be ≤ max_attachment_bytes.")
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"status '{self.status}' is not a valid value.")

    def __repr__(self) -> str:
        return (
            f"EmailIngestConfig(id={self.id!r}, tenant_id={self.tenant_id!r}, "
            f"host={self.imap_host!r}, username={self.imap_username!r}, "
            f"enabled={self.enabled}, status={self.status!r})"
        )
