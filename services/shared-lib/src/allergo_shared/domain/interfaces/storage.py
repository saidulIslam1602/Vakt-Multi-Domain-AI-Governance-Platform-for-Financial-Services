"""Storage port — abstraction over blob/object storage."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BlobStoragePort(ABC):
    """Interface for blob storage operations."""

    @abstractmethod
    async def upload(
        self,
        container: str,
        blob_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes and return the blob URL/path."""

    @abstractmethod
    async def download(self, container: str, blob_name: str) -> bytes:
        """Download blob contents as bytes."""

    @abstractmethod
    async def delete(self, container: str, blob_name: str) -> None:
        """Delete a blob."""

    @abstractmethod
    async def exists(self, container: str, blob_name: str) -> bool:
        """Check if a blob exists."""

    @abstractmethod
    async def generate_sas_url(
        self,
        container: str,
        blob_name: str,
        expiry_hours: int = 1,
    ) -> str:
        """Generate a time-limited SAS URL for a blob."""
