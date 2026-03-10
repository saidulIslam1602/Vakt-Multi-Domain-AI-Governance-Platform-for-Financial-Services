"""LLM-based structured extraction using Azure OpenAI with schema validation."""

from __future__ import annotations

import json

from openai import AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from allergo_shared.domain.entities import ExtractionResult
from allergo_shared.domain.exceptions import ExtractionError
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)

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
