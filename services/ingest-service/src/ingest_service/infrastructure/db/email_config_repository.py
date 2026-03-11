"""PostgreSQL implementation of IEmailConfigRepository.

Password encryption
───────────────────
IMAP passwords are encrypted using pgcrypto's pgp_sym_encrypt / pgp_sym_decrypt
(AES-256) with a key supplied at runtime via ALLERGO_DB_ENCRYPTION_KEY.
The key is read once at construction and never logged or returned via any API.

The raw decrypted password is returned ONLY by decrypt_password(), called
exclusively by the EmailPollerManager — never through any HTTP endpoint.
"""

from __future__ import annotations

import os
from typing import Literal

import asyncpg
from allergo_shared.domain.email_config import EmailIngestConfig
from allergo_shared.domain.interfaces.email_config_repository import IEmailConfigRepository
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)

_ENV_KEY = "ALLERGO_DB_ENCRYPTION_KEY"


def _require_enc_key() -> str:
    key = os.environ.get(_ENV_KEY, "").strip()
    if not key:
        raise RuntimeError(
            f"{_ENV_KEY} is required for email config password encryption but is not set. "
            'Generate a key: python3 -c "import secrets; print(secrets.token_hex(32))"'
        )
    return key


class PostgresEmailConfigRepository(IEmailConfigRepository):
    """asyncpg-backed repository for email_ingest_configs."""

    _SELECT_COLS = (
        "id, tenant_id, imap_host, imap_port, imap_username, "
        "imap_password_enc, imap_mailbox, use_ssl, poll_interval_sec, "
        "enabled, status, status_message, last_polled_at, "
        "allowed_senders, blocked_senders, required_subject_kw, blocked_subject_kw, "
        "min_attachment_bytes, max_attachment_bytes, created_at, updated_at"
    )

    def __init__(self, pool: asyncpg.Pool, enc_key: str | None = None) -> None:
        self._pool = pool
        self._enc_key = enc_key or _require_enc_key()

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get(self, tenant_id: str) -> EmailIngestConfig | None:
        row = await self._pool.fetchrow(
            f"SELECT {self._SELECT_COLS} FROM email_ingest_configs WHERE tenant_id = $1",
            tenant_id,
        )
        return self._to_entity(row) if row else None

    async def get_all_enabled(self) -> list[EmailIngestConfig]:
        rows = await self._pool.fetch(
            f"SELECT {self._SELECT_COLS} FROM email_ingest_configs WHERE enabled = TRUE",
        )
        return [self._to_entity(r) for r in rows]

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create(
        self,
        config: EmailIngestConfig,
        plain_password: str,
    ) -> EmailIngestConfig:
        row = await self._pool.fetchrow(
            f"""INSERT INTO email_ingest_configs (
                    tenant_id, imap_host, imap_port, imap_username,
                    imap_password_enc,
                    imap_mailbox, use_ssl, poll_interval_sec,
                    enabled, status,
                    allowed_senders, blocked_senders,
                    required_subject_kw, blocked_subject_kw,
                    min_attachment_bytes, max_attachment_bytes
                ) VALUES (
                    $1, $2, $3, $4,
                    pgp_sym_encrypt($5, $17),
                    $6, $7, $8,
                    $9, $10,
                    $11, $12, $13, $14, $15, $16
                )
                RETURNING {self._SELECT_COLS}""",
            config.tenant_id,            # $1
            config.imap_host,            # $2
            config.imap_port,            # $3
            config.imap_username,        # $4
            plain_password,              # $5
            config.imap_mailbox,         # $6
            config.use_ssl,              # $7
            config.poll_interval_sec,    # $8
            config.enabled,              # $9
            config.status,               # $10
            config.allowed_senders,      # $11
            config.blocked_senders,      # $12
            config.required_subject_kw,  # $13
            config.blocked_subject_kw,   # $14
            config.min_attachment_bytes, # $15
            config.max_attachment_bytes, # $16
            self._enc_key,               # $17
        )
        logger.info("email_config_created", tenant_id=config.tenant_id, host=config.imap_host)
        return self._to_entity(row)  # type: ignore[arg-type]

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
        set_clauses: list[str] = []
        params: list = [tenant_id]  # $1 for WHERE

        def _add(col: str, val: object) -> None:
            params.append(val)
            set_clauses.append(f"{col} = ${len(params)}")

        if imap_host is not None:
            _add("imap_host", imap_host)
        if imap_port is not None:
            _add("imap_port", imap_port)
        if imap_username is not None:
            _add("imap_username", imap_username)
        if plain_password is not None:
            params.append(plain_password)
            p_idx = len(params)
            params.append(self._enc_key)
            k_idx = len(params)
            set_clauses.append(f"imap_password_enc = pgp_sym_encrypt(${p_idx}, ${k_idx})")
        if imap_mailbox is not None:
            _add("imap_mailbox", imap_mailbox)
        if use_ssl is not None:
            _add("use_ssl", use_ssl)
        if poll_interval_sec is not None:
            _add("poll_interval_sec", poll_interval_sec)
        if enabled is not None:
            _add("enabled", enabled)
        if allowed_senders is not None:
            _add("allowed_senders", allowed_senders)
        if blocked_senders is not None:
            _add("blocked_senders", blocked_senders)
        if required_subject_kw is not None:
            _add("required_subject_kw", required_subject_kw)
        if blocked_subject_kw is not None:
            _add("blocked_subject_kw", blocked_subject_kw)
        if min_attachment_bytes is not None:
            _add("min_attachment_bytes", min_attachment_bytes)
        if max_attachment_bytes is not None:
            _add("max_attachment_bytes", max_attachment_bytes)

        if not set_clauses:
            existing = await self.get(tenant_id)
            if existing is None:
                raise KeyError(f"No email config for tenant {tenant_id!r}")
            return existing

        sql = (
            f"UPDATE email_ingest_configs SET {', '.join(set_clauses)} "
            f"WHERE tenant_id = $1 RETURNING {self._SELECT_COLS}"
        )
        row = await self._pool.fetchrow(sql, *params)
        if row is None:
            raise KeyError(f"No email config for tenant {tenant_id!r}")
        logger.info("email_config_updated", tenant_id=tenant_id)
        return self._to_entity(row)

    async def update_status(
        self,
        tenant_id: str,
        status: Literal["idle", "running", "error", "disabled"],
        status_message: str | None = None,
    ) -> None:
        await self._pool.execute(
            "UPDATE email_ingest_configs SET status=$2, status_message=$3 WHERE tenant_id=$1",
            tenant_id, status, status_message,
        )

    async def mark_polled(self, tenant_id: str) -> None:
        await self._pool.execute(
            "UPDATE email_ingest_configs "
            "SET last_polled_at=NOW(), status='idle', status_message=NULL "
            "WHERE tenant_id=$1",
            tenant_id,
        )

    async def delete(self, tenant_id: str) -> bool:
        result = await self._pool.execute(
            "DELETE FROM email_ingest_configs WHERE tenant_id=$1", tenant_id,
        )
        deleted = result != "DELETE 0"
        if deleted:
            logger.info("email_config_deleted", tenant_id=tenant_id)
        return deleted

    async def decrypt_password(self, tenant_id: str) -> str:
        row = await self._pool.fetchrow(
            "SELECT pgp_sym_decrypt(imap_password_enc, $2)::TEXT AS pw "
            "FROM email_ingest_configs WHERE tenant_id=$1",
            tenant_id, self._enc_key,
        )
        if row is None:
            raise KeyError(f"No email config for tenant {tenant_id!r}")
        return str(row["pw"])

    # ── Mapper ────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(row: asyncpg.Record) -> EmailIngestConfig:
        return EmailIngestConfig(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            imap_host=row["imap_host"],
            imap_port=row["imap_port"],
            imap_username=row["imap_username"],
            imap_password_enc=bytes(row["imap_password_enc"]) if row["imap_password_enc"] else None,
            imap_mailbox=row["imap_mailbox"],
            use_ssl=row["use_ssl"],
            poll_interval_sec=row["poll_interval_sec"],
            enabled=row["enabled"],
            status=row["status"],
            status_message=row.get("status_message"),
            last_polled_at=row["last_polled_at"],
            allowed_senders=row["allowed_senders"] or "",
            blocked_senders=row["blocked_senders"] or "",
            required_subject_kw=row["required_subject_kw"] or "",
            blocked_subject_kw=row["blocked_subject_kw"] or "",
            min_attachment_bytes=row["min_attachment_bytes"],
            max_attachment_bytes=row["max_attachment_bytes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
