"""Search service configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    service_name: str = "search-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    environment: str = "production"

    azure_search_endpoint: str
    azure_search_index_name: str = "documents"
    azure_openai_endpoint: str
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    auth_jwks_uri: str
    auth_audience: str
    auth_issuer: str
    auth_enabled: bool = True
    cors_origins: list[str] = ["*"]


from functools import lru_cache


@lru_cache
def get_settings() -> Settings:
    return Settings()
