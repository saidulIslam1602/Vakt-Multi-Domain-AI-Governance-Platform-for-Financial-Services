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

    # ── Email ingestion filters ────────────────────────────────────────────────
    # IMAP_ALLOWED_SENDERS — comma-separated list of trusted sender addresses or
    #   domains.  If non-empty, emails from any other sender are silently skipped.
    #   Examples:
    #     "vendor@acme.com"                         → exact address match
    #     "@acme.com"                               → entire domain
    #     "vendor@acme.com,@partner.no"             → mix of both
    #   Leave empty ("") to accept mail from any sender.
    imap_allowed_senders: str = ""

    # IMAP_REQUIRED_SUBJECT_KEYWORDS — comma-separated words / phrases.
    #   ALL listed keywords must appear in the subject (case-insensitive).
    #   Leave empty to skip subject filtering.
    #   Example: "invoice,2026"  → subject must contain both "invoice" AND "2026"
    imap_required_subject_keywords: str = ""

    # IMAP_BLOCKED_SUBJECT_KEYWORDS — comma-separated words / phrases.
    #   If ANY of these appear in the subject the whole email is skipped.
    #   Example: "newsletter,unsubscribe,auto-reply"
    imap_blocked_subject_keywords: str = ""

    # IMAP_BLOCKED_SENDERS — comma-separated addresses / domains to always skip,
    #   evaluated after the allowlist (acts as a deny-override).
    #   Example: "noreply@salesforce.com,@marketing.acme.com"
    imap_blocked_senders: str = ""

    # Per-attachment size limits (bytes).  Defaults: 1 KB min, 50 MB max.
    imap_min_attachment_bytes: int = 1_024            # 1 KB
    imap_max_attachment_bytes: int = 50 * 1_024 * 1_024  # 50 MB

    # ── Database-level encryption (pgcrypto AES) ──────────────────────────────
    # Used to encrypt / decrypt IMAP passwords stored in email_ingest_configs.
    # MUST be set in production.  Generate with:
    #   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    db_encryption_key: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
