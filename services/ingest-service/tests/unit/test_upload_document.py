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


@pytest.mark.asyncio()
async def test_upload_valid_docx(use_case, mock_storage):
    docx_bytes = b"PK\x03\x04" + b"\x00" * 100  # minimal ZIP magic bytes
    document = await use_case.execute(
        filename="report.docx",
        data=docx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        tenant_id="tenant-1",
    )
    assert document.status == DocumentStatus.UPLOADED
    assert document.filename == "report.docx"


@pytest.mark.asyncio()
async def test_upload_valid_xlsx(use_case, mock_storage):
    xlsx_bytes = b"PK\x03\x04" + b"\x00" * 100  # ZIP magic bytes (xlsx is a zip)
    document = await use_case.execute(
        filename="ledger.xlsx",
        data=xlsx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        tenant_id="tenant-1",
    )
    assert document.status == DocumentStatus.UPLOADED
    assert document.filename == "ledger.xlsx"


@pytest.mark.asyncio()
async def test_upload_valid_txt(use_case, mock_storage):
    document = await use_case.execute(
        filename="notes.txt",
        data=b"plain text content",
        content_type="text/plain",
        tenant_id="tenant-1",
    )
    assert document.status == DocumentStatus.UPLOADED


@pytest.mark.asyncio()
async def test_upload_stores_tenant_id_in_document(use_case):
    document = await use_case.execute(
        filename="invoice.pdf",
        data=b"%PDF invoice",
        content_type="application/pdf",
        tenant_id="my-tenant-99",
    )
    assert str(document.tenant_id) == "my-tenant-99"


@pytest.mark.asyncio()
async def test_upload_storage_path_contains_tenant(use_case, mock_storage):
    """Blob path must be scoped to the tenant so documents are isolated."""
    await use_case.execute(
        filename="invoice.pdf",
        data=b"%PDF",
        content_type="application/pdf",
        tenant_id="tenant-xyz",
    )
    call_args = mock_storage.upload.call_args
    # Second positional arg or 'blob_name' kwarg should contain the tenant
    blob_name = call_args[1].get("blob_name") or call_args[0][1]
    assert "tenant-xyz" in blob_name, f"Expected tenant in blob_name, got: {blob_name}"
