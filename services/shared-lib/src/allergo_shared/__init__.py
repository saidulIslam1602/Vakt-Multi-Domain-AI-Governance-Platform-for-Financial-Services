"""Allergo Nordic shared library — common domain primitives, Azure clients, and utilities."""

from allergo_shared.domain.entities import Document, DocumentChunk, ExtractionResult
from allergo_shared.domain.enums import DocumentStatus, DocumentType
from allergo_shared.domain.exceptions import (
    AllergoError,
    DocumentNotFoundError,
    ExtractionError,
    StorageError,
    ValidationError,
)
from allergo_shared.domain.value_objects import DocumentId, TenantId

__all__ = [
    "Document",
    "DocumentChunk",
    "ExtractionResult",
    "DocumentStatus",
    "DocumentType",
    "AllergoError",
    "DocumentNotFoundError",
    "ExtractionError",
    "StorageError",
    "ValidationError",
    "DocumentId",
    "TenantId",
]
