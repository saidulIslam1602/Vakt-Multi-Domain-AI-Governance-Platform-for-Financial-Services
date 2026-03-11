"""Ingest service configuration — loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Service
    service_name: str = "ingest-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    environment: str = "production"

    # Azure Blob
    azure_blob_account_url: str

    # Azure Service Bus
    azure_servicebus_namespace_fqdn: str

    # PostgreSQL
    database_url: str  # asyncpg DSN: postgresql+asyncpg://user:pass@host:5432/db

    # Auth (Azure AD / OIDC)
    auth_jwks_uri: str = ""
    auth_audience: str = ""
    auth_issuer: str = ""
    auth_enabled: bool = True

    # Limits
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB

    # CORS
    cors_origins: list[str] = ["*"]

    # ── Email ingestion (IMAP poller) ─────────────────────────────────────────
    email_ingest_enabled: bool = False
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_poll_interval_sec: int = 300    # poll every 5 minutes
    imap_use_ssl: bool = True
    imap_tenant_id: str = "default"     # Allergo tenant that owns ingested docs


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
