"""FastAPI application factory for the chat service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import asyncpg
from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential
from azure.identity import get_bearer_token_provider
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncAzureOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from allergo_shared.infrastructure.health import make_health_router
from allergo_shared.infrastructure.logging import configure_logging
from chat_service.application.rag import RagUseCase
from chat_service.infrastructure.db_reader import FinancialDbReader
from chat_service.presentation.routes.chat import router as chat_router


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    service_name: str = "chat-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    environment: str = "production"
    database_url: str
    azure_search_endpoint: str
    azure_search_index_name: str = "documents"
    azure_openai_endpoint: str
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    auth_jwks_uri: str = ""
    auth_audience: str = ""
    auth_issuer: str = ""
    auth_enabled: bool = True
    cors_origins: list[str] = ["*"]
    rag_top_k: int = 6


def create_app() -> FastAPI:
    cfg = Settings()
    configure_logging(cfg.service_name, cfg.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=8)
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            SyncDefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        search_client = SearchClient(
            endpoint=cfg.azure_search_endpoint,
            index_name=cfg.azure_search_index_name,
            credential=credential,
        )
        openai_client = AsyncAzureOpenAI(
            azure_endpoint=cfg.azure_openai_endpoint,
            api_version=cfg.azure_openai_api_version,
            azure_ad_token_provider=token_provider,
        )
        db_reader = FinancialDbReader(pool)
        application.state.rag = RagUseCase(
            search_client=search_client,
            openai_client=openai_client,
            db_reader=db_reader,
            embedding_deployment=cfg.azure_openai_embedding_deployment,
            chat_deployment=cfg.azure_openai_chat_deployment,
            top_k=cfg.rag_top_k,
        )
        yield
        await pool.close()
        await search_client.close()
        await openai_client.close()
        await credential.close()

    app = FastAPI(
        title="Allergo Nordic — CFO Chat Service",
        description=(
            "Agentic RAG: tool-calling over vector search + structured financial DB. "
            "Returns grounded answers, citations, follow-up suggestions, and tools used."
        ),
        version=cfg.service_version,
        lifespan=lifespan,
        docs_url="/docs" if cfg.environment != "production" else None,
    )
    app.add_middleware(  # type: ignore[call-arg]
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(make_health_router(cfg.service_name, cfg.service_version))
    app.include_router(chat_router, prefix="/api/v1")
    return app


def _get_app() -> FastAPI:
    return create_app()
