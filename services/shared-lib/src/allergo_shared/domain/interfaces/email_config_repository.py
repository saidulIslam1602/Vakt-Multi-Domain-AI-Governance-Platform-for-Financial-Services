"""Repository port for EmailIngestConfig persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from allergo_shared.domain.email_config import EmailIngestConfig


class IEmailConfigRepository(ABC):
    """Abstract repository for per-tenant email ingestion configurations.

    Implementations must:
    - Never return the raw decrypted password in any response.
    - Store imap_password_enc as AES-encrypted bytes.
    - Enforce tenant isolation (only return configs for the requesting tenant).
    """

    @abstractmethod
    async def get(self, tenant_id: str) -> EmailIngestConfig | None:
        """Return the email config for this tenant, or None if not configured."""

    @abstractmethod
    async def get_all_enabled(self) -> list[EmailIngestConfig]:
        """Return all enabled configs across all tenants (used by poller manager)."""

    @abstractmethod
    async def create(
        self,
        config: EmailIngestConfig,
        plain_password: str,
    ) -> EmailIngestConfig:
        """Persist a new config, encrypting plain_password before storage."""

    @abstractmethod
    async def update(
        self,
        tenant_id: str,
        *,
        imap_host: str | None = None,
        imap_port: int | None = None,
        imap_username: str | None = None,
        plain_password: str | None = None,
        imap_mailbox: str | None = None,
        use_ssl: bool | None = None,
        poll_interval_sec: int | None = None,
        enabled: bool | None = None,
        allowed_senders: str | None = None,
        blocked_senders: str | None = None,
        required_subject_kw: str | None = None,
        blocked_subject_kw: str | None = None,
        min_attachment_bytes: int | None = None,
        max_attachment_bytes: int | None = None,
    ) -> EmailIngestConfig:
        """Apply a partial update. Only non-None fields are changed."""

    @abstractmethod
    async def update_status(
        self,
        tenant_id: str,
        status: Literal["idle", "running", "error", "disabled"],
        status_message: str | None = None,
    ) -> None:
        """Update operational status reported by the poller manager."""

    @abstractmethod
    async def mark_polled(self, tenant_id: str) -> None:
        """Set last_polled_at = NOW() after a successful poll cycle."""

    @abstractmethod
    async def delete(self, tenant_id: str) -> bool:
        """Delete the config. Returns True if a row was deleted."""

    @abstractmethod
    async def decrypt_password(self, tenant_id: str) -> str:
        """Return the plaintext password for internal use by the poller.

        MUST NOT be exposed in any API response.
        Raises KeyError if no config exists for this tenant.
        """
