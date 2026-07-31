# OpenDataGraph

OpenDataGraph is a source-available data intelligence and AI policy platform. It catalogs enterprise data, explains sensitivity and lifecycle findings, evaluates AI data-use policy, records observed AI activity, and exposes governed context through REST APIs, an operational console, and an MCP server.

> Release: **v1.6.0 Ecosystem and Scale Preview**. Shared deployments require authentication, tenant-bound identities, TLS, external secret management, migrations, backups, network controls, and reviewed connector, integration, workload-identity, evidence-package, and export configuration.

## Platform capabilities

- Enterprise metadata catalog with ownership, source identity, timestamps, exposure, encryption, lifecycle posture, and AI access context
- Metadata-first connectors for AWS S3, Google Drive, GitHub, GitLab, SharePoint / OneDrive, and PostgreSQL catalogs through a normalized cursor-aware connector SDK
- Deterministic classification, optional bounded enrichment, confidence and explanations, human review, and lifecycle recommendations
- Explainable AI data-use decisions, YAML rules, versioned policy bundles, simulation, diffs, delegated approvals, renewable exceptions, activation, rollback, and audit history
- AI agent registry, idempotent AI usage events, policy correlation, indexed relational graph edges, OpenLineage ingestion, path explanations, bounded multi-hop queries, synchronous export, and asynchronous large-estate export jobs
- Tenant-bound API keys, signed provider-specific OIDC validation with cached discovery, fixed-trust short-lived workload federation, SCIM user, group, and bulk provisioning, deprovisioning workflows, service accounts with one-time credentials and controlled rotation, ordered roles, and tenant-scoped APIs
- Durable database-backed jobs, interval or time-zone-aware cron connector and ownership schedules, maintenance windows, shared provider request budgets, governance notifications, evidence-package and export execution, retries, cancellation, stale-claim recovery, and reference-only secrets
- OpenSearch-backed metadata indexing with database fallback and tenant-scoped search
- Bounded local or S3-compatible evidence storage with SHA-256 integrity, retention dates, object-lock verification, disposition approvals, governed deletion, and legal hold
- Signed outbound alert, decision, governance, and export events with explicit host allowlists, native, CloudEvents, CEF, and Splunk HEC formats, delivery dashboards, dead-letter state, controlled replay, and worker retries
- Unified policy and evidence review queue with assignment, deadlines, overdue notifications, and tenant SLA metrics
- Catalog ownership campaigns with bounded scope, recurring schedules, selected notification destinations, immutable assignment snapshots, owner attestations, owner correction, remediation deadlines, and completion tracking
- Governance analytics with SLA, aging, ownership, evidence, identity, and policy-decision posture plus integrity-checked metadata-only evidence packages
- Pluggable graph export sinks for allowlisted S3 and HTTPS destinations, using runtime workload identity without persisted sink credentials
- Alembic migrations, SQLite and PostgreSQL backup/restore, PostgreSQL query-plan capture, production-like benchmark profiles, readiness checks, Prometheus metrics, JSON logs, request IDs, and optional OTLP tracing
- Operational console, REST API, MCP server, Docker Compose, HA-oriented Helm chart, and AWS backing-service templates

## New in v1.6

- Recurring ownership campaign schedules use interval or time-zone-aware cron calendars, maintenance windows, bounded launch scope, idempotent worker jobs, and selected integration notification channels
- External workload identities validate signed OIDC tokens with exact issuer and audience, fixed tenant and role trust, and a maximum one-hour lifetime without storing the token
- The graph export sink registry supports allowlisted S3 and HTTPS destinations; HTTPS pushes read a mounted short-lived workload token only at execution time and never follow redirects
- Governance analytics report SLA compliance, aging, ownership remediation, evidence disposition, service-account credential, and policy-decision posture; asynchronous metadata-only evidence packages add SHA-256 integrity and local or S3 storage
- The metadata-only PostgreSQL catalog connector inventories visible tables and views with bounded opaque pagination, row estimates, ownership, and column counts without reading table content
- PostgreSQL benchmark profiles and read-only `EXPLAIN (FORMAT JSON)` capture support larger-estate qualification without claiming certified capacity

## Local start

Use Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

Run the background worker separately:

```bash
python -m app.worker
```

Open:

- Dashboard: `http://localhost:8080`
- API documentation: `http://localhost:8080/docs`
- Health: `http://localhost:8080/health`
- Readiness: `http://localhost:8080/ready`
- Metrics: `http://localhost:8080/metrics`

The default local configuration uses SQLite, the `default` tenant, synthetic demo records, database search, local evidence storage, and disabled authentication.

## Containers

```bash
export ODG_POSTGRES_PASSWORD='replace-with-a-secret'
docker compose up --build
```

The stack runs PostgreSQL, OpenSearch, a migration task, the API, and a background worker. OpenSearch indexes metadata only; PostgreSQL remains authoritative.

## Configuration

Review `.env.example` before running outside local development. Important settings include `ODG_DATABASE_URL`, `ODG_DEFAULT_TENANT`, human and workload identity providers, service-account lifetimes, `ODG_SEARCH_BACKEND`, evidence and governance-package storage, governance SLAs, `ODG_SECRET_FILE_ROOTS`, connector and integration host allowlists, graph export storage and sink allowlists, and `OTEL_EXPORTER_OTLP_ENDPOINT`.

Keep `ODG_AUTH_DISABLED=true` only for trusted local development.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API guide](docs/api/README.md)
- [Authentication and tenancy](docs/AUTHENTICATION.md)
- [Identity provisioning](docs/IDENTITY_PROVISIONING.md)
- [Service accounts](docs/SERVICE_ACCOUNTS.md)
- [Workload identity](docs/WORKLOAD_IDENTITY.md)
- [Governance operations](docs/GOVERNANCE_OPERATIONS.md)
- [Ownership campaigns](docs/OWNERSHIP_CAMPAIGNS.md)
- [Governance evidence packages](docs/GOVERNANCE_EVIDENCE_PACKAGES.md)
- [Background jobs](docs/BACKGROUND_JOBS.md)
- [Scheduling and provider budgets](docs/SCHEDULING_AND_RATE_LIMITS.md)
- [Search](docs/SEARCH.md)
- [Evidence storage](docs/EVIDENCE_STORAGE.md)
- [Policy governance](docs/POLICY_GOVERNANCE.md)
- [Integrations](docs/INTEGRATIONS.md)
- [OpenLineage](docs/OPENLINEAGE.md)
- [Observability](docs/OBSERVABILITY.md)
- [Backup and restore](docs/BACKUP_RESTORE.md)
- [Connectors](docs/CONNECTORS.md)
- [Classification](docs/CLASSIFICATION.md)
- [Policy as code](docs/POLICY_AS_CODE.md)
- [AI usage events](docs/AI_USAGE_EVENTS.md)
- [Knowledge graph](docs/KNOWLEDGE_GRAPH.md)
- [Export sinks](docs/EXPORT_SINKS.md)
- [Performance qualification](docs/PERFORMANCE.md)
- [PostgreSQL query plans](docs/QUERY_PLANS.md)
- [Upgrade compatibility](docs/UPGRADE_COMPATIBILITY.md)
- [MCP server](docs/MCP_SERVER.md)
- [Deployment](docs/deployment/README.md)
- [Development](docs/development/README.md)
- [Security](SECURITY.md)
- [Release notes](RELEASE_NOTES.md)
- [Roadmap](docs/ROADMAP.md)

## Validation

```bash
pytest -q
ruff check .
python -m compileall -q app connectors migrations mcp_server.py
docker compose config
docker compose build
```

## License

OpenDataGraph v1.6.0 is source-available under the [Functional Source License, Version 1.1, ALv2 Future License](LICENSE) (`FSL-1.1-ALv2`). Internal use, non-commercial education and research, and qualifying professional services are permitted. Competing commercial products and services are not permitted.

The v1.6.0 release becomes available under Apache License 2.0 on July 31, 2028. Earlier releases remain available under the terms distributed with those releases. Contact the licensor for commercial terms not granted by FSL.
