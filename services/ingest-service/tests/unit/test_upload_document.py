"""Unit tests for UploadDocumentUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from allergo_shared.domain.enums import DocumentStatus
from allergo_shared.domain.exceptions import ValidationError
from ingest_service.application.use_cases.upload_document import UploadDocumentUseCase


@pytest.fixture()
def mock_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.upload.return_value = "tenant-1/some-id/test.pdf"
    return storage


@pytest.fixture()
def mock_queue() -> AsyncMock:
    return AsyncMock()


@pytest.fixture()
def mock_repository() -> AsyncMock:
    repo = AsyncMock()
    repo.save.return_value = None
    return repo


@pytest.fixture()
def use_case(mock_storage, mock_queue, mock_repository) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(
        storage=mock_storage,
        queue=mock_queue,
        repository=mock_repository,
    )


@pytest.mark.asyncio()
async def test_upload_valid_pdf(use_case, mock_storage, mock_queue, mock_repository):
    pdf_bytes = b"%PDF-1.4 fake content"
    document = await use_case.execute(
        filename="contract.pdf",
        data=pdf_bytes,
        content_type="application/pdf",
        tenant_id="tenant-1",
    )

    assert document.status == DocumentStatus.UPLOADED
    assert document.filename == "contract.pdf"
    assert document.size_bytes == len(pdf_bytes)
    mock_storage.upload.assert_awaited_once()
    mock_repository.save.assert_awaited_once()
    mock_queue.publish.assert_awaited_once()


@pytest.mark.asyncio()
async def test_upload_unsupported_type_raises(use_case):
    with pytest.raises(ValidationError, match="Unsupported file type"):
        await use_case.execute(
            filename="script.exe",
            data=b"binary",
            content_type="application/x-msdownload",
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio()
async def test_upload_too_large_raises(use_case):
    oversized = b"x" * (51 * 1024 * 1024)
    with pytest.raises(ValidationError, match="exceeds maximum"):
        await use_case.execute(
            filename="big.pdf",
            data=oversized,
            content_type="application/pdf",
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio()
async def test_upload_publishes_correct_event(use_case, mock_queue):
    await use_case.execute(
        filename="report.pdf",
        data=b"%PDF content",
        content_type="application/pdf",
        tenant_id="tenant-abc",
    )
    call_kwargs = mock_queue.publish.call_args
    message = call_kwargs[0][1]
    assert message["event_type"] == "document.uploaded"
    assert message["tenant_id"] == "tenant-abc"
    assert message["filename"] == "report.pdf"
