# Architecture

## Design goals

OpenDataGraph is API-first, cloud-neutral, model-agnostic, explainable, metadata-first, tenant-aware, and safe by default. It enriches existing security and governance controls rather than replacing storage platforms, identity providers, or enterprise enforcement points.

## Components

1. **API and console** expose catalog, classification, lifecycle, policy, rollout, runtime authorization and enforcement, AI resource, telemetry, connector, schedule, identity, service-account, governance, ownership, evidence, integration, AI usage, lineage, relationship, and stateless MCP workflows.
2. **Tenant boundary** maps each API-key, service account, validated human OIDC principal, or fixed-trust workload identity to one tenant and applies that tenant to every data lookup and mutation.
3. **Connector SDK and registry** emit normalized `AssetRecord` objects in cursor-aware `ScanBatch` results and govern versioned capability manifests, conformance, explicitly allowlisted plugins, and deployment plus tenant capability policy.
4. **Durable queue and scheduler** store bounded non-secret job payloads, atomically enqueue due connector and ownership interval or time-zone-aware cron schedules and campaign escalation stages outside maintenance windows, share provider request budgets, and support multiple workers, retries, cancellation, idempotent integration delivery, and stale-claim recovery.
5. **Connector ingestion** records runs, capability provenance, counts, safe errors, classification reviews, graph relationships, and derived search documents.
6. **Catalog** stores source identity, ownership, timestamps, security metadata, classification, lifecycle, and AI access context.
7. **Classification and review** combine deterministic metadata signals, optional bounded samples, optional local-model enrichment, and analyst correction.
8. **Policy governance** evaluates deterministic YAML or active versioned bundles, caches effective definitions for a bounded interval, and records explainable decisions, change diffs, delegated approvals, activation, rollback, scoped exceptions, and renewal.
9. **Runtime policy-decision point** accepts AuthZEN-compatible single or bounded batch evaluations, applies observe/warn/enforce semantics, returns obligations, and commits an append-only decision receipt before responding. Receipt manifests digest request properties instead of copying their values.
10. **Runtime receipt assurance** claims pending receipts in workers and signs canonical manifests with configured Ed25519, AWS KMS, or Sigstore profiles outside the authorization request path. Retention cleanup is bounded and signing verification separates integrity, signature validity, and trust.
11. **AI usage and resource plane** records idempotent tenant-scoped activity and policy correlation; registers governed models, prompts, vector indexes, tools, endpoints, and AI systems; ingests metadata-only GenAI spans; discovers review-state models; and denies missing or unapproved AI resources at runtime.
12. **Relationship and lineage layer** stores indexed directed tenant-scoped graph edges, OpenLineage events, expected AI relationships, idempotent runtime observations, drift findings, bounded multi-hop traversal, path explanations, synchronous export, and asynchronous integrity-checked export jobs with governed S3, HTTPS, Google Cloud Storage, and Azure Blob sinks.
13. **Search index** stores derived catalog metadata in OpenSearch while PostgreSQL or SQLite remains authoritative.
14. **Evidence governance** keeps object bytes outside the database and records integrity, subject, retention, application legal hold, object-lock verification, disposition approval, and deletion metadata relationally.
15. **Identity plane** validates configured human OIDC providers with cached discovery and short-lived workload providers with fixed tenant and role trust; exchanges referenced subject tokens for bounded temporary AWS, Azure, or Google Cloud credentials; manages tenant-scoped SCIM users, groups, Bulk requests, and durable deprovisioning; and issues hashed, rotating service-account credentials.
16. **Governance operations** unify policy and evidence reviews, deadlines, assignment, SLA reporting, runtime decision, enforcement, telemetry, rollout and AI lineage evidence, NIST AI RMF coverage gaps, signed metadata-only evidence packages, notifications, scheduled ownership attestations, escalation stages, and remediation.
17. **Integration plane** queues allowlisted native, CloudEvents, CEF, or Splunk HEC events with dead-letter recovery and controlled replay without performing source-system mutations.
18. **Operations layer** provides Alembic migrations, configurable PostgreSQL pools, backups, readiness, Prometheus metrics, JSON logs, optional OTLP export, a transactional governance outbox, deterministic and PostgreSQL benchmark profiles including runtime authorization, comparative regression baselines, structural read-only query-plan fingerprints, and soak tooling.

## Runtime topology

```text
clients / governed MCP
          |
 identity-aware ingress
          |
API / AuthZEN PDP replicas ---- PostgreSQL
          |                   /    |       \
          |            receipts   jobs   governance
          |                |
          +----------- worker replicas ----- approved webhooks / HTTPS sinks
          |                |
     OpenSearch        connectors ---- graph export / governance package stores
          |
 S3-compatible evidence store
```

## Persistence

PostgreSQL is recommended for shared deployments, concurrent workers, runtime authorization, telemetry, rollout, and outbox dispatch. SQLite supports local development, tests, and single-worker evaluation. Alembic owns shared schema upgrades. OpenSearch is a rebuildable metadata index. Evidence, graph-export, and governance-package bytes live in configured local or S3-compatible object storage; the database stores metadata, state, receipts, enforcement events, rollout comparisons, telemetry summaries, lineage, outbox records, and digests. Receipt and outbox writes are synchronous; signature creation and integration fan-out are asynchronous.

## Trust boundaries

Source credentials remain outside catalog, receipt, enforcement, telemetry, lineage, outbox, and job tables. Synchronous tokens are request-scoped. AuthZEN properties and context influence policy in memory; receipt manifests store digests and an allowlisted replay context rather than arbitrary values. OTLP prompt, response, message, instruction, and tool content is discarded. Queued connectors and webhook integrations resolve secret references only inside workers after endpoint validation. API keys, service accounts, validated human OIDC tokens, and fixed-trust workload identities carry role and tenant context; the remote MCP preview further requires OIDC bearer authentication. Service-account verifiers are salted and clear keys are one-time responses. OIDC discovery and discovered JWKS hosts are bounded by provider configuration. SCIM uses a dedicated tenant-bound credential. Cloud exchange reads a referenced subject token and keeps returned credentials in memory only. Graph export sinks require exact destination allowlisting and workload identity; HTTPS sinks read mounted short-lived tokens only during delivery. Package and runtime receipt signing resolve external keys or identities in workers, and verification trust is independently configured. Connector plugins are trusted process code and require an explicit administrator allowlist. Production ingress must terminate TLS, restrict `/metrics`, rate-limit AuthZEN, OTLP, and MCP endpoints, manage secrets externally, and isolate connector, identity, integration, signing, and export egress.

## Availability

The Helm chart runs multiple stateless API and worker replicas, performs migrations before install or upgrade, and includes readiness probes, autoscaling, a disruption budget, and a network policy. Authorization capacity scales with API replicas until PostgreSQL commit, pool, lock, or I/O limits dominate. Receipt signing scales through atomic worker claims and should be qualified independently from API latency. PostgreSQL, OpenSearch, object storage, ingress, secret management, and telemetry collectors should be independently resilient. See [Scaling](SCALING.md).
