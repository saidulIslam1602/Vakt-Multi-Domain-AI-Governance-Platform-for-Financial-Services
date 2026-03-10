# Talking Points — AI-Driven Document Automation

Use these 1–2 sentence answers when they ask follow-up questions. Adapt wording to the flow of the conversation.

---

## 3. Tech Stack

**Why a queue instead of processing uploads synchronously?**  
We need to decouple upload from processing so the API stays fast and we can scale workers independently. A queue gives us retries, dead-letter handling, and at-least-once processing without blocking the user.

**Why PostgreSQL for metadata and possibly search?**  
PostgreSQL gives us relational metadata, JSONB for flexible extracted fields, and built-in full-text search. That’s enough for many B2B volumes and keeps the system simpler. We can add Elasticsearch later if we outgrow it.

**Why pgvector vs a managed vector DB?**  
pgvector keeps everything in one database and reduces operational surface. It’s a good fit for moderate scale and cost control. We’d consider Pinecone or Weaviate if we need very large-scale or specialized vector features.

**Why Tika plus a PDF library?**  
Tika handles many formats out of the box. For PDFs we add PyMuPDF or pdfplumber for better text and table extraction. That combination covers most document types we’d see in B2B.

**Why LLM for extraction instead of only rule-based parsing?**  
Documents vary in layout and wording. An LLM with structured output lets us extract dates, parties, amounts, and terms across formats without hand-writing rules for each template. We validate and optionally retry or flag for human review.

---

## 4. Document Processing Flow

**What happens when a document fails parsing?**  
The worker retries with backoff. After a defined number of failures it goes to a dead-letter queue so we can inspect and fix (e.g. unsupported format or corrupted file) without blocking the rest of the pipeline.

**How do you avoid processing the same document twice?**  
Jobs are idempotent and keyed by document id. If we enqueue the same document again (e.g. retry), we check whether we already have metadata for that id and skip or overwrite according to policy.

**Where does OCR fit in?**  
OCR runs inside the parse step when we detect an image-only PDF or scanned document. We use Tesseract or a cloud OCR API depending on cost and accuracy requirements, then feed the text into the same extraction and indexing pipeline.

**How do extraction and indexing relate?**  
Parse produces raw text. One path goes to the extraction service (LLM) and then to the metadata DB. Another path goes to chunking, embedding, and the vector DB, plus full-text index. Both can be separate workers consuming from the same or chained queues.

---

## 5. Scaling

**How would you scale the extractor?**  
Workers are stateless and pull from the queue. We scale the number of workers based on queue depth (e.g. Kubernetes HPA or serverless on queue length). The bottleneck is usually LLM rate limits or cost, so we might batch or throttle and scale workers within that constraint.

**What if the queue backs up?**  
We’d scale up workers and check for slow or failing downstream services (DB, blob, LLM). Runbooks would cover this: alert on queue depth, scale workers, and if needed temporarily pause ingest or add more queue partitions.

**How do you keep the vector DB from becoming a bottleneck?**  
We batch embedding requests, use approximate search (e.g. HNSW), and shard by tenant if we’re multi-tenant. For very large scale we’d consider a dedicated vector store and possibly separate indexing pipelines per tenant or document type.

**How do you control cost at scale?**  
We use spot or preemptible instances for workers where we can tolerate interruption, lifecycle policies on blob storage (e.g. cold after 90 days), and we monitor and cap AI usage (extraction and chat) per tenant or overall. Caching embeddings and reusing them for search and RAG avoids re-embedding the same content.

---

## 6. Clean Architecture

**How is the codebase structured?**  
We’d use clear layers: presentation (API, chat endpoint), application (orchestration and use cases), domain (entities and extraction contract), and infrastructure (blob, queue, DB, LLM client). Dependencies point inward; infrastructure implements interfaces defined in the domain or application layer.

**Why keep extraction behind an interface?**  
So we can swap providers (e.g. different LLM or document AI API) or add a new document type with a new adapter without changing the core flow. The same applies to storage and the queue—we can test use cases with mocks and change infrastructure for cost or scale later.

**How would you add a new document type?**  
Define the extraction schema and possibly a new parser or OCR path. Implement an adapter that satisfies the extraction interface and register it (config or factory). No change to the core pipeline logic if the contract stays the same.

---

## 7. Production Readiness

**How do you observe the pipeline?**  
Structured logs with request and job ids so we can trace a document from upload to index. Metrics for throughput, latency, and error rate per stage (upload, parse, extract, index). Dashboards and alerts on queue depth, failure rate, and LLM latency/cost.

**How do you handle tenant isolation?**  
Every blob path and DB row is scoped by tenant id. APIs resolve tenant from auth and only return or modify that tenant’s data. Queue messages carry tenant id so workers never mix data between tenants.

**What if the LLM is slow or down?**  
We’d use timeouts and a circuit breaker so we don’t pile up requests. Failed extraction jobs go to DLQ or retry with backoff. We can degrade to “pending extraction” in the UI and process when the service recovers.

**How is infrastructure managed?**  
Infrastructure as code (e.g. Terraform or Pulumi) for blob, queue, DB, and optional vector store. CI/CD for the application services. Runbooks for common incidents (queue backup, extraction failures, high latency).

---

## 8. Cost

**What drives cost the most?**  
AI usage: extraction per document, embeddings per chunk, and chat per query. After that, blob and database storage and compute for workers. We’d set budgets and alerts per tenant or overall and optimize the biggest levers first.

**How do you reduce AI cost?**  
Cache embeddings so we don’t re-embed unchanged content. Batch extraction where the API allows. Use a smaller or cheaper model for extraction if accuracy is acceptable. For chat, limit context size and cache frequent queries or answers where it makes sense.

**Why mention labour cost in the proposal?**  
Good architecture and documentation reduce long-term cost: faster onboarding, safer changes, and fewer incidents. We’d invest in ADRs, API specs, and runbooks so the team can iterate without constant rediscovery.

---

*Use these as a base; shorten or expand depending on how deep they want to go.*
