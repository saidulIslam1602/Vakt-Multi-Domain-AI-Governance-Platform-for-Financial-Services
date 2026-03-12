"""FastAPI application factory for the chat service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from allergo_shared.infrastructure.rate_limit import RateLimitMiddleware
from openai import AsyncAzureOpenAI

from allergo_shared.infrastructure.health import make_health_router
from allergo_shared.infrastructure.logging import configure_logging
from chat_service.application.rag import RagUseCase
from chat_service.infrastructure.db_reader import FinancialDbReader
from chat_service.presentation.config import Settings  # re-exported for backward compat
from chat_service.presentation.routes.chat import router as chat_router
from chat_service.presentation.routes.saved_queries import router as saved_queries_router

_ELASTICSEARCH_MARKERS = (":9200", "elasticsearch", "localhost:9200", "127.0.0.1:9200")


def _is_elasticsearch(endpoint: str) -> bool:
    lower = endpoint.lower()
    return any(m in lower for m in _ELASTICSEARCH_MARKERS)


def create_app() -> FastAPI:
    cfg = Settings()
    configure_logging(cfg.service_name, cfg.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=8)
        db_reader = FinancialDbReader(pool)
        # Store pool so saved_queries route can access it
        application.state.pool = pool

        # Build OpenAI client — prefer API key (works locally without managed identity)
        if cfg.azure_openai_api_key:
            openai_client = AsyncAzureOpenAI(
                azure_endpoint=cfg.azure_openai_endpoint,
                api_version=cfg.azure_openai_api_version,
                api_key=cfg.azure_openai_api_key,
            )
        else:
            from azure.identity import DefaultAzureCredential as SyncCred
            from azure.identity import get_bearer_token_provider
            token_provider = get_bearer_token_provider(
                SyncCred(), "https://cognitiveservices.azure.com/.default"
            )
            openai_client = AsyncAzureOpenAI(
                azure_endpoint=cfg.azure_openai_endpoint,
                api_version=cfg.azure_openai_api_version,
                azure_ad_token_provider=token_provider,
            )

        if _is_elasticsearch(cfg.azure_search_endpoint):
            from chat_service.application.es_rag import ElasticsearchRagUseCase
            application.state.rag = ElasticsearchRagUseCase(
                es_endpoint=cfg.azure_search_endpoint,
                index_name=cfg.azure_search_index_name,
                openai_client=openai_client,
                db_reader=db_reader,
                embedding_deployment=cfg.azure_openai_embedding_deployment,
                chat_deployment=cfg.azure_openai_chat_deployment,
                top_k=cfg.rag_top_k,
            )
            yield
            await pool.close()
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
    # Chat / RAG is expensive — tighter per-tenant limit (30 rpm, burst to 60)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=30,
        burst_multiplier=2.0,
        enabled=cfg.environment != "local",
    )
    app.include_router(make_health_router(cfg.service_name, cfg.service_version))
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(saved_queries_router, prefix="/api/v1")
    return app


def _get_app() -> FastAPI:
    return create_app()
