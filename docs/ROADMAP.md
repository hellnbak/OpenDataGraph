# Roadmap

## v1.1 — Design-partner foundation

- Connector SDK, scan history, and incremental cursors
- AWS S3, Google Drive, GitHub, GitLab, and SharePoint / OneDrive
- Classification review workflow
- YAML policy bundles and simulation
- API-key roles and OIDC integration boundary
- AI usage events and relational knowledge graph

## v1.2 — Enterprise deployment

- Durable background workers and database-backed queue
- OpenSearch-backed metadata indexing and search
- Local and S3-compatible evidence storage
- Tenant context and stronger authorization isolation
- Alembic migrations and upgrade tooling
- Metrics, optional tracing, structured logs, backup, and restore
- Docker Compose API and worker topology
- Kubernetes Helm chart, HA defaults, and AWS backing-service templates

## v1.3 — Operational hardening

- Managed connector schedules and provider-wide rate-limit budgets
- Evidence retention, deletion, and legal hold
- Provider-specific OIDC validation and SCIM provisioning
- Policy lifecycle, approvals, exceptions, and rollback
- Alert destinations and enforcement integrations
- OpenLineage ingestion and advanced graph queries

## v1.4 — Product hardening

- Cron and time-zone schedule calendars with maintenance windows
- OIDC discovery caching, SCIM bulk operations, and identity deprovisioning workflows
- Integration dead-letter handling, replay controls, and delivery dashboards
- Policy change diffs, delegated approvers, and exception renewal workflows
- Evidence object-lock verification and disposition approvals
- Larger-estate graph indexing, path explanations, and export

## v1.5 — Commercial readiness

- Service accounts, credential rotation workflows, and identity lifecycle reporting
- Policy and evidence governance notifications, review queues, and SLA metrics
- Integration adapters for common security and governance event formats
- Catalog ownership campaigns, attestations, and remediation tracking
- Graph export jobs for very large estates and external analytics sinks
- Upgrade compatibility matrix, performance benchmarks, and long-running soak tests

Delivered in v1.5.0.

## v1.6 — Ecosystem and scale

- Additional ownership campaign scheduling and notification channels
- External identity federation for short-lived workload credentials
- Pluggable export sinks with equivalent allowlist and workload-identity controls
- Expanded governance analytics and evidence packaging
- PostgreSQL query plans and production-like benchmark profiles for larger estates
- Connector coverage selected from validated customer metadata requirements
