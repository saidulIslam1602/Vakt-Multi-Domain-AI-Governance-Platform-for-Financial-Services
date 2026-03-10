"""Document repository port for the ingest service."""

from __future__ import annotations

from abc import ABC, abstractmethod

from allergo_shared.domain.entities import Document


class DocumentRepository(ABC):
    """Persistence contract for document records."""

    @abstractmethod
    async def save(self, document: Document) -> None:
        """Persist a new or updated document record."""

    @abstractmethod
    async def get_by_id(self, document_id: str, tenant_id: str) -> Document | None:
        """Return a document by id scoped to a tenant, or None."""

    @abstractmethod
    async def list_by_tenant(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Document]:
        """Return a page of documents for a tenant."""
