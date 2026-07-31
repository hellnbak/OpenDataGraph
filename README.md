# OpenDataGraph

OpenDataGraph is a source-available data intelligence and AI policy platform. It catalogs enterprise data, explains sensitivity and lifecycle findings, evaluates AI data-use policy, records observed AI activity, and exposes governed context through REST APIs, an operational console, and an MCP server.

> Release: **v1.2.0 Community Preview**. Shared deployments require authentication, tenant-bound identities, TLS, external secret management, migrations, backups, and network controls.

## v1.2 capabilities

- Durable database-backed jobs with workers, retry backoff, cancellation, stale-claim recovery, and reference-only connector secrets
- OpenSearch-backed metadata indexing with database fallback and tenant-scoped queries
- Bounded evidence objects stored locally or in an S3-compatible service, with SHA-256 integrity metadata
- Tenant-bound API keys and tenant filters across catalog, policy, connector, review, usage, graph, job, and evidence APIs
- Alembic database migrations for SQLite and PostgreSQL deployments
- Prometheus metrics, structured JSON logs, request correlation IDs, optional OTLP tracing, readiness checks, backup, and restore
- Docker Compose application and worker services, a Helm chart with HA defaults, and AWS PostgreSQL, OpenSearch, and evidence-storage templates
- Metadata-first connectors, explainable classification, review workflows, YAML policy bundles, AI usage events, and relational graph edges

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

Review `.env.example` before running outside local development. Important settings include `ODG_DATABASE_URL`, `ODG_DEFAULT_TENANT`, `ODG_AUTH_DISABLED`, `ODG_API_KEYS_JSON`, `ODG_SEARCH_BACKEND`, `ODG_OPENSEARCH_URL`, `ODG_EVIDENCE_BACKEND`, `ODG_EVIDENCE_BUCKET`, `ODG_SECRET_FILE_ROOTS`, provider-specific connector host allowlists, and `OTEL_EXPORTER_OTLP_ENDPOINT`.

Keep `ODG_AUTH_DISABLED=true` only for trusted local development.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API guide](docs/api/README.md)
- [Authentication and tenancy](docs/AUTHENTICATION.md)
- [Background jobs](docs/BACKGROUND_JOBS.md)
- [Search](docs/SEARCH.md)
- [Evidence storage](docs/EVIDENCE_STORAGE.md)
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

OpenDataGraph v1.2.0 is source-available under the [Functional Source License, Version 1.1, ALv2 Future License](LICENSE) (`FSL-1.1-ALv2`). Internal use, non-commercial education and research, and qualifying professional services are permitted. Competing commercial products and services are not permitted.

The v1.2.0 release becomes available under Apache License 2.0 on July 30, 2028. Earlier releases remain available under the terms distributed with those releases. Contact the licensor for commercial terms not granted by FSL.
