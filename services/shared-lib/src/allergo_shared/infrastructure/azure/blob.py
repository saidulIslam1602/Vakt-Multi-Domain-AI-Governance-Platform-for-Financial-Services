"""Azure Blob Storage adapter — implements BlobStoragePort."""

from __future__ import annotations

import datetime

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions, UserDelegationKey

from allergo_shared.domain.exceptions import StorageError
from allergo_shared.domain.interfaces.storage import BlobStoragePort


class AzureBlobStorage(BlobStoragePort):
    """Production Azure Blob Storage implementation."""

    def __init__(self, account_url: str) -> None:
        self._account_url = account_url
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
            blob_client = container_client.get_blob_client(blob_name)
            await blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings={"content_type": content_type},
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
        """Generate a time-limited SAS URL using a user delegation key (Managed Identity)."""
        try:
            now = datetime.datetime.utcnow()
            expiry = now + datetime.timedelta(hours=expiry_hours)
            # User delegation key requires the identity to have Storage Blob Delegator role.
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
        await self._credential.close()
