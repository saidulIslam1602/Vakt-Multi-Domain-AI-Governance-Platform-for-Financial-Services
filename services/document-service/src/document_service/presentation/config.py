"""Document service configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    service_name: str = "document-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    environment: str = "production"
    database_url: str
    azure_storage_account_url: str = ""
    auth_jwks_uri: str = ""
    auth_audience: str = ""
    auth_issuer: str = ""
    auth_enabled: bool = True
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
