# Architecture

## Design goals

OpenDataGraph is API-first, cloud-neutral, model-agnostic, explainable, and safe by default. It is intended to enrich existing security and governance controls rather than replace every catalog, DLP, or storage platform.

## V1 components

1. **Connector layer** — discovers source metadata and maps it to a normalized asset record. AWS S3 is the first live adapter.
2. **Normalized catalog** — stores source identity, ownership, size, timestamps, security metadata, classifications, and lifecycle findings.
3. **Classification engine** — evaluates deterministic metadata indicators and optionally calls a locally hosted Ollama model. Hybrid mode falls back safely.
4. **Lifecycle engine** — computes age, inactivity, stale score, lifecycle state, and advisory retention actions.
5. **Policy decision point** — evaluates whether an asset can be sent, summarized, embedded, or used for training at a named AI destination.
6. **Dashboard and API** — gives humans a clear demo experience and allows AI gateways to consume the same intelligence programmatically.

## Data age semantics

`created_at`, `modified_at`, and `last_accessed_at` are retained separately because sources expose different levels of evidence. `age_days` is based on creation when available, then modification, then discovery time. Lifecycle inactivity is based on last access when available, otherwise modification. Every future connector should document timestamp provenance and confidence.

## Production evolution

A production architecture should replace SQLite with PostgreSQL, use a queue for connector and enrichment jobs, add object-level authorization, encrypt secrets through a dedicated secret manager, and separate the control plane from workers. OpenSearch may be added for large-scale search; Apache AGE or another graph store may be added only when graph queries justify the operational cost.
