# Deployment

## Docker Compose

```bash
export ODG_POSTGRES_PASSWORD='replace-with-a-secret'
docker compose up --build
```

The stack includes PostgreSQL, OpenSearch, a one-shot migration service, the API, and a durable worker. Local evidence, graph exports, and governance packages use separate named volumes shared by API and worker processes. Authentication remains disabled by default for local evaluation; enable it before shared use.

## Database upgrades

Shared deployments set `ODG_AUTO_CREATE_SCHEMA=false` and run:

```bash
alembic upgrade head
```

Back up and stop API and worker processes before upgrading an existing database. Downgrades are not supported.

## Helm

The chart is under `deploy/helm/opendatagraph`. It requires a pre-created Kubernetes Secret named by `secretName`. The Secret must contain runtime values including:

- `ODG_DATABASE_URL`
- `ODG_API_KEYS_JSON`
- `ODG_OIDC_PROVIDERS_JSON`
- `ODG_WORKLOAD_IDENTITY_PROVIDERS_JSON`
- `ODG_WORKLOAD_EXCHANGE_PROFILES_JSON`
- `ODG_GOVERNANCE_PACKAGE_SIGNING_PROFILES_JSON`
- `ODG_GOVERNANCE_PACKAGE_VERIFICATION_PROFILES_JSON`
- `ODG_AUTHZEN_PAGINATION_SECRET`
- `ODG_SCIM_TOKENS_JSON`
- `ODG_OPENSEARCH_URL`
- `ODG_EVIDENCE_BUCKET`
- `ODG_EVIDENCE_REGION`
- `ODG_GRAPH_EXPORT_BUCKET`
- `ODG_GOVERNANCE_PACKAGE_BUCKET`
- optional `OTEL_EXPORTER_OTLP_ENDPOINT`
- optional connector and integration signing secrets referenced by workers

The migration hook runs before install and upgrade. The chart deploys multiple API and worker replicas, probes, autoscaling, a disruption budget, and a network policy. Configure TLS ingress, workload identity, secret injection, egress restrictions, and telemetry scraping for the target cluster. `workloadIdentityToken` preserves the single-token v1.6 configuration. `workloadIdentityTokens` can project multiple audience-specific Kubernetes service-account tokens into API and worker replicas for cloud exchange profiles. `extraVolumes` and `extraVolumeMounts` can mount externally managed public or private signing material under `/run/secrets`.

## Runtime authorization and capacity

Set `config.publicBaseUrl` to the externally reachable HTTPS policy-decision point URL. The well-known AuthZEN document derives evaluation and search endpoints from this value. Keep `config.runtimeAuthorizationMode=enforce` for shared deployments; `warn` and `observe` are migration modes.

Review batch and search size, pagination secret, rollout cache, receipt retention, signing profile, signing batch size, retry count, purge batch size, telemetry batch size, and outbox claim and retry limits before enabling runtime traffic. Receipt signing profiles and verification trust profiles remain in the Kubernetes Secret. A configured receipt signing profile must reference key material mounted under approved secret roots or a least-privilege KMS identity available to workers.

Database pool limits apply per API or worker process. Multiply `databasePoolSize + databaseMaxOverflow` by the maximum simultaneous API and worker replica count, including rollout and autoscaling overlap, then reserve database connections for migrations, monitoring, failover, and administration. Tune against measured commit latency and query plans rather than connection count alone.

Runtime receipts and their governance outbox records are durable synchronous PostgreSQL writes. API replicas can scale horizontally until database commit, pool, lock, or I/O limits dominate. Shadow and canary requests perform baseline and candidate evaluation. Signing and outbox claims scale across workers, but KMS, Sigstore, downstream endpoint, or database quotas can become the next bottleneck. See [Scaling](../SCALING.md).

Keep remote MCP disabled unless required. When enabled, configure `config.remoteMcpDefaultAgentKey`, OIDC issuer and audience validation, TLS, body and rate limits, and ingress only for the intended clients. The gateway is stateless and does not replace identity-aware ingress. Route GenAI OTLP JSON through an authenticated collector that performs filtering, sampling, batching, and retry.

Provider and integration endpoints must use HTTPS and match exact host allowlists in chart configuration. OIDC discovery uses the configured issuer host; explicitly approve any different JWKS host. Add self-hosted provider domains explicitly and keep network-policy egress aligned with the same lists.

## AWS templates

`deploy/aws` provisions encrypted Multi-AZ PostgreSQL with managed master credentials, encrypted VPC OpenSearch across two availability zones, private versioned S3 evidence storage, and runtime IAM permissions.

The templates expect an existing VPC, private subnets, and application workload security groups. The runtime policy allows `evidence/`, `graph-exports/`, and `governance-packages/` prefixes in the provisioned private bucket. Review instance sizes, retention, deletion protection, encryption keys, IAM principals, logging, and cost before use.

## Evidence

Production deployments should use `ODG_EVIDENCE_BACKEND=s3`, bucket versioning, encryption, public-access blocking, lifecycle policy, and workload identity. Align `ODG_EVIDENCE_DEFAULT_RETENTION_DAYS`, application legal hold, Object Lock, disposition approval, and bucket lifecycle. The Helm default enables `ODG_EVIDENCE_DISPOSITION_APPROVAL_REQUIRED`. Local evidence storage is for evaluation or controlled single-node environments.

## Graph exports and cloud exchange

The Helm default uses `ODG_GRAPH_EXPORT_BACKEND=s3`; provide `ODG_GRAPH_EXPORT_BUCKET` through the runtime Secret. Configure edge and byte bounds, encryption, retention, and least-privilege workload identity. Keep S3, Google Cloud Storage, Azure Blob, and HTTPS sink allowlists empty unless destinations have been approved. Configure each cloud destination with a dedicated workload exchange profile, projected subject-token audience, and least-privilege role. HTTPS sinks continue to support a directly mounted destination token. Local export storage requires a read-write volume shared by API and worker replicas and is not the Helm default.

## Governance packages

The Helm default uses `ODG_GOVERNANCE_PACKAGE_BACKEND=s3`; provide `ODG_GOVERNANCE_PACKAGE_BUCKET` through the runtime Secret. Use a private encrypted prefix, workload identity, versioning, retention, and tested restore procedures. Configure separate signing and verification profiles, mount key material read-only or grant a dedicated KMS signing role, and enable required signing only after a synthetic package verifies independently. Sigstore profiles also require a compatible `cosign` binary in the image. Local package storage requires a shared read-write volume and is intended only for controlled single-node operation.

## Observability

Collect `/metrics` through an internal scrape path. Set `OTEL_EXPORTER_OTLP_ENDPOINT` for an approved OTLP HTTP collector. Route JSON logs to centralized storage and alert on readiness failure, job failures, connector errors, elevated policy denies, enforcement failures, rollout deltas, telemetry rejection, outbox lag, runtime authorization latency and errors, receipt signing and purge lag, lineage drift, database saturation, OpenSearch health, and evidence write failures.

## Backup and recovery

Use `python -m app.operations backup` for application-coordinated recovery testing. Managed PostgreSQL and S3 deployments also require provider-native snapshots, point-in-time recovery, versioning, retention, and periodic restore tests.

## Required production controls

- TLS and identity-aware ingress
- `ODG_AUTH_DISABLED=false`
- tenant-bound, role-scoped identities
- externally correct HTTPS `ODG_PUBLIC_BASE_URL`, enforced runtime mode, bounded batches and search, protected pagination secret, receipt retention, and signing trust
- fail-closed PEP obligation handling, enforcement-event monitoring, and measured rollout promotion
- metadata-only OTLP collector filtering, authentication, batching, rate limits, and model-review ownership
- outbox lag, retry, fan-out, destination quota, and failure monitoring
- remote MCP disabled or protected by OIDC bearer validation, fixed agent identity, TLS, network policy, and rate limits
- managed PostgreSQL, OpenSearch, and S3-compatible evidence
- external secret management and workload identity
- connector egress restrictions
- connector plugin provenance, identical API and worker installation, capability manifests, conformance, allowlist, and tenant policy
- integration egress restrictions and signing-secret rotation
- reviewed human OIDC claim mapping, fixed workload tenant and roles, bounded workload token lifetime, and independently rotated SCIM credentials
- service-account ownership, least-privilege roles, expiry, rotation, and stale-account review
- provider request budgets, time zones, and maintenance windows before enabling schedules
- OIDC discovery egress and SCIM deprovisioning ownership
- integration dead-letter monitoring and replay procedures
- governance review SLA ownership and overdue notification routing
- ownership campaign and schedule scope, notification routing, attestation, and remediation procedures
- evidence retention, Object Lock verification, legal hold, and disposition approval procedures
- bounded graph export limits, storage integrity, S3, GCS, Azure, and HTTPS sink allowlists, workload token audience, retention, and access review
- cloud exchange issuer, audience, role, subject-token mount, lifetime, egress, and failure monitoring
- governance package categories, record limits, storage, signature profile, independent trust profile, integrity, retention, and access review
- ownership escalation stages, recipient routing, endpoint idempotency, retry monitoring, and overdue trend review
- least-privilege PostgreSQL connector grants and metadata-only validation
- migration and rollback plans
- tested database and evidence recovery
- centralized logs, metrics, traces, and alerts
- database connection budgets, resource limits, probes, autoscaling, and disruption budgets
- representative runtime authorization and estate benchmarks, accepted regression baseline, read-only query-plan fingerprint, and soak qualification

See `.env.example` for the complete environment-variable list.
