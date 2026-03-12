"""Domain enumerations shared across all services."""

from enum import Enum


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    TXT = "txt"
    HTML = "html"
    IMAGE = "image"
    UNKNOWN = "unknown"


class JobEventType(str, Enum):
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_PARSED = "document.parsed"
    DOCUMENT_EXTRACTED = "document.extracted"
    DOCUMENT_INDEXED = "document.indexed"
    DOCUMENT_FAILED = "document.failed"
