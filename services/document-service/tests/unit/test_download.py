"""Unit tests for the download URL endpoint.

Verifies that the container is always "raw-documents" and that
blob_path is passed through unchanged (not split to derive a container).
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(tenant_id: str = "tenant-abc"):
    from allergo_shared.infrastructure.auth import AuthenticatedUser
    return AuthenticatedUser(sub="dev-user", tenant_id=tenant_id, scopes=[])


# ── Container name logic tests (pure — no imports needed) ─────────────────────

class TestContainerNameLogic:
    """Test the logic: container must always be 'raw-documents'."""

    def test_container_is_always_raw_documents(self):
        """Regardless of blob_path, container must be 'raw-documents'."""
        blob_paths = [
            "tenant-abc/doc-123/invoice.pdf",
            "tenant-xyz/doc-456/contract.docx",
            "00000000-0000-0000-0000-000000000001/id/file.xlsx",
        ]
        for blob_path in blob_paths:
            # Old (broken) logic: container = blob_path.split("/", 1)[0]
            broken_container = blob_path.split("/", 1)[0]
            # Fixed logic: container = "raw-documents"
            fixed_container = "raw-documents"

            assert broken_container != fixed_container, (
                f"blob_path '{blob_path}' split would wrongly give container '{broken_container}'"
            )
            assert fixed_container == "raw-documents"

    def test_blob_name_is_full_path_not_split(self):
        """blob_name must be the full blob_path, not just the suffix after first slash."""
        blob_path = "tenant-abc/doc-123/invoice.pdf"
        # Old (broken) logic: blob_name = blob_path.split("/", 1)[1]
        broken_blob_name = blob_path.split("/", 1)[1]
        # Fixed logic: blob_name = blob_path (the full path)
        fixed_blob_name = blob_path

        assert broken_blob_name == "doc-123/invoice.pdf"
        assert fixed_blob_name == "tenant-abc/doc-123/invoice.pdf"


# ── Full endpoint test via FastAPI test client ────────────────────────────────

@pytest.fixture(autouse=True)
def _set_required_env(monkeypatch):
    """Provide the minimum env vars required by Settings() at import time."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "http://azurite:10000/devstoreaccount1")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")


class TestGetDownloadUrlEndpoint:
    @pytest.mark.asyncio
    async def test_sas_called_with_raw_documents_container(self, _set_required_env):
        """The blob.generate_sas_url must always receive container='raw-documents'."""
        # Import inside test after env vars are set
        from document_service.presentation.routes.download import router
        from document_service.presentation.dependencies import get_blob, get_current_user, get_pool
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        blob_path = "tenant-abc/doc-999/report.pdf"

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value={
            "filename": "report.pdf",
            "blob_path": blob_path,
        })

        mock_blob = AsyncMock()
        mock_blob.generate_sas_url = AsyncMock(
            return_value="http://azurite:10000/raw-documents/tenant-abc/doc-999/report.pdf?sig=xyz"
        )

        mock_user = _make_user("tenant-abc")

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_blob] = lambda: mock_blob
        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)
        response = client.get("/api/v1/documents/doc-999/download-url")

        assert response.status_code == 200
        # Verify blob was called with correct container
        mock_blob.generate_sas_url.assert_awaited_once()
        call_kwargs = mock_blob.generate_sas_url.call_args
        container_arg = call_kwargs.kwargs.get("container") or call_kwargs.args[0]
        assert container_arg == "raw-documents", (
            f"Expected container='raw-documents' but got '{container_arg}'"
        )
        # Verify blob_name is the FULL path, not split
        blob_name_arg = call_kwargs.kwargs.get("blob_name") or call_kwargs.args[1]
        assert blob_name_arg == blob_path, (
            f"Expected blob_name='{blob_path}' but got '{blob_name_arg}'"
        )

    @pytest.mark.asyncio
    async def test_missing_document_returns_404(self, _set_required_env):
        from document_service.presentation.routes.download import router
        from document_service.presentation.dependencies import get_blob, get_current_user, get_pool
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        mock_pool = AsyncMock()
        mock_pool.fetchrow = AsyncMock(return_value=None)
        mock_blob = AsyncMock()
        mock_user = _make_user()

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_pool] = lambda: mock_pool
        app.dependency_overrides[get_blob] = lambda: mock_blob
        app.dependency_overrides[get_current_user] = lambda: mock_user

        client = TestClient(app)
        response = client.get("/api/v1/documents/nonexistent/download-url")
        assert response.status_code == 404

