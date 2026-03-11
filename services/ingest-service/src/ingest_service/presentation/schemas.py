"""Request and response schemas for the ingest service API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from allergo_shared.domain.enums import DocumentStatus, DocumentType


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    status: DocumentStatus
    document_type: DocumentType
    size_bytes: int | None
    uploaded_at: datetime
    message: str = "Document uploaded and queued for processing."


class DocumentResponse(BaseModel):
    document_id: str
    tenant_id: str
    filename: str
    status: DocumentStatus
    document_type: DocumentType
    blob_path: str
    size_bytes: int | None
    page_count: int | None
    error_message: str | None
    uploaded_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int = Field(default=50)
    offset: int = Field(default=0)


class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: str | None = None


class BulkUploadItem(BaseModel):
    filename: str
    document_id: str | None = None
    status: str  # "queued" | "skipped" | "error"
    error: str | None = None


class BulkUploadResponse(BaseModel):
    total_files: int
    queued: int
    skipped: int
    errors: int
    results: list[BulkUploadItem]
