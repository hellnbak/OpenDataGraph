# Architecture

## Design goals

OpenDataGraph is API-first, cloud-neutral, model-agnostic, explainable, metadata-first, tenant-aware, and safe by default. It enriches existing security and governance controls rather than replacing storage platforms, identity providers, or enterprise enforcement points.

## Components

1. **API and console** expose catalog, classification, lifecycle, policy, connector, schedule, identity, service-account, governance, ownership, evidence, integration, AI usage, lineage, and relationship workflows.
2. **Tenant boundary** maps each API-key, service account, validated human OIDC principal, or fixed-trust workload identity to one tenant and applies that tenant to every data lookup and mutation.
3. **Connector SDK** emits normalized `AssetRecord` objects in cursor-aware `ScanBatch` results.
4. **Durable queue and scheduler** store bounded non-secret job payloads, atomically enqueue due connector and ownership interval or time-zone-aware cron schedules outside maintenance windows, share provider request budgets, and support multiple workers, retries, cancellation, and stale-claim recovery.
5. **Connector ingestion** records runs, counts, safe errors, classification reviews, graph relationships, and derived search documents.
6. **Catalog** stores source identity, ownership, timestamps, security metadata, classification, lifecycle, and AI access context.
7. **Classification and review** combine deterministic metadata signals, optional bounded samples, optional local-model enrichment, and analyst correction.
8. **Policy governance** evaluates deterministic YAML or active versioned bundles and records explainable decisions, change diffs, delegated approvals, activation, rollback, scoped exceptions, and renewal.
9. **AI usage ingestion** records idempotent tenant-scoped activity and policy correlation.
10. **Relationship and lineage layer** stores indexed directed tenant-scoped graph edges, OpenLineage events, bounded multi-hop traversal, path explanations, synchronous export, and asynchronous integrity-checked export jobs with pluggable governed sinks.
11. **Search index** stores derived catalog metadata in OpenSearch while PostgreSQL or SQLite remains authoritative.
12. **Evidence governance** keeps object bytes outside the database and records integrity, subject, retention, application legal hold, object-lock verification, disposition approval, and deletion metadata relationally.
13. **Identity plane** validates configured human OIDC providers with cached discovery and short-lived workload providers with fixed tenant and role trust; manages tenant-scoped SCIM users, groups, Bulk requests, and durable deprovisioning; and issues hashed, rotating service-account credentials.
14. **Governance operations** unify policy and evidence reviews, deadlines, assignment, SLA reporting, analytics, metadata-only evidence packages, notifications, scheduled ownership attestations, and remediation.
15. **Integration plane** queues allowlisted native, CloudEvents, CEF, or Splunk HEC events with dead-letter recovery and controlled replay without performing source-system mutations.
16. **Operations layer** provides Alembic migrations, backups, readiness, Prometheus metrics, JSON logs, optional OTLP traces, deterministic and PostgreSQL benchmark profiles, read-only query plans, and soak tooling.

## Runtime topology

```text
clients / MCP
      |
identity-aware ingress
      |
API replicas ---- PostgreSQL
      |          /    |     \
      |    schedules  jobs   governance
      |               |
      +---------- worker replicas ----- approved webhooks / HTTPS sinks
      |               |
 OpenSearch       connectors ---- graph export / governance package stores
      |
S3-compatible evidence store
```

## Persistence

PostgreSQL is recommended for shared deployments and concurrent workers. SQLite supports local development, tests, and single-worker evaluation. Alembic owns shared schema upgrades. OpenSearch is a rebuildable metadata index. Evidence, graph-export, and governance-package bytes live in configured local or S3-compatible object storage; the database stores metadata, state, and digests.

## Trust boundaries

Source credentials remain outside catalog and job tables. Synchronous tokens are request-scoped. Queued connectors and webhook integrations resolve secret references only inside workers after endpoint validation. API keys, service accounts, validated human OIDC tokens, and fixed-trust workload identities carry role and tenant context. Service-account verifiers are salted and clear keys are one-time responses. OIDC discovery and discovered JWKS hosts are bounded by provider configuration. SCIM uses a dedicated tenant-bound credential. Graph export sinks require explicit bucket or host allowlisting and workload identity; HTTPS sinks read mounted short-lived tokens only during delivery. Production ingress must terminate TLS, restrict `/metrics`, manage secrets externally, and isolate connector, integration, and export egress.

## Availability

The Helm chart runs multiple stateless API and worker replicas, performs migrations before install or upgrade, and includes readiness probes, autoscaling, a disruption budget, and a network policy. PostgreSQL, OpenSearch, object storage, ingress, secret management, and telemetry collectors should be independently resilient.
