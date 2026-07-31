# Changelog

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
