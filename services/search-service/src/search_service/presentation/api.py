"""FastAPI application factory for the search service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from azure.identity import get_bearer_token_provider
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncAzureOpenAI

from allergo_shared.infrastructure.health import make_health_router
from allergo_shared.infrastructure.logging import configure_logging
from search_service.application.search import SearchUseCase
from search_service.infrastructure.config import get_settings
from search_service.presentation.routes.search import router as search_router


def create_app() -> FastAPI:
    cfg = get_settings()
    configure_logging(cfg.service_name, cfg.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
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
        application.state.search_use_case = SearchUseCase(
            search_client=search_client,
            openai_client=openai_client,
            embedding_deployment=cfg.azure_openai_embedding_deployment,
        )
        yield
        await search_client.close()
        await openai_client.close()
        await credential.close()

    app = FastAPI(
        title="Allergo Nordic — Search Service",
        description="Hybrid full-text + semantic search over processed documents.",
        version=cfg.service_version,
        lifespan=lifespan,
        docs_url="/docs" if cfg.environment != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(make_health_router(cfg.service_name, cfg.service_version))
    app.include_router(search_router, prefix="/api/v1")
    return app


def _get_app() -> FastAPI:
    return create_app()
