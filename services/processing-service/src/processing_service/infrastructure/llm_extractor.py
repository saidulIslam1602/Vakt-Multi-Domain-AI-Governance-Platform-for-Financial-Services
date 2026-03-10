"""LLM-based structured extraction using Azure OpenAI with schema validation."""

from __future__ import annotations

import json

from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from allergo_shared.domain.entities import ExtractionResult
from allergo_shared.domain.exceptions import ExtractionError
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Each GPT-4o call receives at most this many characters (~30k tokens budget).
# For long documents we run multiple passes and merge results.
_CHARS_PER_PASS = 40_000
# First pass always covers the opening section (most fields live here).
_FIRST_PASS_CHARS = 40_000

_SYSTEM_PROMPT = """You are a financial and legal document analysis assistant for a CFO management platform.
Extract structured information from the provided document text.
Return ONLY a valid JSON object matching the schema below. Never add explanations or markdown.

The platform is used by CFOs and finance teams. Prioritise financial accuracy.
For Norwegian documents: extract KID number as reference_number, use NOK as currency default.

Schema (all fields optional — only include when confidently present):
{
  "document_category": "invoice|contract|financial_report|purchase_order|expense_claim|other",
  "dates": ["ISO 8601 dates found"],
  "parties": ["Names of companies, persons, or organisations"],
  "amounts": ["All monetary amounts with currency, e.g. NOK 50,000"],
  "key_terms": ["Important domain-specific terms, max 10"],
  "summary": "One paragraph summary (max 200 words)",
  "confidence_score": 0.0,

  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "total_amount": "NOK 125,000.00 or null",
  "net_amount": "string or null",
  "vat_amount": "string or null",
  "vat_rate": "25% or null",
  "currency": "NOK|EUR|USD|... or null",

  "vendor_name": "string or null",
  "vendor_org_number": "string or null",
  "vendor_address": "string or null",
  "vendor_iban": "string or null",

  "buyer_name": "string or null",
  "buyer_org_number": "string or null",

  "payment_terms": "Net 30 or null",
  "bank_account": "string or null",
  "reference_number": "KID or payment ref or null",

  "contract_value": "string or null",
  "contract_start_date": "YYYY-MM-DD or null",
  "contract_end_date": "YYYY-MM-DD or null",
  "renewal_clause": "string describing renewal terms or null",

  "cost_center": "string or null",
  "gl_account": "string or null",

  "approval_required": true,

  "store_location": "store, branch, or office name/location this document relates to or null",
  "department": "business department or unit or null",

  "governing_law": "jurisdiction or governing law clause or null",
  "termination_clause": "summary of termination rights and notice periods or null",
  "penalty_clause": "description of penalty, liquidated damages, or exit fee or null",
  "liability_cap": "limitation of liability amount or description or null",
  "force_majeure": false,
  "indemnity_clause": false,
  "dispute_resolution": "arbitration|mediation|court|other or null",
  "legal_obligations": ["obligation with deadline, e.g. 'Notify within 30 days of breach'"],
  "legal_risk_flag": false,

  "report_period": "e.g. Q3 2025 or FY2025 or null",
  "report_type": "balance_sheet|income_statement|cash_flow|budget|forecast|other or null",
  "total_revenue": "amount with currency or null",
  "total_expenses": "amount with currency or null",
  "ebitda": "amount with currency or null",
  "net_profit": "amount with currency or null",
  "report_line_items": [{"account": "Revenue", "amount": "NOK 5,200,000", "period": "2025-Q3"}],

  "ledger_entries": [
    {"date": "YYYY-MM-DD", "account_code": "6400", "account_name": "Leiekostnad", "debit": "NOK 50,000", "credit": null, "description": "Monthly rent Bergen"}
  ],
  "posting_period": "YYYY-MM or null",
  "journal_ref": "journal entry reference number or null"
}

Rules:
- Set confidence_score 0.0 (very uncertain) to 1.0 (very confident).
- Set approval_required true if total amount exceeds NOK 100,000 OR document contains unusual payment terms.
- Set legal_risk_flag true if document contains non-standard liability caps, unusual penalty clauses, missing limitation of liability, or one-sided termination rights.
- Set force_majeure / indemnity_clause true only if the clause is explicitly present.
- For report_line_items extract up to 30 key line items; for ledger_entries extract up to 50 rows.
- For legal_obligations include deadline where available, e.g. 'Notice of termination: 6 months before contract_end_date'.
"""

_MERGE_SYSTEM_PROMPT = """You are merging two partial JSON extraction results from different sections of the same document.
Return ONLY a single merged JSON object. Rules:
- For string fields: prefer the non-null value; if both non-null prefer first_pass unless second_pass is clearly more complete.
- For list fields (dates, parties, amounts, key_terms, legal_obligations, report_line_items, ledger_entries): concatenate and deduplicate.
- For boolean fields: use logical OR (true if either is true).
- For confidence_score: use the minimum of the two values.
- Do not add new fields. Do not lose any field present in either input.
"""

CONFIDENCE_REVIEW_THRESHOLD = 0.70


class LLMExtractor:
    def __init__(
        self,
        client: AsyncAzureOpenAI,
        deployment: str,
        max_retries: int = 3,
    ) -> None:
        self._client = client
        self._deployment = deployment
        self._max_retries = max_retries

    async def extract(self, text: str, document_id: str) -> ExtractionResult:
        """Multi-pass extraction: first pass on opening section, additional passes
        for subsequent segments, then merge all results into one ExtractionResult."""

        segments = _split_into_segments(text)
        logger.info(
            "extraction_segments",
            document_id=document_id,
            segment_count=len(segments),
            total_chars=len(text),
        )

        # Extract first segment (always present)
        merged = await self._extract_segment(segments[0], document_id, pass_num=1)

        # Extract remaining segments and merge progressively
        for i, segment in enumerate(segments[1:], start=2):
            partial = await self._extract_segment(segment, document_id, pass_num=i)
            merged = await self._merge(merged, partial, document_id)

        return _build_result(merged, document_id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _extract_segment(
        self, text: str, document_id: str, pass_num: int
    ) -> dict:
        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Document text (segment {pass_num}):\n\n{text}"},
                ],
                temperature=0.0,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise ExtractionError(
                f"LLM call failed for document '{document_id}' segment {pass_num}: {exc}"
            ) from exc

        raw_content = response.choices[0].message.content or "{}"
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                f"LLM returned invalid JSON for document '{document_id}' segment {pass_num}: "
                f"{raw_content[:200]}"
            ) from exc

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _merge(
        self, first: dict, second: dict, document_id: str
    ) -> dict:
        """Ask the LLM to merge two partial extraction dicts into one."""
        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": _MERGE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"first_pass:\n{json.dumps(first, ensure_ascii=False)}\n\n"
                            f"second_pass:\n{json.dumps(second, ensure_ascii=False)}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning(
                "merge_failed_using_first",
                document_id=document_id,
                error=str(exc),
            )
            return first  # graceful degradation

        raw = response.choices[0].message.content or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return first  # graceful degradation


def _split_into_segments(text: str) -> list[str]:
    """Split text into segments of at most _CHARS_PER_PASS characters.
    The first segment always gets the full _FIRST_PASS_CHARS budget."""
    if len(text) <= _FIRST_PASS_CHARS:
        return [text]

    segments: list[str] = [text[:_FIRST_PASS_CHARS]]
    pos = _FIRST_PASS_CHARS
    while pos < len(text):
        segments.append(text[pos : pos + _CHARS_PER_PASS])
        pos += _CHARS_PER_PASS
    return segments


def _build_result(parsed: dict, document_id: str) -> ExtractionResult:
    """Map a raw parsed dict to ExtractionResult, log, and return."""
    confidence = float(parsed.get("confidence_score", 0.5))
    result = ExtractionResult(
        # Core
        dates=parsed.get("dates", []),
        parties=parsed.get("parties", []),
        amounts=parsed.get("amounts", []),
        key_terms=parsed.get("key_terms", []),
        summary=parsed.get("summary", ""),
        confidence_score=confidence,
        raw=parsed,
        # Invoice / PO
        document_category=parsed.get("document_category"),
        invoice_number=parsed.get("invoice_number"),
        invoice_date=parsed.get("invoice_date"),
        due_date=parsed.get("due_date"),
        total_amount=parsed.get("total_amount"),
        net_amount=parsed.get("net_amount"),
        vat_amount=parsed.get("vat_amount"),
        vat_rate=parsed.get("vat_rate"),
        currency=parsed.get("currency"),
        vendor_name=parsed.get("vendor_name"),
        vendor_org_number=parsed.get("vendor_org_number"),
        vendor_address=parsed.get("vendor_address"),
        vendor_iban=parsed.get("vendor_iban"),
        buyer_name=parsed.get("buyer_name"),
        buyer_org_number=parsed.get("buyer_org_number"),
        payment_terms=parsed.get("payment_terms"),
        bank_account=parsed.get("bank_account"),
        reference_number=parsed.get("reference_number"),
        # Contract
        contract_value=parsed.get("contract_value"),
        contract_start_date=parsed.get("contract_start_date"),
        contract_end_date=parsed.get("contract_end_date"),
        renewal_clause=parsed.get("renewal_clause"),
        # Accounting
        cost_center=parsed.get("cost_center"),
        gl_account=parsed.get("gl_account"),
        approval_required=bool(parsed.get("approval_required", False)),
        # Location
        store_location=parsed.get("store_location"),
        department=parsed.get("department"),
        # Legal
        governing_law=parsed.get("governing_law"),
        termination_clause=parsed.get("termination_clause"),
        penalty_clause=parsed.get("penalty_clause"),
        liability_cap=parsed.get("liability_cap"),
        force_majeure=bool(parsed.get("force_majeure", False)),
        indemnity_clause=bool(parsed.get("indemnity_clause", False)),
        dispute_resolution=parsed.get("dispute_resolution"),
        legal_obligations=parsed.get("legal_obligations", []),
        legal_risk_flag=bool(parsed.get("legal_risk_flag", False)),
        # Financial reports
        report_period=parsed.get("report_period"),
        report_type=parsed.get("report_type"),
        total_revenue=parsed.get("total_revenue"),
        total_expenses=parsed.get("total_expenses"),
        ebitda=parsed.get("ebitda"),
        net_profit=parsed.get("net_profit"),
        report_line_items=parsed.get("report_line_items", []),
        # Ledger
        ledger_entries=parsed.get("ledger_entries", []),
        posting_period=parsed.get("posting_period"),
        journal_ref=parsed.get("journal_ref"),
    )
    logger.info(
        "extraction_complete",
        document_id=document_id,
        confidence=confidence,
        needs_review=confidence < CONFIDENCE_REVIEW_THRESHOLD,
        category=result.document_category,
        approval_required=result.approval_required,
        legal_risk_flag=result.legal_risk_flag,
        ledger_entries=len(result.ledger_entries),
        report_line_items=len(result.report_line_items),
    )
    return result


_SYSTEM_PROMPT = """You are a financial document analysis assistant for a CFO management platform.
Extract structured information from the provided document text.
Return ONLY a valid JSON object matching the schema below. Never add explanations or markdown.

The platform is used by CFOs and finance teams. Prioritise financial accuracy.
For Norwegian documents: extract KID number as reference_number, use NOK as currency default.

Schema (all fields optional — only include when confidently present):
{
  "document_category": "invoice|contract|financial_report|purchase_order|expense_claim|other",
  "dates": ["ISO 8601 dates found"],
  "parties": ["Names of companies, persons, or organisations"],
  "amounts": ["All monetary amounts with currency, e.g. NOK 50,000"],
  "key_terms": ["Important domain-specific terms, max 10"],
  "summary": "One paragraph summary (max 200 words)",
  "confidence_score": 0.0,

  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "total_amount": "NOK 125,000.00 or null",
  "net_amount": "string or null",
  "vat_amount": "string or null",
  "vat_rate": "25% or null",
  "currency": "NOK|EUR|USD|... or null",

  "vendor_name": "string or null",
  "vendor_org_number": "string or null",
  "vendor_address": "string or null",
  "vendor_iban": "string or null",

  "buyer_name": "string or null",
  "buyer_org_number": "string or null",

  "payment_terms": "Net 30 or null",
  "bank_account": "string or null",
  "reference_number": "KID or payment ref or null",

  "contract_value": "string or null",
  "contract_start_date": "YYYY-MM-DD or null",
  "contract_end_date": "YYYY-MM-DD or null",
  "renewal_clause": "string describing renewal terms or null",

  "cost_center": "string or null",
  "gl_account": "string or null",

  "approval_required": true
}

Set confidence_score between 0.0 (very uncertain) and 1.0 (very confident).
Set approval_required to true if the total amount exceeds NOK 100,000 or if the document contains unusual payment terms.
"""

CONFIDENCE_REVIEW_THRESHOLD = 0.70


class LLMExtractor:
    def __init__(
        self,
        client: AsyncAzureOpenAI,
        deployment: str,
        max_retries: int = 3,
    ) -> None:
        self._client = client
        self._deployment = deployment
        self._max_retries = max_retries

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def extract(self, text: str, document_id: str) -> ExtractionResult:
        truncated = text[:12000]  # ~3000 tokens

        try:
            response = await self._client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Document text:\n\n{truncated}"},
                ],
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise ExtractionError(f"LLM call failed for document '{document_id}': {exc}") from exc

        raw_content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                f"LLM returned invalid JSON for document '{document_id}': {raw_content[:200]}"
            ) from exc

        confidence = float(parsed.get("confidence_score", 0.5))
        result = ExtractionResult(
            dates=parsed.get("dates", []),
            parties=parsed.get("parties", []),
            amounts=parsed.get("amounts", []),
            key_terms=parsed.get("key_terms", []),
            summary=parsed.get("summary", ""),
            confidence_score=confidence,
            raw=parsed,
            # CFO fields
            document_category=parsed.get("document_category"),
            invoice_number=parsed.get("invoice_number"),
            invoice_date=parsed.get("invoice_date"),
            due_date=parsed.get("due_date"),
            total_amount=parsed.get("total_amount"),
            net_amount=parsed.get("net_amount"),
            vat_amount=parsed.get("vat_amount"),
            vat_rate=parsed.get("vat_rate"),
            currency=parsed.get("currency"),
            vendor_name=parsed.get("vendor_name"),
            vendor_org_number=parsed.get("vendor_org_number"),
            vendor_address=parsed.get("vendor_address"),
            vendor_iban=parsed.get("vendor_iban"),
            buyer_name=parsed.get("buyer_name"),
            buyer_org_number=parsed.get("buyer_org_number"),
            payment_terms=parsed.get("payment_terms"),
            bank_account=parsed.get("bank_account"),
            reference_number=parsed.get("reference_number"),
            contract_value=parsed.get("contract_value"),
            contract_start_date=parsed.get("contract_start_date"),
            contract_end_date=parsed.get("contract_end_date"),
            renewal_clause=parsed.get("renewal_clause"),
            cost_center=parsed.get("cost_center"),
            gl_account=parsed.get("gl_account"),
            approval_required=bool(parsed.get("approval_required", False)),
        )
        logger.info(
            "extraction_complete",
            document_id=document_id,
            confidence=confidence,
            needs_review=confidence < CONFIDENCE_REVIEW_THRESHOLD,
            category=result.document_category,
            approval_required=result.approval_required,
        )
        return result
