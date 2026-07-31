# OpenDataGraph

OpenDataGraph is a source-available data intelligence and AI policy platform. It catalogs enterprise data, explains sensitivity and lifecycle findings, evaluates AI data-use policy, records observed AI activity, and exposes governed context through REST APIs, an operational console, and an MCP server.

> Release: **v1.3.0 Community Preview**. Shared deployments require authentication, tenant-bound identities, TLS, external secret management, migrations, backups, network controls, and reviewed outbound integrations.

## Platform capabilities

- Enterprise metadata catalog with ownership, source identity, timestamps, exposure, encryption, lifecycle posture, and AI access context
- Metadata-first connectors for AWS S3, Google Drive, GitHub, GitLab, and SharePoint / OneDrive through a normalized cursor-aware connector SDK
- Deterministic classification, optional bounded enrichment, confidence and explanations, human review, and lifecycle recommendations
- Explainable AI data-use decisions, YAML rules, versioned policy bundles, simulation, approvals, exceptions, activation, rollback, and audit history
- AI agent registry, idempotent AI usage events, policy correlation, relational graph edges, OpenLineage ingestion, and bounded multi-hop graph queries
- Tenant-bound API keys, signed provider-specific OIDC validation, SCIM user and group provisioning, ordered roles, and tenant-scoped APIs
- Durable database-backed jobs, managed connector schedules, shared provider request budgets, retries, cancellation, stale-claim recovery, and reference-only secrets
- OpenSearch-backed metadata indexing with database fallback and tenant-scoped search
- Bounded local or S3-compatible evidence storage with SHA-256 integrity, retention dates, governed deletion, and legal hold
- Signed outbound alert and decision webhooks with explicit host allowlists, observable delivery state, and worker retries
- Alembic migrations, SQLite and PostgreSQL backup/restore, readiness checks, Prometheus metrics, JSON logs, request IDs, and optional OTLP tracing
- Operational console, REST API, MCP server, Docker Compose, HA-oriented Helm chart, and AWS backing-service templates

## New in v1.3

- Managed interval schedules for all queued connectors and tenant/provider request budgets shared across workers
- OIDC signature, issuer, audience, lifetime, tenant, and role validation plus SCIM 2.0 user and group provisioning
- Evidence retention defaults, legal-hold controls, governed deletion, and retention-cleanup jobs
- Versioned policy lifecycle with submit, independent approval, activation, rollback, and bounded exceptions
- Allowlisted signed webhooks for policy alerts and downstream decision-enforcement integrations
- Idempotent OpenLineage run-event ingestion and tenant-scoped inbound, outbound, or bidirectional graph traversal

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

Review `.env.example` before running outside local development. Important settings include `ODG_DATABASE_URL`, `ODG_DEFAULT_TENANT`, `ODG_AUTH_DISABLED`, `ODG_API_KEYS_JSON`, `ODG_OIDC_PROVIDERS_JSON`, `ODG_SCIM_TOKENS_JSON`, `ODG_SEARCH_BACKEND`, evidence configuration, `ODG_SECRET_FILE_ROOTS`, connector and integration host allowlists, and `OTEL_EXPORTER_OTLP_ENDPOINT`.

Keep `ODG_AUTH_DISABLED=true` only for trusted local development.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API guide](docs/api/README.md)
- [Authentication and tenancy](docs/AUTHENTICATION.md)
- [Identity provisioning](docs/IDENTITY_PROVISIONING.md)
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

OpenDataGraph v1.3.0 is source-available under the [Functional Source License, Version 1.1, ALv2 Future License](LICENSE) (`FSL-1.1-ALv2`). Internal use, non-commercial education and research, and qualifying professional services are permitted. Competing commercial products and services are not permitted.

The v1.3.0 release becomes available under Apache License 2.0 on July 30, 2028. Earlier releases remain available under the terms distributed with those releases. Contact the licensor for commercial terms not granted by FSL.
