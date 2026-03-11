"""Application service: manage per-tenant email ingestion configuration.

Responsibilities
────────────────
• create  — register a new IMAP inbox for a tenant
• update  — patch connection/filter settings
• get     — return config with password masked
• delete  — remove config and stop the running poller
• test_connection — validate IMAP credentials without saving anything

The service is deliberately thin: it validates inputs, delegates persistence
to IEmailConfigRepository, then notifies the EmailPollerManager so running
pollers are updated without a service restart.
"""

from __future__ import annotations

import imaplib
import ssl
import uuid
from typing import TYPE_CHECKING

from allergo_shared.domain.email_config import EmailIngestConfig
from allergo_shared.domain.interfaces.email_config_repository import IEmailConfigRepository
from allergo_shared.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from ingest_service.infrastructure.email_poller_manager import EmailPollerManager

logger = get_logger(__name__)

_PASSWORD_MASK = "••••••••"


class ConflictError(Exception):
    """Raised when a tenant already has an email config."""


class NotFoundError(Exception):
    """Raised when no email config exists for the tenant."""


class EmailConfigService:
    """Orchestrates CRUD + live-sync for per-tenant email ingestion configs."""

    def __init__(
        self,
        repository: IEmailConfigRepository,
        poller_manager: EmailPollerManager,
    ) -> None:
        self._repo = repository
        self._manager = poller_manager

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get(self, tenant_id: str) -> dict:
        """Return the config with password masked. Raises NotFoundError if absent."""
        config = await self._repo.get(tenant_id)
        if config is None:
            raise NotFoundError(f"No email config for tenant {tenant_id!r}")
        return _mask(config)

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(
        self,
        tenant_id: str,
        *,
        imap_host: str,
        imap_port: int = 993,
        imap_username: str,
        plain_password: str,
        imap_mailbox: str = "INBOX",
        use_ssl: bool = True,
        poll_interval_sec: int = 300,
        enabled: bool = True,
        allowed_senders: str = "",
        blocked_senders: str = "",
        required_subject_kw: str = "",
        blocked_subject_kw: str = "",
        min_attachment_bytes: int = 1024,
        max_attachment_bytes: int = 52_428_800,
    ) -> dict:
        """Register a new IMAP inbox. Raises ConflictError if one already exists."""
        existing = await self._repo.get(tenant_id)
        if existing is not None:
            raise ConflictError(
                f"Tenant {tenant_id!r} already has an email config. "
                "Use PATCH /api/v1/email-config to update it."
            )

        config = EmailIngestConfig(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            imap_host=imap_host.strip(),
            imap_port=imap_port,
            imap_username=imap_username.strip(),
            imap_mailbox=imap_mailbox.strip(),
            use_ssl=use_ssl,
            poll_interval_sec=poll_interval_sec,
            enabled=enabled,
            status="idle",
            allowed_senders=allowed_senders,
            blocked_senders=blocked_senders,
            required_subject_kw=required_subject_kw,
            blocked_subject_kw=blocked_subject_kw,
            min_attachment_bytes=min_attachment_bytes,
            max_attachment_bytes=max_attachment_bytes,
        )
        config.validate()

        saved = await self._repo.create(config, plain_password)

        # Start poller immediately if enabled
        if saved.enabled:
            plain_pw = await self._repo.decrypt_password(tenant_id)
            await self._manager.start_tenant(saved, plain_pw)

        logger.info("email_config_service_created", tenant_id=tenant_id, host=imap_host)
        return _mask(saved)

    # ── Update ────────────────────────────────────────────────────────────────

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
    ) -> dict:
        """Patch the config. Raises NotFoundError if no config exists."""
        try:
            updated = await self._repo.update(
                tenant_id,
                imap_host=imap_host,
                imap_port=imap_port,
                imap_username=imap_username,
                plain_password=plain_password,
                imap_mailbox=imap_mailbox,
                use_ssl=use_ssl,
                poll_interval_sec=poll_interval_sec,
                enabled=enabled,
                allowed_senders=allowed_senders,
                blocked_senders=blocked_senders,
                required_subject_kw=required_subject_kw,
                blocked_subject_kw=blocked_subject_kw,
                min_attachment_bytes=min_attachment_bytes,
                max_attachment_bytes=max_attachment_bytes,
            )
        except KeyError as exc:
            raise NotFoundError(str(exc)) from exc

        # Sync the live poller: restart if enabled, stop if disabled
        if updated.enabled:
            plain_pw = await self._repo.decrypt_password(tenant_id)
            await self._manager.restart_tenant(updated, plain_pw)
        else:
            await self._manager.stop_tenant(tenant_id)

        logger.info("email_config_service_updated", tenant_id=tenant_id)
        return _mask(updated)

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete(self, tenant_id: str) -> None:
        """Remove config and stop the poller. Raises NotFoundError if absent."""
        await self._manager.stop_tenant(tenant_id)
        deleted = await self._repo.delete(tenant_id)
        if not deleted:
            raise NotFoundError(f"No email config for tenant {tenant_id!r}")
        logger.info("email_config_service_deleted", tenant_id=tenant_id)

    # ── Test connection ───────────────────────────────────────────────────────

    async def test_connection(
        self,
        *,
        imap_host: str,
        imap_port: int,
        imap_username: str,
        plain_password: str,
        imap_mailbox: str = "INBOX",
        use_ssl: bool = True,
    ) -> dict[str, str | bool]:
        """Validate IMAP credentials without persisting anything.

        Returns {"success": True, "message": "..."} or
                {"success": False, "message": "<error detail>"}

        The test runs in a thread executor to avoid blocking the event loop
        with synchronous imaplib calls.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            _imap_connect_test,
            imap_host,
            imap_port,
            imap_username,
            plain_password,
            imap_mailbox,
            use_ssl,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask(config: EmailIngestConfig) -> dict:
    """Return a dict representation with the password replaced by a mask."""
    return {
        "id": config.id,
        "tenant_id": config.tenant_id,
        "imap_host": config.imap_host,
        "imap_port": config.imap_port,
        "imap_username": config.imap_username,
        "imap_password": _PASSWORD_MASK,
        "imap_mailbox": config.imap_mailbox,
        "use_ssl": config.use_ssl,
        "poll_interval_sec": config.poll_interval_sec,
        "enabled": config.enabled,
        "status": config.status,
        "status_message": config.status_message,
        "last_polled_at": config.last_polled_at.isoformat() if config.last_polled_at else None,
        "allowed_senders": config.allowed_senders,
        "blocked_senders": config.blocked_senders,
        "required_subject_kw": config.required_subject_kw,
        "blocked_subject_kw": config.blocked_subject_kw,
        "min_attachment_bytes": config.min_attachment_bytes,
        "max_attachment_bytes": config.max_attachment_bytes,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def _imap_connect_test(
    host: str,
    port: int,
    username: str,
    password: str,
    mailbox: str,
    use_ssl: bool,
) -> dict[str, str | bool]:
    """Synchronous IMAP connection test — called in a thread executor."""
    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        else:
            conn = imaplib.IMAP4(host, port)

        conn.login(username, password)
        status, data = conn.select(mailbox, readonly=True)
        conn.logout()

        if status != "OK":
            return {
                "success": False,
                "message": f"Login succeeded but could not SELECT mailbox '{mailbox}': {status}",
            }

        msg_count = int(data[0]) if data and data[0] else 0
        return {
            "success": True,
            "message": (
                f"Connection successful. Mailbox '{mailbox}'"
                f" contains {msg_count} message(s)."
            ),
        }
    except imaplib.IMAP4.error as exc:
        return {"success": False, "message": f"IMAP error: {exc}"}
    except OSError as exc:
        return {"success": False, "message": f"Network error connecting to {host}:{port} — {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "message": f"Unexpected error: {exc}"}
