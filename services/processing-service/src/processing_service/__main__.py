"""Entry point for the processing worker."""

from __future__ import annotations

import asyncio

import asyncpg
from azure.identity import get_bearer_token_provider
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from openai import AsyncAzureOpenAI

from allergo_shared.infrastructure.azure.blob import AzureBlobStorage
from allergo_shared.infrastructure.azure.service_bus import AzureServiceBus
from allergo_shared.infrastructure.logging import configure_logging, get_logger
from processing_service.application.worker import ProcessingWorker
from processing_service.infrastructure.config import get_settings
from processing_service.infrastructure.db_updater import DocumentStatusUpdater
from processing_service.infrastructure.llm_extractor import LLMExtractor
from processing_service.infrastructure.search_indexer import ensure_index, index_chunks

logger = get_logger(__name__)


async def main() -> None:
    cfg = get_settings()
    configure_logging(cfg.service_name, cfg.log_level)
    logger.info("processing_worker_initializing", version=cfg.service_version)

    credential = DefaultAzureCredential()
    # get_bearer_token_provider returns a Callable[[], str] as required by AsyncAzureOpenAI.
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )

    pool = await asyncpg.create_pool(cfg.database_url, min_size=2, max_size=10)
    blob = AzureBlobStorage(cfg.azure_blob_account_url)
    queue = AzureServiceBus(cfg.azure_servicebus_namespace_fqdn)
    openai_client = AsyncAzureOpenAI(
        azure_endpoint=cfg.azure_openai_endpoint,
        api_version=cfg.azure_openai_api_version,
        azure_ad_token_provider=token_provider,
    )
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

    extractor = LLMExtractor(openai_client, cfg.azure_openai_chat_deployment)
    db_updater = DocumentStatusUpdater(pool)

    async def _index_fn(chunks):  # type: ignore[no-untyped-def]
        await index_chunks(
            search_client, openai_client, cfg.azure_openai_embedding_deployment, chunks
        )

    worker = ProcessingWorker(
        queue=queue,
        storage=blob,
        extractor=extractor,
        indexer_fn=_index_fn,
        db_updater=db_updater,
        settings=cfg,
    )

    try:
        await worker.run()
    finally:
        await pool.close()
        await blob.close()
        await queue.close()
        await openai_client.close()
        await search_client.close()
        await index_client.close()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
