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
- `ODG_SCIM_TOKENS_JSON`
- `ODG_OPENSEARCH_URL`
- `ODG_EVIDENCE_BUCKET`
- `ODG_EVIDENCE_REGION`
- `ODG_GRAPH_EXPORT_BUCKET`
- `ODG_GOVERNANCE_PACKAGE_BUCKET`
- optional `OTEL_EXPORTER_OTLP_ENDPOINT`
- optional connector and integration signing secrets referenced by workers

The migration hook runs before install and upgrade. The chart deploys multiple API and worker replicas, probes, autoscaling, a disruption budget, and a network policy. Configure TLS ingress, workload identity, secret injection, egress restrictions, and telemetry scraping for the target cluster. `workloadIdentityToken` can project a bounded Kubernetes service-account token into workers for approved HTTPS export sinks.

Provider and integration endpoints must use HTTPS and match exact host allowlists in chart configuration. OIDC discovery uses the configured issuer host; explicitly approve any different JWKS host. Add self-hosted provider domains explicitly and keep network-policy egress aligned with the same lists.

## AWS templates

`deploy/aws` provisions encrypted Multi-AZ PostgreSQL with managed master credentials, encrypted VPC OpenSearch across two availability zones, private versioned S3 evidence storage, and runtime IAM permissions.

The templates expect an existing VPC, private subnets, and application workload security groups. The runtime policy allows `evidence/`, `graph-exports/`, and `governance-packages/` prefixes in the provisioned private bucket. Review instance sizes, retention, deletion protection, encryption keys, IAM principals, logging, and cost before use.

## Evidence

Production deployments should use `ODG_EVIDENCE_BACKEND=s3`, bucket versioning, encryption, public-access blocking, lifecycle policy, and workload identity. Align `ODG_EVIDENCE_DEFAULT_RETENTION_DAYS`, application legal hold, Object Lock, disposition approval, and bucket lifecycle. The Helm default enables `ODG_EVIDENCE_DISPOSITION_APPROVAL_REQUIRED`. Local evidence storage is for evaluation or controlled single-node environments.

## Graph exports

The Helm default uses `ODG_GRAPH_EXPORT_BACKEND=s3`; provide `ODG_GRAPH_EXPORT_BUCKET` through the runtime Secret. Configure edge and byte bounds, encryption, retention, and least-privilege workload identity. Keep S3 bucket and HTTPS host sink allowlists empty unless destinations have been approved. HTTPS sinks also require a projected short-lived token with the destination audience. Local export storage requires a read-write volume shared by API and worker replicas and is not the Helm default.

## Governance packages

The Helm default uses `ODG_GOVERNANCE_PACKAGE_BACKEND=s3`; provide `ODG_GOVERNANCE_PACKAGE_BUCKET` through the runtime Secret. Use a private encrypted prefix, workload identity, versioning, retention, and tested restore procedures. Local package storage requires a shared read-write volume and is intended only for controlled single-node operation.

## Observability

Collect `/metrics` through an internal scrape path. Set `OTEL_EXPORTER_OTLP_ENDPOINT` for an approved OTLP HTTP collector. Route JSON logs to centralized storage and alert on readiness failure, job failures, connector errors, elevated policy denies, database saturation, OpenSearch health, and evidence write failures.

## Backup and recovery

Use `python -m app.operations backup` for application-coordinated recovery testing. Managed PostgreSQL and S3 deployments also require provider-native snapshots, point-in-time recovery, versioning, retention, and periodic restore tests.

## Required production controls

- TLS and identity-aware ingress
- `ODG_AUTH_DISABLED=false`
- tenant-bound, role-scoped identities
- managed PostgreSQL, OpenSearch, and S3-compatible evidence
- external secret management and workload identity
- connector egress restrictions
- integration egress restrictions and signing-secret rotation
- reviewed human OIDC claim mapping, fixed workload tenant and roles, bounded workload token lifetime, and independently rotated SCIM credentials
- service-account ownership, least-privilege roles, expiry, rotation, and stale-account review
- provider request budgets, time zones, and maintenance windows before enabling schedules
- OIDC discovery egress and SCIM deprovisioning ownership
- integration dead-letter monitoring and replay procedures
- governance review SLA ownership and overdue notification routing
- ownership campaign and schedule scope, notification routing, attestation, and remediation procedures
- evidence retention, Object Lock verification, legal hold, and disposition approval procedures
- bounded graph export limits, storage integrity, S3 and HTTPS sink allowlists, workload token audience, retention, and access review
- governance package categories, record limits, storage, integrity, retention, and access review
- least-privilege PostgreSQL connector grants and metadata-only validation
- migration and rollback plans
- tested database and evidence recovery
- centralized logs, metrics, traces, and alerts
- resource limits, probes, autoscaling, and disruption budgets
- representative benchmark, read-only query-plan, and soak qualification

See `.env.example` for the complete environment-variable list.
