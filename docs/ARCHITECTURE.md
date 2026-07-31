# Architecture

## Design goals

OpenDataGraph is API-first, cloud-neutral, model-agnostic, explainable, metadata-first, tenant-aware, and safe by default. It enriches existing security and governance controls rather than replacing storage platforms, identity providers, or enterprise enforcement points.

## Components

1. **API and console** expose catalog, classification, lifecycle, policy, connector, job, evidence, AI usage, and relationship workflows.
2. **Tenant boundary** maps each authenticated principal to one tenant and applies that tenant to every data lookup and mutation.
3. **Connector SDK** emits normalized `AssetRecord` objects in cursor-aware `ScanBatch` results.
4. **Durable queue** stores bounded non-secret job payloads in the primary database and supports multiple workers, retries, cancellation, and stale-claim recovery.
5. **Connector ingestion** records runs, counts, safe errors, classification reviews, graph relationships, and derived search documents.
6. **Catalog** stores source identity, ownership, timestamps, security metadata, classification, lifecycle, and AI access context.
7. **Classification and review** combine deterministic metadata signals, optional bounded samples, optional local-model enrichment, and analyst correction.
8. **Policy engine** loads deterministic YAML rules and records explainable decisions.
9. **AI usage ingestion** records idempotent tenant-scoped activity and policy correlation.
10. **Relationship layer** stores directed tenant-scoped graph edges in the relational database.
11. **Search index** stores derived catalog metadata in OpenSearch while PostgreSQL or SQLite remains authoritative.
12. **Evidence store** keeps object bytes outside the database and records integrity and subject metadata relationally.
13. **Operations layer** provides Alembic migrations, backups, readiness, Prometheus metrics, JSON logs, and optional OTLP traces.

## Runtime topology

```text
clients / MCP
      |
identity-aware ingress
      |
API replicas ---- PostgreSQL
      |               |
      |          durable jobs
      |               |
      +---------- worker replicas
      |               |
 OpenSearch       connectors
      |
S3-compatible evidence store
```

## Persistence

PostgreSQL is recommended for shared deployments and concurrent workers. SQLite supports local development, tests, and single-worker evaluation. Alembic owns shared schema upgrades. OpenSearch is a rebuildable metadata index. Evidence bytes live in local or S3-compatible object storage; the database stores evidence metadata and digests.

## Trust boundaries

Source credentials remain outside catalog and job tables. Synchronous tokens are request-scoped. Queued connectors resolve secret references only inside workers. API keys carry role and tenant context. Production ingress must terminate TLS, validate identity, restrict `/metrics`, manage secrets externally, and isolate connector egress.

## Availability

The Helm chart runs multiple stateless API and worker replicas, performs migrations before install or upgrade, and includes readiness probes, autoscaling, a disruption budget, and a network policy. PostgreSQL, OpenSearch, object storage, ingress, secret management, and telemetry collectors should be independently resilient.
