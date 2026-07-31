# Changelog

## 1.7.0 - 2026-07-31

### Added

- Version 2 governance evidence packages with canonical manifests, per-section digests, Ed25519, AWS KMS, and Sigstore signing, separate verification trust profiles, API verification, and an offline verifier
- Connector SDK v2 manifests, deterministic conformance checks, a central built-in and allowlisted plugin registry, manifest-digest run provenance, and deployment plus tenant capability policy enforcement
- AWS, Azure, and Google Cloud workload exchange profiles with referenced subject tokens, bounded temporary credentials, safe test responses, and multiple projected Kubernetes token audiences
- Governed Google Cloud Storage and Azure Blob graph export adapters plus optional AWS exchange credentials for S3 and KMS operations
- Durable ownership escalation policies, idempotent endpoint delivery, stale-claim recovery, event inspection, and bounded completion, response-time, remediation, and overdue trends
- Performance baseline capture and comparison with configurable latency and throughput budgets, structural read-only query-plan fingerprints, and documented reference topologies
- Alembic upgrade from v1.6 and deterministic tests for v1.7 assurance and extensibility controls

### Changed

- Updated application, console, chart, policy, documentation, deployment defaults, and release packaging versions to `1.7.0`
- Extended governance packages, connector jobs and runs, graph export sinks, ownership campaigns and schedules, integration deliveries, worker scheduling, and deployment token projection without removing prior behavior
- Preserved all prior catalog, connector, classification, policy, AI activity, identity, evidence, integration, graph, search, job, ownership, governance, observability, and scale-qualification capabilities

## 1.6.0 - 2026-07-31

### Added

- Recurring tenant-scoped ownership campaign schedules with interval or cron cadence, time zones, maintenance windows, idempotent launch jobs, and selected notification endpoints
- Short-lived external workload identity federation with asymmetric OIDC validation and fixed provider tenant and role assignments
- Pluggable graph export sink registry with compatible allowlisted S3 delivery and allowlisted HTTPS push using mounted workload identity tokens
- Governance analytics covering review SLAs and aging, ownership remediation, evidence disposition, service-account credential posture, and policy decisions
- Asynchronous metadata-only governance evidence packages with bounded records, SHA-256 integrity, and local or S3-compatible storage
- Metadata-only PostgreSQL catalog connector with opaque pagination, least-privilege discovery, row estimates, ownership, and column counts
- PostgreSQL benchmark profiles, read-only JSON query-plan capture, and targeted larger-estate composite indexes
- Alembic upgrade from v1.5 and deterministic tests for v1.6 ecosystem and scale controls

### Changed

- Updated application, console, chart, documentation, deployment defaults, and release packaging versions to `1.6.0`
- Extended the worker scheduler and durable job registry for ownership campaign launches and governance package generation
- Expanded Docker Compose and Helm configuration for workload federation, HTTPS export identity, and governance package storage
- Preserved all prior catalog, connector, classification, policy, AI activity, identity, evidence, integration, graph, search, job, ownership, governance, and observability capabilities

## 1.5.0 - 2026-07-30

### Added

- Tenant-scoped service accounts with one-time PBKDF2-backed credentials, bounded lifetimes, rotation grace periods, explicit revocation, and lifecycle reporting
- Unified policy and evidence governance reviews with assignment, deadlines, SLA metrics, and allowlisted overdue notifications
- Native JSON, CloudEvents 1.0, CEF, and Splunk HEC integration event adapters with bounded payloads
- Catalog ownership campaigns, bounded asset assignment, attestations, owner correction, remediation deadlines, and completion tracking
- Asynchronous JSON, CSV, and GraphML graph export jobs with SHA-256 verification, local or S3 storage, and allowlisted S3 analytics sinks
- Deterministic local benchmark and bounded read-only soak tools
- Upgrade compatibility and performance qualification documentation
- Alembic upgrade from v1.4 and deterministic tests for v1.5 commercial-readiness controls

### Changed

- Updated application, console, chart, documentation, deployment defaults, and release packaging versions to `1.5.0`
- Extended summary metrics and the operational console for service accounts, governance reviews, ownership work, and graph exports
- Expanded Docker Compose, Helm, and AWS runtime configuration for graph export storage and v1.5 lifecycle controls
- Preserved all prior catalog, connector, classification, policy, AI activity, identity, evidence, integration, graph, search, job, and observability capabilities

## 1.4.0 - 2026-07-30

### Added

- Five-field cron connector schedules with IANA time zones and recurring maintenance windows
- Cached OIDC discovery metadata, bounded SCIM Bulk operations, and durable identity deprovisioning jobs
- Integration dead-letter state, tenant delivery dashboards, and explicit replay with provenance
- Structured policy bundle diffs, scoped approver delegation, and independently approved exception renewal
- S3 Object Lock verification and two-person evidence disposition workflows
- Composite tenant graph indexes, path explanations, and bounded JSON, CSV, and GraphML export
- Alembic upgrade from v1.3 and deterministic tests for all v1.4 product-hardening controls

### Changed

- Updated application, console, chart, documentation, and release packaging versions to `1.4.0`
- Extended existing schedule, SCIM, evidence, policy, integration, graph, job, and summary APIs without removing prior release capabilities
- Expanded operator guidance for identity, retention, outbound delivery recovery, graph export, and production configuration

## 1.3.0 - 2026-07-30

### Added

- Managed tenant-scoped connector schedules with worker-safe due-time claiming
- Shared provider request budgets enforced across direct scans, schedules, and workers
- Signed provider-specific OIDC validation with claim and role mapping
- SCIM 2.0 user and group provisioning with bounded payloads and dedicated authentication
- Evidence retention defaults, governance updates, legal hold, deletion metadata, and retention jobs
- Versioned policy bundles with submission, approval, activation, retirement, rollback, and scoped exceptions
- Allowlisted signed webhook destinations, delivery records, worker retries, and observe or enforce modes
- Idempotent OpenLineage ingestion and bounded advanced relational graph traversal
- Alembic upgrade from v1.2 and deterministic tests for every v1.3 control plane

### Changed

- Updated application, console, chart, policy, and documentation versions to `1.3.0`
- Reworked the README to preserve cumulative v1.1 and v1.2 platform capabilities
- Expanded authentication, connector, evidence, policy, API, graph, deployment, security, and operations documentation

## 1.2.0 - 2026-07-30

### Added

- Durable database-backed jobs, worker execution, retry backoff, cancellation, and stale-claim recovery
- Reference-only connector secrets resolved from approved environment variables or mounted files
- Provider-specific HTTPS endpoint allowlists and safe connector-error redaction
- OpenSearch metadata indexing, tenant-scoped search, reindex jobs, and database fallback
- Local and S3-compatible evidence storage with bounded uploads and SHA-256 integrity records
- Tenant context across catalog, agents, decisions, connector runs, reviews, AI usage, graph edges, jobs, and evidence
- Alembic migration and upgrade tooling
- Prometheus metrics, structured JSON logging, request IDs, optional OTLP tracing, and readiness checks
- SQLite and PostgreSQL backup and restore operations
- Migration-gated Docker Compose API and worker services
- Helm HA deployment and AWS backing-service templates
- Tests for tenant isolation, connector security, durable jobs, evidence integrity, search documents, migrations, and backups

### Changed

- Updated application, console, chart, policy, and documentation versions to `1.2.0`
- Made S3 and Google Drive implement the normalized connector batch and cursor contract
- Scoped AI usage idempotency, agent keys, asset identities, graph edges, and policy audits by tenant
- Made shared deployments migration-managed while preserving automatic schema creation for local SQLite
- Updated FastAPI, Starlette, multipart parsing, and pytest to security-fixed compatible releases
- Expanded user, API, architecture, security, connector, deployment, and development documentation
- Adopted `FSL-1.1-ALv2` source-available terms with an Apache License 2.0 future license effective July 30, 2028

## 1.1.0 - 2026-07-30

- Added the connector SDK, GitHub, GitLab, SharePoint / OneDrive, classification review queue, YAML policy simulation, API-key roles, AI usage events, relational graph edges, expanded MCP tools, and operational metrics.

## 1.0.0 RC1 - 2026-07-30

- Added the FastAPI application, operational dashboard, normalized catalog, lifecycle scoring, AI agent registry, policy decisions, enterprise synthetic demo, AWS S3 and Google Drive connectors, MCP server, PostgreSQL and SQLite support, Docker Compose, and initial tests.
