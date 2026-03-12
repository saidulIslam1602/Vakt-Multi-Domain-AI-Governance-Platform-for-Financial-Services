"""FastAPI application factory for the search service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allergo_shared.infrastructure.rate_limit import RateLimitMiddleware
from openai import AsyncAzureOpenAI

from allergo_shared.infrastructure.health import make_health_router
from allergo_shared.infrastructure.logging import configure_logging
from search_service.application.search import SearchUseCase
from search_service.infrastructure.config import get_settings
from search_service.presentation.routes.search import router as search_router

_ELASTICSEARCH_MARKERS = (":9200", "elasticsearch", "localhost:9200", "127.0.0.1:9200")


def _is_elasticsearch(endpoint: str) -> bool:
    lower = endpoint.lower()
    return any(m in lower for m in _ELASTICSEARCH_MARKERS)


def create_app() -> FastAPI:
    cfg = get_settings()
    configure_logging(cfg.service_name, cfg.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        # Build OpenAI client (API key or managed identity)
        if cfg.azure_openai_api_key:
            openai_client = AsyncAzureOpenAI(
                azure_endpoint=cfg.azure_openai_endpoint,
                api_version=cfg.azure_openai_api_version,
                api_key=cfg.azure_openai_api_key,
            )
        else:
            from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential
            from azure.identity import get_bearer_token_provider
            token_provider = get_bearer_token_provider(
                SyncDefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            )
            openai_client = AsyncAzureOpenAI(
                azure_endpoint=cfg.azure_openai_endpoint,
                api_version=cfg.azure_openai_api_version,
                azure_ad_token_provider=token_provider,
            )

        if _is_elasticsearch(cfg.azure_search_endpoint):
            from search_service.application.es_search import ElasticsearchSearchUseCase
            application.state.search_use_case = ElasticsearchSearchUseCase(
                endpoint=cfg.azure_search_endpoint,
                index_name=cfg.azure_search_index_name,
                openai_client=openai_client,
                embedding_deployment=cfg.azure_openai_embedding_deployment,
            )
            yield
            await openai_client.close()
        else:
            from azure.identity.aio import DefaultAzureCredential
            from azure.search.documents.aio import SearchClient

            credential = DefaultAzureCredential()
            search_client = SearchClient(
                endpoint=cfg.azure_search_endpoint,
                index_name=cfg.azure_search_index_name,
                credential=credential,
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
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=60,
        burst_multiplier=2.0,
        enabled=cfg.environment != "local",
    )
    app.include_router(make_health_router(cfg.service_name, cfg.service_version))
    app.include_router(search_router, prefix="/api/v1")
    return app


def _get_app() -> FastAPI:
    return create_app()
