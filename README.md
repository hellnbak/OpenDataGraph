# OpenDataGraph

OpenDataGraph is a source-available data intelligence and AI policy platform. It catalogs enterprise data, explains sensitivity and lifecycle findings, evaluates AI data-use policy, records observed AI activity, and exposes governed context through REST APIs, an operational console, and an MCP server.

> Release: **v1.5.0 Commercial Readiness Preview**. Shared deployments require authentication, tenant-bound identities, TLS, external secret management, migrations, backups, network controls, and reviewed outbound integrations and export sinks.

## Platform capabilities

- Enterprise metadata catalog with ownership, source identity, timestamps, exposure, encryption, lifecycle posture, and AI access context
- Metadata-first connectors for AWS S3, Google Drive, GitHub, GitLab, and SharePoint / OneDrive through a normalized cursor-aware connector SDK
- Deterministic classification, optional bounded enrichment, confidence and explanations, human review, and lifecycle recommendations
- Explainable AI data-use decisions, YAML rules, versioned policy bundles, simulation, diffs, delegated approvals, renewable exceptions, activation, rollback, and audit history
- AI agent registry, idempotent AI usage events, policy correlation, indexed relational graph edges, OpenLineage ingestion, path explanations, bounded multi-hop queries, synchronous export, and asynchronous large-estate export jobs
- Tenant-bound API keys, signed provider-specific OIDC validation with cached discovery, SCIM user, group, and bulk provisioning, deprovisioning workflows, service accounts with one-time credentials and controlled rotation, ordered roles, and tenant-scoped APIs
- Durable database-backed jobs, interval or time-zone-aware cron connector schedules, maintenance windows, shared provider request budgets, governance notifications, export execution, retries, cancellation, stale-claim recovery, and reference-only secrets
- OpenSearch-backed metadata indexing with database fallback and tenant-scoped search
- Bounded local or S3-compatible evidence storage with SHA-256 integrity, retention dates, object-lock verification, disposition approvals, governed deletion, and legal hold
- Signed outbound alert, decision, governance, and export events with explicit host allowlists, native, CloudEvents, CEF, and Splunk HEC formats, delivery dashboards, dead-letter state, controlled replay, and worker retries
- Unified policy and evidence review queue with assignment, deadlines, overdue notifications, and tenant SLA metrics
- Catalog ownership campaigns with bounded scope, immutable assignment snapshots, owner attestations, owner correction, remediation deadlines, and completion tracking
- Alembic migrations, SQLite and PostgreSQL backup/restore, readiness checks, Prometheus metrics, JSON logs, request IDs, and optional OTLP tracing
- Operational console, REST API, MCP server, Docker Compose, HA-oriented Helm chart, and AWS backing-service templates

## New in v1.5

- Tenant-scoped service accounts issue non-recoverable one-time credentials, authenticate through a dedicated header, rotate with bounded grace periods, and expose lifecycle reports without revealing hashes or salts
- Policy approvals, exception renewals, and evidence dispositions populate a unified governance queue with assignment, SLA metrics, and allowlisted overdue notifications
- Integration endpoints adapt bounded events to native OpenDataGraph JSON, CloudEvents 1.0, CEF, or Splunk HEC
- Ownership campaigns select a bounded catalog scope and track confirmation, owner correction, remediation, resolution, and campaign completion
- Asynchronous graph export jobs produce integrity-checked JSON, CSV, or GraphML in local or S3 storage and can write only to allowlisted external S3 sinks
- Deterministic benchmark and read-only soak tools, an upgrade compatibility matrix, and expanded release qualification guidance support deployment planning

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

Review `.env.example` before running outside local development. Important settings include `ODG_DATABASE_URL`, `ODG_DEFAULT_TENANT`, authentication and identity settings, service-account lifetimes, `ODG_SEARCH_BACKEND`, evidence and disposition configuration, governance SLAs, `ODG_SECRET_FILE_ROOTS`, connector and integration host allowlists, graph export storage and sink allowlists, and `OTEL_EXPORTER_OTLP_ENDPOINT`.

Keep `ODG_AUTH_DISABLED=true` only for trusted local development.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API guide](docs/api/README.md)
- [Authentication and tenancy](docs/AUTHENTICATION.md)
- [Identity provisioning](docs/IDENTITY_PROVISIONING.md)
- [Service accounts](docs/SERVICE_ACCOUNTS.md)
- [Governance operations](docs/GOVERNANCE_OPERATIONS.md)
- [Ownership campaigns](docs/OWNERSHIP_CAMPAIGNS.md)
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
- [Performance qualification](docs/PERFORMANCE.md)
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

OpenDataGraph v1.5.0 is source-available under the [Functional Source License, Version 1.1, ALv2 Future License](LICENSE) (`FSL-1.1-ALv2`). Internal use, non-commercial education and research, and qualifying professional services are permitted. Competing commercial products and services are not permitted.

The v1.5.0 release becomes available under Apache License 2.0 on July 30, 2028. Earlier releases remain available under the terms distributed with those releases. Contact the licensor for commercial terms not granted by FSL.
