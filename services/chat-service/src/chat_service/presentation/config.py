"""Pydantic Settings for the chat service.

Kept in a separate module so that dependencies.py can import Settings
without causing a circular import through api.py.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    service_name: str = "chat-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    environment: str = "production"
    database_url: str
    azure_search_endpoint: str
    azure_search_index_name: str = "documents"
    azure_search_key: str = ""  # API key for AI Search (set when authOptions=apiKeyOnly)
    azure_openai_endpoint: str
    azure_openai_api_version: str = "2024-08-01-preview"
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    auth_jwks_uri: str = ""
    auth_audience: str = ""
    auth_issuer: str = ""
    auth_enabled: bool = True
    cors_origins: list[str] = ["*"]
    rag_top_k: int = 6
    # Base URL for document-service calls (posture tools + cross-service audit).
    # In Docker Compose this is http://document-service:8002; locally http://localhost:8002.
    document_service_url: str = "http://localhost:8002"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
