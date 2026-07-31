# Changelog

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
