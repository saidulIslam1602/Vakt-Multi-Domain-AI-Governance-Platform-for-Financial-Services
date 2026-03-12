"""Azure Blob Storage adapter — implements BlobStoragePort."""

from __future__ import annotations

import datetime

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import (
    ContentSettings,
    UserDelegationKey,
)
from azure.storage.blob.aio import BlobServiceClient

from allergo_shared.domain.exceptions import StorageError
from allergo_shared.domain.interfaces.storage import BlobStoragePort

# Azurite (local emulator) well-known connection string
_AZURITE_ACCOUNT_NAME = "devstoreaccount1"
# This is the public, well-known Azurite development key — NOT a real secret.
_AZURITE_ACCOUNT_KEY = (
    "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tfd8"
    "e9jmJAbWE56NfzFiZy7YlQ=="
)
_AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;"
    f"AccountName={_AZURITE_ACCOUNT_NAME};"
    f"AccountKey={_AZURITE_ACCOUNT_KEY};"
    "BlobEndpoint=http://{{host}}:10000/devstoreaccount1;"
)


def _is_azurite(account_url: str) -> bool:
    """Return True when the URL points to a local Azurite emulator."""
    lower = account_url.lower()
    return (
        "127.0.0.1" in lower
        or "localhost" in lower
        or "azurite" in lower
        or "devstoreaccount1" in lower
    )


def _build_azurite_connection_string(account_url: str) -> str:
    """Build a connection string from an Azurite endpoint URL."""
    # Extract host (e.g. "azurite", "localhost", "127.0.0.1") from URL like
    # http://azurite:10000/devstoreaccount1
    import re
    m = re.match(r"https?://([^:/]+)", account_url)
    host = m.group(1) if m else "localhost"
    return (
        "DefaultEndpointsProtocol=http;"
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tfd8"
        "e9jmJAbWE56NfzFiZy7YlQ==;"
        f"BlobEndpoint=http://{host}:10000/devstoreaccount1;"
    )


class AzureBlobStorage(BlobStoragePort):
    """Azure Blob Storage implementation.

    Automatically detects Azurite (local emulator) URLs and uses the
    shared-key connection string instead of DefaultAzureCredential,
    so the service works out of the box with ``docker compose up``.
    """

    def __init__(self, account_url: str) -> None:
        self._account_url = account_url
        self._is_local = _is_azurite(account_url)
        if self._is_local:
            conn_str = _build_azurite_connection_string(account_url)
            self._credential = None
            self._client = BlobServiceClient.from_connection_string(conn_str)
        else:
            self._credential = DefaultAzureCredential()
            self._client = BlobServiceClient(
                account_url=account_url,
                credential=self._credential,
            )

    async def upload(
        self,
        container: str,
        blob_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        try:
            container_client = self._client.get_container_client(container)
            # Ensure container exists (idempotent — safe to call repeatedly)
            try:
                await container_client.create_container()
            except Exception:  # noqa: BLE001
                pass  # Container already exists — ResourceExistsError is expected
            blob_client = container_client.get_blob_client(blob_name)
            await blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
            return blob_name
        except Exception as exc:
            raise StorageError(f"Failed to upload blob '{blob_name}': {exc}") from exc

    async def download(self, container: str, blob_name: str) -> bytes:
        try:
            blob_client = self._client.get_blob_client(container=container, blob=blob_name)
            stream = await blob_client.download_blob()
            return await stream.readall()
        except Exception as exc:
            raise StorageError(f"Failed to download blob '{blob_name}': {exc}") from exc

    async def delete(self, container: str, blob_name: str) -> None:
        try:
            blob_client = self._client.get_blob_client(container=container, blob=blob_name)
            await blob_client.delete_blob()
        except Exception as exc:
            raise StorageError(f"Failed to delete blob '{blob_name}': {exc}") from exc

    async def exists(self, container: str, blob_name: str) -> bool:
        try:
            blob_client = self._client.get_blob_client(container=container, blob=blob_name)
            return await blob_client.exists()
        except Exception as exc:
            raise StorageError(f"Failed to check blob '{blob_name}': {exc}") from exc

    async def generate_sas_url(
        self,
        container: str,
        blob_name: str,
        expiry_hours: int = 1,
    ) -> str:
        """Generate a time-limited SAS URL.

        For Azurite: uses account key to generate a shared-access signature.
        For production: uses a user delegation key from Managed Identity.
        """
        try:
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            expiry = now + datetime.timedelta(hours=expiry_hours)

            if self._is_local:
                # Azurite: use account-key based SAS
                from azure.storage.blob import BlobSasPermissions, generate_blob_sas
                token = generate_blob_sas(
                    account_name=_AZURITE_ACCOUNT_NAME,
                    container_name=container,
                    blob_name=blob_name,
                    account_key=_AZURITE_ACCOUNT_KEY,
                    permission=BlobSasPermissions(read=True),
                    expiry=expiry,
                )
                return f"{self._account_url}/{container}/{blob_name}?{token}"

            # Production: user delegation key (requires Storage Blob Delegator role)
            delegation_key: UserDelegationKey = await self._client.get_user_delegation_key(
                key_start_time=now - datetime.timedelta(minutes=5),
                key_expiry_time=expiry,
            )
            token = generate_blob_sas(
                account_name=self._client.account_name,  # type: ignore[arg-type]
                container_name=container,
                blob_name=blob_name,
                user_delegation_key=delegation_key,
                permission=BlobSasPermissions(read=True),
                expiry=expiry,
            )
            return f"{self._account_url}/{container}/{blob_name}?{token}"
        except Exception as exc:
            raise StorageError(f"Failed to generate SAS URL for '{blob_name}': {exc}") from exc

    async def close(self) -> None:
        await self._client.close()
        if self._credential is not None:
            await self._credential.close()
