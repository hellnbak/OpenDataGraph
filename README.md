# OpenDataGraph

OpenDataGraph is an open-source data intelligence and AI policy platform. It catalogs enterprise data, explains sensitivity and lifecycle findings, evaluates AI data-use policy, records observed AI activity, and exposes the resulting context to applications and MCP clients.

> Release: **v1.1.0 Community Preview**. Use synthetic or non-sensitive data until authentication, network, and secret-management controls are configured for your environment.

## v1.1 capabilities

- Connector SDK with normalized records, incremental cursors, run history, completion state, and error visibility
- Metadata-first connectors for AWS S3, Google Drive, GitHub, GitLab, and SharePoint / OneDrive
- Deterministic classification with optional sampled-content and local-model enrichment
- Confidence scores, explanations, and a human classification review queue
- YAML policy bundles with simulation and explainable allow, conditional, or deny outcomes
- API-key roles and an OIDC integration boundary
- Idempotent AI usage event ingestion with policy correlation
- Relational knowledge-graph edges connecting assets, owners, domains, repositories, and AI agents
- Operational console, REST API, MCP server, PostgreSQL support, SQLite development mode, and Docker Compose

## Quick start

Python 3.12 is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Open:

- Dashboard: `http://localhost:8080`
- API documentation: `http://localhost:8080/docs`
- Health: `http://localhost:8080/health`

The default configuration uses SQLite, synthetic demo records, and disabled authentication for local evaluation.

## Containers

```bash
docker compose up --build
```

This starts PostgreSQL, OpenSearch, and OpenDataGraph. PostgreSQL is the system of record; OpenSearch is included as an integration service for future indexed search.

## Configuration

Copy `.env.example` to `.env` and review every value.

Important settings:

- `ODG_DATABASE_URL`
- `ODG_CLASSIFICATION_MODE`
- `ODG_CLASSIFICATION_REVIEW_THRESHOLD`
- `ODG_AUTH_DISABLED`
- `ODG_API_KEYS_JSON`
- `ODG_OIDC_ISSUER`
- `ODG_OIDC_AUDIENCE`
- `ODG_POLICY_DIRECTORY`

Keep `ODG_AUTH_DISABLED=true` only for trusted local development.

## Connector safety

Connectors are metadata-first. Use short-lived, least-privilege credentials and provider scopes that allow only the sources being cataloged. Connector tokens are accepted for a scan and are not stored in connector-run records.

See [Connector overview](docs/CONNECTORS.md) and [Connector SDK](docs/CONNECTOR_SDK.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API guide](docs/api/README.md)
- [Classification](docs/CLASSIFICATION.md)
- [Policy as code](docs/POLICY_AS_CODE.md)
- [Authentication and roles](docs/AUTHENTICATION.md)
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
python -m compileall -q app connectors mcp_server.py
```

## License

See [LICENSE](LICENSE).
