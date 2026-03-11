"""Entry point for the processing worker."""

from __future__ import annotations

import asyncio

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import]
from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential
from azure.identity import get_bearer_token_provider
from azure.identity.aio import DefaultAzureCredential

from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
from allergo_shared.infrastructure.azure.service_bus import AzureServiceBus
from allergo_shared.infrastructure.logging import configure_logging, get_logger
from processing_service.application.contract_renewal_scanner import ContractRenewalScanner
from processing_service.application.worker import ProcessingWorker
from processing_service.infrastructure.config import get_settings
from processing_service.infrastructure.db_updater import DocumentStatusUpdater
from processing_service.infrastructure.es_indexer import (
    _is_elasticsearch,
    ensure_es_index,
    index_chunks_es,
)
from processing_service.infrastructure.llm_extractor import LLMExtractor
from processing_service.infrastructure.search_indexer import ensure_index, index_chunks

logger = get_logger(__name__)


async def main() -> None:
    cfg = get_settings()
    configure_logging(cfg.service_name, cfg.log_level)
    logger.info("processing_worker_initializing", version=cfg.service_version)

    # Use API key auth if configured (avoids managed-identity RBAC on regional endpoints),
    # otherwise fall back to AAD token provider.
    from openai import AsyncAzureOpenAI

    if cfg.azure_openai_api_key:
        openai_client = AsyncAzureOpenAI(
            azure_endpoint=cfg.azure_openai_endpoint,
            api_version=cfg.azure_openai_api_version,
            api_key=cfg.azure_openai_api_key,
        )
    else:
        token_provider = get_bearer_token_provider(
            SyncDefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        openai_client = AsyncAzureOpenAI(
            azure_endpoint=cfg.azure_openai_endpoint,
            api_version=cfg.azure_openai_api_version,
            azure_ad_token_provider=token_provider,
        )

    pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=10)
    blob = AzureBlobStorage(cfg.azure_blob_account_url)
    queue = AzureServiceBus(cfg.azure_servicebus_namespace_fqdn)

    # Choose indexer backend: Elasticsearch (local dev) or Azure AI Search (prod)
    use_elasticsearch = _is_elasticsearch(cfg.azure_search_endpoint)

    if use_elasticsearch:
        logger.info("indexer_backend", backend="elasticsearch", endpoint=cfg.azure_search_endpoint)
        await ensure_es_index(cfg.azure_search_endpoint, cfg.azure_search_index_name)

        async def _index_fn(chunks):  # type: ignore[no-untyped-def]
            await index_chunks_es(
                cfg.azure_search_endpoint,
                cfg.azure_search_index_name,
                openai_client,
                cfg.azure_openai_embedding_deployment,
                chunks,
            )

        cleanup_search = None
    else:
        logger.info("indexer_backend", backend="azure_search", endpoint=cfg.azure_search_endpoint)
        credential = DefaultAzureCredential()
        from azure.search.documents.aio import SearchClient
        from azure.search.documents.indexes.aio import SearchIndexClient

        search_client = SearchClient(
            endpoint=cfg.azure_search_endpoint,
            index_name=cfg.azure_search_index_name,
            credential=credential,
        )
        index_client = SearchIndexClient(
            endpoint=cfg.azure_search_endpoint,
            credential=credential,
        )
        await ensure_index(index_client, cfg.azure_search_index_name)

        async def _index_fn(chunks):  # type: ignore[no-untyped-def]
            await index_chunks(
                search_client, openai_client, cfg.azure_openai_embedding_deployment, chunks
            )

        async def cleanup_search() -> None:
            await search_client.close()
            await index_client.close()
            await credential.close()

    extractor = LLMExtractor(openai_client, cfg.azure_openai_chat_deployment)
    db_updater = DocumentStatusUpdater(pool)

    worker = ProcessingWorker(
        queue=queue,
        storage=blob,
        extractor=extractor,
        indexer_fn=_index_fn,
        db_updater=db_updater,
        settings=cfg,
    )

    # ── Contract renewal scanner (APScheduler) ────────────────────────────────
    scheduler: AsyncIOScheduler | None = None
    if cfg.scheduler_enabled:
        scanner = ContractRenewalScanner(pool=pool, settings=cfg)
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            scanner.run_scan,
            trigger="cron",
            hour=cfg.scheduler_hour_utc,
            minute=0,
            id="contract_renewal_scan",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(
            "contract_renewal_scheduler_started",
            schedule=f"daily at {cfg.scheduler_hour_utc:02d}:00 UTC",
        )

    try:
        await worker.run()
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await pool.close()
        await blob.close()
        await queue.close()
        await openai_client.close()
        if cleanup_search is not None:
            await cleanup_search()


if __name__ == "__main__":
    asyncio.run(main())
