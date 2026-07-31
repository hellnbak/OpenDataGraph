# OpenDataGraph

OpenDataGraph is a source-available data intelligence and AI policy platform. It catalogs enterprise data, explains sensitivity and lifecycle findings, evaluates AI data-use policy, records observed AI activity, and exposes governed context through REST APIs, an operational console, and an MCP server.

> Release: **v1.7.0 Assurance and Extensibility Preview**. Shared deployments require authentication, tenant-bound identities, TLS, external secret management, migrations, backups, network controls, and reviewed connector, integration, workload-identity, signing, evidence-package, and export configuration.

## Platform capabilities

- Enterprise metadata catalog with ownership, source identity, timestamps, exposure, encryption, lifecycle posture, and AI access context
- Metadata-first connectors for AWS S3, Google Drive, GitHub, GitLab, SharePoint / OneDrive, and PostgreSQL catalogs through a normalized cursor-aware connector SDK with versioned capability manifests, conformance checks, an allowlisted plugin registry, and tenant policy enforcement
- Deterministic classification, optional bounded enrichment, confidence and explanations, human review, and lifecycle recommendations
- Explainable AI data-use decisions, YAML rules, versioned policy bundles, simulation, diffs, delegated approvals, renewable exceptions, activation, rollback, and audit history
- AI agent registry, idempotent AI usage events, policy correlation, indexed relational graph edges, OpenLineage ingestion, path explanations, bounded multi-hop queries, synchronous export, and asynchronous large-estate export jobs
- Tenant-bound API keys, signed provider-specific OIDC validation with cached discovery, fixed-trust short-lived workload federation, SCIM user, group, and bulk provisioning, deprovisioning workflows, service accounts with one-time credentials and controlled rotation, ordered roles, and tenant-scoped APIs
- Durable database-backed jobs, interval or time-zone-aware cron connector and ownership schedules, maintenance windows, shared provider request budgets, governance notifications, evidence-package and export execution, retries, cancellation, stale-claim recovery, and reference-only secrets
- OpenSearch-backed metadata indexing with database fallback and tenant-scoped search
- Bounded local or S3-compatible evidence storage with SHA-256 integrity, retention dates, object-lock verification, disposition approvals, governed deletion, and legal hold
- Signed outbound alert, decision, governance, and export events with explicit host allowlists, native, CloudEvents, CEF, and Splunk HEC formats, delivery dashboards, dead-letter state, controlled replay, and worker retries
- Unified policy and evidence review queue with assignment, deadlines, overdue notifications, and tenant SLA metrics
- Catalog ownership campaigns with bounded scope, recurring schedules, durable escalation stages, selected notification destinations, immutable assignment snapshots, owner attestations, owner correction, remediation deadlines, completion tracking, and trend analytics
- Governance analytics with SLA, aging, ownership, evidence, identity, and policy-decision posture plus integrity-checked metadata-only evidence packages with optional Ed25519, AWS KMS, or Sigstore signing and independent trust verification
- Pluggable graph export sinks for allowlisted S3, HTTPS, Google Cloud Storage, and Azure Blob destinations, using temporary workload exchange without persisted sink credentials
- Alembic migrations, SQLite and PostgreSQL backup/restore, PostgreSQL query-plan capture, production-like benchmark profiles, regression baselines, readiness checks, Prometheus metrics, JSON logs, request IDs, and optional OTLP tracing
- Operational console, REST API, MCP server, Docker Compose, HA-oriented Helm chart, and AWS backing-service templates

## New in v1.7

- Governance evidence packages use a signed canonical manifest, per-section digests, separate trust profiles, API verification, and an offline verifier; Ed25519, AWS KMS, and Sigstore signing are supported
- Connector SDK v2 adds versioned manifests, digest-pinned run records, deterministic conformance checks, an administrator allowlisted plugin registry, and deployment plus tenant capability policy enforcement
- AWS, Azure, and Google Cloud workload exchange profiles issue temporary credentials for S3, Google Cloud Storage, Azure Blob, and KMS operations without persisting subject or provider tokens
- Ownership escalation policies add idempotent reminder and overdue stages, durable retry state, explicit integration routing, and bounded completion, response-time, and overdue trends
- Performance baseline capture compares latency, throughput, and structural read-only PostgreSQL plan fingerprints across documented reference topologies

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

Review `.env.example` before running outside local development. Important settings include `ODG_DATABASE_URL`, `ODG_DEFAULT_TENANT`, human and workload identity providers, cloud workload exchange profiles, service-account lifetimes, `ODG_SEARCH_BACKEND`, evidence and governance-package storage and signing, governance SLAs, `ODG_SECRET_FILE_ROOTS`, connector capability policy and host allowlists, graph export storage and sink allowlists, and `OTEL_EXPORTER_OTLP_ENDPOINT`.

Keep `ODG_AUTH_DISABLED=true` only for trusted local development.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API guide](docs/api/README.md)
- [Authentication and tenancy](docs/AUTHENTICATION.md)
- [Identity provisioning](docs/IDENTITY_PROVISIONING.md)
- [Service accounts](docs/SERVICE_ACCOUNTS.md)
- [Workload identity](docs/WORKLOAD_IDENTITY.md)
- [Cloud workload exchange](docs/WORKLOAD_EXCHANGE.md)
- [Governance operations](docs/GOVERNANCE_OPERATIONS.md)
- [Ownership campaigns](docs/OWNERSHIP_CAMPAIGNS.md)
- [Governance evidence packages](docs/GOVERNANCE_EVIDENCE_PACKAGES.md)
- [Evidence signing and verification](docs/EVIDENCE_SIGNING.md)
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
- [Connector conformance and capability policy](docs/CONNECTOR_CONFORMANCE.md)
- [Classification](docs/CLASSIFICATION.md)
- [Policy as code](docs/POLICY_AS_CODE.md)
- [AI usage events](docs/AI_USAGE_EVENTS.md)
- [Knowledge graph](docs/KNOWLEDGE_GRAPH.md)
- [Export sinks](docs/EXPORT_SINKS.md)
- [Performance qualification](docs/PERFORMANCE.md)
- [Performance baselines](docs/PERFORMANCE_BASELINES.md)
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

OpenDataGraph v1.7.0 is source-available under the [Functional Source License, Version 1.1, ALv2 Future License](LICENSE) (`FSL-1.1-ALv2`). Internal use, non-commercial education and research, and qualifying professional services are permitted. Competing commercial products and services are not permitted.

The v1.7.0 release becomes available under Apache License 2.0 on July 31, 2028. Earlier releases remain available under the terms distributed with those releases. Contact the licensor for commercial terms not granted by FSL.
