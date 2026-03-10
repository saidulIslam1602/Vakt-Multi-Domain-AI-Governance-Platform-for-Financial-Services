"""Domain exceptions shared across all services."""

from __future__ import annotations


class AllergoError(Exception):
    """Base exception for all Allergo Nordic services."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class DocumentNotFoundError(AllergoError):
    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document '{document_id}' not found.", code="DOCUMENT_NOT_FOUND")
        self.document_id = document_id


class ValidationError(AllergoError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, code="VALIDATION_ERROR")


class StorageError(AllergoError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, code="STORAGE_ERROR")


class ExtractionError(AllergoError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, code="EXTRACTION_ERROR")


class IndexingError(AllergoError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, code="INDEXING_ERROR")


class QueueError(AllergoError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail, code="QUEUE_ERROR")


class AuthorizationError(AllergoError):
    def __init__(self, detail: str = "Access denied.") -> None:
        super().__init__(detail, code="AUTHORIZATION_ERROR")
