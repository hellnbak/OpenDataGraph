# OpenDataGraph

**Open-source data intelligence and policy context for enterprise AI.**

OpenDataGraph inventories enterprise data, adds explainable sensitivity and lifecycle context, registers AI agents, and returns auditable decisions before an AI system uses data.

> **Release:** v1.0.0-RC1 Phase 1. This is a testable release candidate, not a production certification.

## Phase 1 capabilities

- Enterprise Demo Mode with synthetic Financial Services, Healthcare, SaaS, and diversified-enterprise profiles
- Normalized data inventory with ownership, source, classification, age, inactivity, stale score, retention recommendation, encryption, and exposure context
- Explainable deterministic classification with optional local Ollama inference
- AI Agent Registry
- Policy Decision API returning `allow`, `conditional`, or `deny`, reasons, controls, risk score, version, expiry, and an audit record
- Interactive policy playground and screenshot-ready dashboard
- Live metadata connectors for AWS S3 and Google Drive
- MCP server exposing search, asset lookup, agent listing, summary, and authorization tools
- PostgreSQL-backed Docker deployment; SQLite remains available for lightweight development
- OpenSearch service included for Phase 1 search/integration testing
- Automated tests and GitHub Actions

## Five-minute demo

```bash
git clone https://github.com/hellnbak/OpenDataGraph.git
cd OpenDataGraph
docker compose up --build
```

Open:

- Dashboard: `http://localhost:8080`
- OpenAPI: `http://localhost:8080/docs`
- Health: `http://localhost:8080/health`
- OpenSearch: `http://localhost:9200`

Demo data is synthetic. No cloud account or model is required.

## Native development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

The default local database is SQLite unless `ODG_DATABASE_URL` is set.

## Policy example

```bash
curl -X POST http://localhost:8080/api/v1/policy/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "asset_id": 1,
    "agent_key": "customer-support-copilot",
    "destination": "openai",
    "purpose": "summarization",
    "action": "send"
  }'
```

## Connectors

AWS S3 uses the standard AWS credential chain. Google Drive supports service accounts and Workspace domain-wide delegation. Both connectors are metadata-first in this release. See [`docs/connectors`](docs/connectors/).

## MCP

```bash
ODG_API_URL=http://localhost:8080 python mcp_server.py
```

See [docs/MCP_SERVER.md](docs/MCP_SERVER.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Demo guide](docs/DEMO_GUIDE.md)
- [Enterprise Demo Mode](docs/ENTERPRISE_DEMO.md)
- [Connectors](docs/CONNECTORS.md)
- [API guide](docs/api/README.md)
- [Deployment](docs/deployment/README.md)
- [Development](docs/development/README.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Release notes](RELEASE_NOTES.md)

## Safety boundaries

- No automatic deletion or archival
- No credentials stored in the catalog
- Metadata-first scanning by default
- Google Drive content is not downloaded in Phase 1
- S3 object bodies are not downloaded in Phase 1
- Lifecycle actions are recommendations only
- Policy decisions are advisory until integrated into an enforcing gateway

## License

Apache License 2.0. Review the project name, trademark posture, and long-term commercial licensing strategy before broad public promotion.
