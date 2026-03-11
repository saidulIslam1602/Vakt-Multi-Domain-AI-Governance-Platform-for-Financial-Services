"""Processing service configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    service_name: str = "processing-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    environment: str = "production"

    # Azure
    azure_blob_account_url: str
    azure_servicebus_namespace_fqdn: str
    azure_search_endpoint: str
    azure_search_index_name: str = "documents"

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_api_key: str = ""  # If set, use API key auth instead of managed identity
    azure_openai_api_version: str = "2024-08-01-preview"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    # PostgreSQL
    database_url: str

    # Service Bus topics
    servicebus_topic_document_events: str = "document-events"
    servicebus_subscription_processing: str = "processing-worker"

    # Processing
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64
    max_extraction_retries: int = 3
    worker_concurrency: int = 4


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
