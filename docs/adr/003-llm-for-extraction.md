# ADR 003: Use LLM for structured extraction from documents

**Status:** Proposed (for case presentation)  
**Date:** March 2025  
**Context:** AI-driven document automation — how to extract key elements (dates, parties, amounts, key terms) from documents.

## Decision

We use an **LLM with structured output** (or a document AI API with similar capabilities) as the primary mechanism for extracting structured metadata from document text. We define a schema (e.g. JSON schema) for the extracted fields, validate the model output, and support retries or human-in-the-loop for low-confidence or invalid results.

## Context

- Documents vary in layout, wording, and format; rule-based or template-only extraction does not scale across many document types.
- We need dates, parties, amounts, and key terms as structured metadata for display, edit, and integration.
- LLMs can generalise across formats and languages when given a clear schema and examples.
- Cost and latency are concerns: extraction runs per document and can be a major variable cost.

## Options considered

1. **LLM with structured output (chosen):** Flexible across document types; schema enforces shape; we can tune prompts and add validation. Cons: cost per doc, latency, need for validation and fallbacks.
2. **Rule-based / regex / template parsing:** Low cost and predictable. Cons: does not generalise; high maintenance for each new document type or layout.
3. **Document AI APIs (e.g. AWS Textract, Google Document AI):** Good for forms and invoices with pre-built entities. Cons: vendor lock-in, cost, and may not cover all document types we need; can be combined with LLM for hybrid extraction later.

## Consequences

- **Positive:** One extraction path that can handle many document types; easier to add new fields or document types by updating schema and prompts; aligns with “AI to the maximum” in development and product.
- **Negative:** Variable cost (tokens per document); need rate limiting, retries, and circuit breakers; must validate and sanitise output; optional human review for edge cases.
- **Mitigation:** Cache or skip re-extraction when document content is unchanged; use a smaller or cheaper model where accuracy is sufficient; batch where the API allows; store confidence scores and flag low-confidence extractions for review.

## References

- Plan: Document processing flow (Extract step); Tech stack (AI extraction).
- Talking points: “Why LLM for extraction instead of only rule-based parsing?”
