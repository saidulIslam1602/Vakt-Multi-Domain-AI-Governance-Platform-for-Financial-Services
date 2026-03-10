# ADR 001: Queue-based document processing

**Status:** Proposed (for case presentation)  
**Date:** March 2025  
**Context:** AI-driven document automation — how to handle upload and processing of large volumes of documents.

## Decision

We use an **asynchronous, queue-based pipeline** for document processing. The upload API accepts files, stores them in blob storage, and enqueues one job per document (or per batch). Workers pull jobs from the queue and perform parse → extract → index. Upload responds quickly; processing runs in the background.

## Context

- Documents can be large; parsing and AI extraction take seconds to minutes.
- Synchronous processing would tie up the API and cause timeouts and poor UX.
- We need to scale processing independently of upload traffic and handle failures without losing work.
- Multiple document types and optional steps (e.g. OCR) make the pipeline variable in duration and resource use.

## Options considered

1. **Synchronous:** Upload and process in the same request. Rejected: slow responses, no natural retry, hard to scale.
2. **Queue-based (chosen):** Upload → blob + enqueue; workers process. Pros: decoupling, retries, DLQ, horizontal scaling of workers.
3. **Event-driven (e.g. blob events trigger processing):** Viable but ties us to a specific cloud; queue is more portable and explicit.

## Consequences

- **Positive:** Fast upload response; workers scale with queue depth; retries and DLQ for failed jobs; clear observability (queue depth, processing latency).
- **Negative:** Eventually consistent (metadata/search available after processing); need to design job idempotency and document identity; operational dependency on queue and workers.
- **Mitigation:** Job status API so frontend can poll or show “processing”; idempotent jobs keyed by document id; runbooks for queue backup and worker failures.

## References

- Plan: Document processing flow (upload → parse → extract → index).
- Talking points: “Why a queue instead of processing uploads synchronously?”
