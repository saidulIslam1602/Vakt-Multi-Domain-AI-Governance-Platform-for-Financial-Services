# ADR 002: Vector store — pgvector vs managed vector DB

**Status:** Proposed (for case presentation)  
**Date:** March 2025  
**Context:** AI-driven document automation — where to store embeddings for RAG (chat and semantic search).

## Decision

We **prefer pgvector (PostgreSQL extension)** as the initial vector store, with the option to move to a managed vector DB (e.g. Pinecone, Weaviate) if scale or features require it. Rationale: reduce operational surface, keep metadata and vectors in one place, and control cost for moderate document volumes.

## Context

- We need to store embeddings for document chunks and run approximate nearest-neighbour search for RAG.
- Metadata is already in PostgreSQL; adding vector search there avoids a separate system.
- B2B document volumes may be “moderate” (thousands to low millions of chunks) before we need dedicated vector infrastructure.
- Cost and simplicity matter for a product that must ship and iterate.

## Options considered

1. **pgvector (PostgreSQL):** Single DB for metadata + vectors; good enough for moderate scale; one backup, one connection pool. Cons: vector search performance and scale limits compared to dedicated stores.
2. **Managed vector DB (Pinecone, Weaviate, etc.):** Optimised for vector search at large scale; more features (e.g. namespaces, filtering). Cons: extra system, cost, and operational overhead.
3. **Elasticsearch/OpenSearch with vector support:** Could unify full-text and vector in one engine. Cons: heavier to operate; often more than we need for “search + RAG” at the start.

## Consequences

- **Positive:** Fewer moving parts; lower cost at moderate scale; simpler deployment and backups; same DB for metadata and vectors simplifies consistency and queries.
- **Negative:** May need to migrate to a managed vector DB later if we hit scale or need advanced features; tuning (e.g. HNSW parameters) is our responsibility.
- **Mitigation:** Keep the “vector store” behind an interface so we can swap to Pinecone/Weaviate later without changing application logic; monitor index size and query latency and define thresholds for re-evaluation.

## References

- Plan: Tech stack (Vector DB row); Scaling (Vector DB).
- Talking points: “Why pgvector vs a managed vector DB?”
