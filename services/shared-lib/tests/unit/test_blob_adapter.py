"""Unit tests for AzureBlobStorage — Azurite auto-detection and SAS generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from allergo_shared.infrastructure.azure.blob import (
    _build_azurite_connection_string,
    _is_azurite,
    AzureBlobStorage,
)


# ── _is_azurite ────────────────────────────────────────────────────────────────

class TestIsAzurite:
    def test_localhost_detected(self):
        assert _is_azurite("http://localhost:10000/devstoreaccount1") is True

    def test_127_detected(self):
        assert _is_azurite("http://127.0.0.1:10000/devstoreaccount1") is True

    def test_azurite_hostname_detected(self):
        assert _is_azurite("http://azurite:10000/devstoreaccount1") is True

    def test_devstoreaccount1_detected(self):
        assert _is_azurite("https://devstoreaccount1.blob.core.windows.net") is True

    def test_real_azure_not_detected(self):
        assert _is_azurite("https://mystorage.blob.core.windows.net") is False

    def test_case_insensitive(self):
        assert _is_azurite("http://LOCALHOST:10000/devstoreaccount1") is True


# ── _build_azurite_connection_string ──────────────────────────────────────────

class TestBuildAzuriteConnectionString:
    def test_contains_host_from_url(self):
        conn = _build_azurite_connection_string("http://azurite:10000/devstoreaccount1")
        assert "azurite" in conn
        assert "BlobEndpoint=http://azurite:10000/devstoreaccount1" in conn

    def test_localhost_url(self):
        conn = _build_azurite_connection_string("http://localhost:10000/devstoreaccount1")
        assert "localhost" in conn

    def test_contains_account_name(self):
        conn = _build_azurite_connection_string("http://azurite:10000/devstoreaccount1")
        assert "AccountName=devstoreaccount1" in conn

    def test_contains_account_key(self):
        conn = _build_azurite_connection_string("http://azurite:10000/devstoreaccount1")
        assert "AccountKey=" in conn


# ── AzureBlobStorage constructor ──────────────────────────────────────────────

class TestAzureBlobStorageConstructor:
    @patch("allergo_shared.infrastructure.azure.blob.BlobServiceClient")
    def test_azurite_uses_connection_string(self, mock_bsc):
        mock_bsc.from_connection_string.return_value = MagicMock()
        storage = AzureBlobStorage("http://azurite:10000/devstoreaccount1")
        assert storage._is_local is True
        assert storage._credential is None
        mock_bsc.from_connection_string.assert_called_once()

    @patch("allergo_shared.infrastructure.azure.blob.DefaultAzureCredential")
    @patch("allergo_shared.infrastructure.azure.blob.BlobServiceClient")
    def test_production_uses_managed_identity(self, mock_bsc, mock_cred):
        mock_bsc.return_value = MagicMock()
        mock_cred.return_value = MagicMock()
        storage = AzureBlobStorage("https://mystorage.blob.core.windows.net")
        assert storage._is_local is False
        assert storage._credential is not None
        mock_bsc.assert_called_once()


# ── upload auto-creates container ─────────────────────────────────────────────

class TestAzureBlobStorageUpload:
    @pytest.mark.asyncio
    @patch("allergo_shared.infrastructure.azure.blob.BlobServiceClient")
    async def test_upload_creates_container_and_uploads(self, mock_bsc_cls):
        """upload() should call create_container() then upload_blob()."""
        mock_blob_client = AsyncMock()
        mock_blob_client.upload_blob = AsyncMock(return_value=None)

        mock_container_client = AsyncMock()
        mock_container_client.create_container = AsyncMock(return_value=None)
        # get_blob_client is a sync method — must return the mock directly (not a coroutine)
        mock_container_client.get_blob_client = MagicMock(return_value=mock_blob_client)

        mock_service = MagicMock()
        mock_service.get_container_client = MagicMock(return_value=mock_container_client)
        mock_bsc_cls.from_connection_string.return_value = mock_service

        storage = AzureBlobStorage("http://azurite:10000/devstoreaccount1")
        result = await storage.upload(
            container="raw-documents",
            blob_name="tenant-1/doc-id/test.pdf",
            data=b"%PDF",
            content_type="application/pdf",
        )

        assert result == "tenant-1/doc-id/test.pdf"
        mock_container_client.create_container.assert_awaited_once()
        mock_blob_client.upload_blob.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("allergo_shared.infrastructure.azure.blob.BlobServiceClient")
    async def test_upload_ignores_container_already_exists(self, mock_bsc_cls):
        """create_container() raising should NOT prevent the upload from completing."""
        mock_blob_client = AsyncMock()
        mock_blob_client.upload_blob = AsyncMock(return_value=None)

        mock_container_client = AsyncMock()
        mock_container_client.create_container = AsyncMock(
            side_effect=Exception("ContainerAlreadyExists")
        )
        mock_container_client.get_blob_client = MagicMock(return_value=mock_blob_client)

        mock_service = MagicMock()
        mock_service.get_container_client = MagicMock(return_value=mock_container_client)
        mock_bsc_cls.from_connection_string.return_value = mock_service

        storage = AzureBlobStorage("http://azurite:10000/devstoreaccount1")
        result = await storage.upload(
            container="raw-documents",
            blob_name="tenant-1/doc-id/file.pdf",
            data=b"data",
        )
        assert result == "tenant-1/doc-id/file.pdf"
        mock_blob_client.upload_blob.assert_awaited_once()


# ── generate_sas_url ──────────────────────────────────────────────────────────

class TestGenerateSasUrl:
    @pytest.mark.asyncio
    @patch("allergo_shared.infrastructure.azure.blob.BlobServiceClient")
    async def test_azurite_sas_uses_account_key(self, mock_bsc_cls):
        mock_service = MagicMock()
        mock_bsc_cls.from_connection_string.return_value = mock_service

        storage = AzureBlobStorage("http://azurite:10000/devstoreaccount1")

        # The Azurite branch does `from azure.storage.blob import generate_blob_sas`
        # *inside* the method body, so we must patch it at the source package level.
        # We also patch the module-level binding for belt-and-suspenders.
        with patch("azure.storage.blob.generate_blob_sas", return_value="sig=abc123") as mock_gen, \
             patch("allergo_shared.infrastructure.azure.blob.generate_blob_sas", return_value="sig=abc123"):
            url = await storage.generate_sas_url("raw-documents", "tenant/doc/file.pdf", expiry_hours=2)

        mock_gen.assert_called_once()
        # account_key must be present (Azurite path, not user_delegation_key)
        call_kwargs = mock_gen.call_args.kwargs
        assert "account_key" in call_kwargs, (
            f"Expected account_key in SAS call kwargs, got: {call_kwargs}"
        )
        assert "sig=abc123" in url


# ── close() ───────────────────────────────────────────────────────────────────

class TestClose:
    @pytest.mark.asyncio
    @patch("allergo_shared.infrastructure.azure.blob.BlobServiceClient")
    async def test_close_azurite_does_not_close_none_credential(self, mock_bsc_cls):
        """close() must NOT call close() on a None credential (would AttributeError)."""
        mock_service = AsyncMock()
        mock_bsc_cls.from_connection_string.return_value = mock_service

        storage = AzureBlobStorage("http://azurite:10000/devstoreaccount1")
        # Should not raise
        await storage.close()
        mock_service.close.assert_awaited_once()
