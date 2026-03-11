"""Core domain entities shared across services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from allergo_shared.domain.enums import DocumentStatus, DocumentType
from allergo_shared.domain.value_objects import DocumentId, TenantId


class ExtractionResult(BaseModel):
    """Structured metadata extracted from a document via LLM.

    Core fields apply to all document types.
    CFO-specific fields are populated when the document is financial in nature
    (invoices, contracts, financial reports, purchase orders, etc.).
    All fields are optional so old records remain valid.
    """

    # ── Core fields (all document types) ─────────────────────────────────────
    dates: list[str] = Field(default_factory=list)
    parties: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    raw: dict[str, Any] = Field(default_factory=dict)

    # ── CFO / Finance-specific fields ─────────────────────────────────────────
    document_category: str | None = None
    """E.g. 'invoice', 'contract', 'financial_report', 'purchase_order', 'expense_claim'"""

    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    total_amount: str | None = None
    """Total amount with currency, e.g. 'NOK 125,000.00'"""
    net_amount: str | None = None
    vat_amount: str | None = None
    vat_rate: str | None = None
    currency: str | None = None

    vendor_name: str | None = None
    vendor_org_number: str | None = None
    """Norwegian organisasjonsnummer or EU VAT number"""
    vendor_address: str | None = None
    vendor_iban: str | None = None

    buyer_name: str | None = None
    buyer_org_number: str | None = None

    payment_terms: str | None = None
    """E.g. 'Net 30', 'Forfalt 30 dager'"""
    bank_account: str | None = None
    reference_number: str | None = None
    """Payment reference / KID number"""

    contract_value: str | None = None
    contract_start_date: str | None = None
    contract_end_date: str | None = None
    renewal_clause: str | None = None

    cost_center: str | None = None
    gl_account: str | None = None
    """General Ledger account code if identifiable from the document"""

    approval_required: bool = False
    """LLM-assessed flag: true when amount or terms suggest human approval needed"""

    # ── Location / store fields ────────────────────────────────────────────────
    store_location: str | None = None
    """Store, branch, or office location the document relates to"""
    department: str | None = None
    """Business department or business unit"""

    # ── Legal / compliance fields ──────────────────────────────────────────────
    governing_law: str | None = None
    """Jurisdiction or governing law clause (e.g. 'Norwegian law', 'English law')"""
    termination_clause: str | None = None
    """Summary of termination rights and notice periods"""
    penalty_clause: str | None = None
    """Penalty, liquidated damages, or exit fee description"""
    liability_cap: str | None = None
    """Limitation of liability amount or description"""
    force_majeure: bool = False
    """True if document contains a force majeure clause"""
    indemnity_clause: bool = False
    """True if document contains an indemnity / hold-harmless clause"""
    dispute_resolution: str | None = None
    """Dispute resolution mechanism (e.g. 'arbitration', 'mediation', 'court')"""
    legal_obligations: list[str] = Field(default_factory=list)
    """Key obligations with deadlines extracted from the document"""
    legal_risk_flag: bool = False
    """True if LLM detects unusual or high-risk legal terms"""

    # ── Financial report / P&L fields ─────────────────────────────────────────
    report_period: str | None = None
    """Reporting period, e.g. 'Q3 2025', 'FY2025', '2025-01-01 to 2025-03-31'"""
    report_type: str | None = None
    """Type of report: 'balance_sheet', 'income_statement', 'cash_flow', 'budget', 'forecast',
    'other'"""
    total_revenue: str | None = None
    """Total revenue / top-line figure with currency"""
    total_expenses: str | None = None
    """Total operating expenses with currency"""
    ebitda: str | None = None
    """EBITDA figure with currency if present"""
    net_profit: str | None = None
    """Net profit / net income with currency"""
    report_line_items: list[dict[str, Any]] = Field(default_factory=list)
    """Structured P&L or balance-sheet line items: [{account, amount, period}]"""

    # ── General Ledger / journal entry fields ─────────────────────────────────
    ledger_entries: list[dict[str, Any]] = Field(default_factory=list)
    """Journal entries: [{date, account_code, account_name, debit, credit, description}]"""
    posting_period: str | None = None
    """Accounting period for journal entries, e.g. '2025-02'"""
    journal_ref: str | None = None
    """Journal entry reference number"""


class Document(BaseModel):
    """Core document entity used for status tracking and metadata."""

    id: DocumentId
    tenant_id: TenantId
    filename: str
    document_type: DocumentType
    status: DocumentStatus
    blob_path: str
    raw_text_path: str | None = None
    extraction: ExtractionResult | None = None
    error_message: str | None = None
    uploaded_at: datetime
    updated_at: datetime
    page_count: int | None = None
    size_bytes: int | None = None
    content_type: str | None = None

    model_config = {"frozen": False}

    def mark_parsing(self) -> None:
        self.status = DocumentStatus.PARSING
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_parsed(self, raw_text_path: str, page_count: int | None = None) -> None:
        self.status = DocumentStatus.PARSED
        self.raw_text_path = raw_text_path
        self.page_count = page_count
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_extracting(self) -> None:
        self.status = DocumentStatus.EXTRACTING
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_extracted(self, extraction: ExtractionResult) -> None:
        self.status = DocumentStatus.EXTRACTED
        self.extraction = extraction
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_indexing(self) -> None:
        self.status = DocumentStatus.INDEXING
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_ready(self) -> None:
        self.status = DocumentStatus.READY
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_failed(self, error: str) -> None:
        self.status = DocumentStatus.FAILED
        self.error_message = error
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)


class DocumentChunk(BaseModel):
    """A chunk of document text used for embedding and RAG."""

    id: str
    document_id: str
    tenant_id: str
    chunk_index: int
    text: str
    embedding: list[float] | None = None
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
