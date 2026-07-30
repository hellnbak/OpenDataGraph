# OpenDataGraph

**The open data intelligence layer for enterprise AI.**

OpenDataGraph catalogs enterprise data, enriches it with sensitivity and business context, measures age and staleness, recommends lifecycle actions, and exposes policy decisions that AI gateways and agents can query before using data.

> OpenDataGraph is a working project name. Perform naming and trademark review before a public launch.

## What the V1 demonstrates

- A unified data inventory across representative S3, Google Drive, Microsoft 365, GitHub, and database assets
- A live AWS S3 metadata connector using the local AWS credential chain
- Explainable classification using deterministic signals with optional local Ollama inference
- First-class lifecycle intelligence: created, modified, last accessed, age, inactivity, stale score, lifecycle state, and retention recommendations
- A policy API that returns `allow`, `conditional`, or `deny` for AI use
- A polished dashboard designed for demos and screenshots
- Local-first operation with SQLite and Docker Compose

## Run the demo

### Docker

```bash
git clone https://github.com/YOUR-ORG/opendatagraph.git
cd opendatagraph
docker compose up --build
```

Open `http://localhost:8080`.

The application automatically loads realistic synthetic enterprise data. No cloud credentials or model downloads are required for the demo.

### Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Optional local AI model

OpenDataGraph works without a model by using its explainable classification engine. To add local model inference:

```bash
ollama pull qwen2.5:3b
ollama serve
```

Set `ODG_CLASSIFICATION_MODE=hybrid` or `ollama`. If Ollama is unavailable, hybrid mode safely falls back to deterministic classification.

## Scan an AWS S3 bucket

The Docker configuration mounts `~/.aws` read-only. Use a least-privilege role or profile with `s3:ListBucket` and `s3:GetObject`/`s3:GetObjectAttributes` for the intended bucket.

```bash
curl -X POST http://localhost:8080/api/v1/connectors/s3/scan \
  -H 'Content-Type: application/json' \
  -d '{"bucket":"my-bucket","prefix":"","max_objects":100}'
```

OpenDataGraph retrieves object metadata and headers; V1 does not download object bodies.

## Policy API

```bash
curl -X POST http://localhost:8080/api/v1/policy/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"asset_id":2,"destination":"openai","action":"send","actor":"demo-agent"}'
```

Example response:

```json
{
  "decision": "deny",
  "asset_id": 2,
  "destination": "openai",
  "action": "send",
  "reason": "Restricted data cannot be sent to an unapproved external AI destination.",
  "controls": ["audit-log", "identity-context", "private-model-only", "redaction-required"],
  "confidence": 0.91
}
```

## Architecture

```text
Enterprise Sources
  └─ Connector adapters
       └─ Normalized asset model
            ├─ Explainable classification
            ├─ Lifecycle and retention scoring
            ├─ AI-access context
            └─ REST policy API
                 ├─ AI gateways
                 ├─ Agents and RAG systems
                 ├─ DLP platforms
                 └─ Governance workflows
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md), and [docs/ROADMAP.md](docs/ROADMAP.md).

## API documentation

Interactive OpenAPI documentation is available at `http://localhost:8080/docs`.

## Current limitations

This is an intentionally focused V1. Google Drive, Microsoft 365, GitHub, and database records in the demo are synthetic; their production connectors are interfaces planned for the next milestones. Last-access timestamps are not uniformly available from every source and should be treated as source-dependent evidence. Retention recommendations are advisory and do not delete data.

## Security posture

- No destructive lifecycle actions
- No object-content download in the S3 connector
- Local inference supported
- Credentials are never stored by the application
- Synthetic demo data only
- Policy decisions include a reason and confidence value

See [SECURITY.md](SECURITY.md) before exposing the service outside a local development environment.

## License

Apache License 2.0. A dual-license or source-available commercial strategy can be evaluated before the first public release.

## Enterprise Demo Mode

Select **Enterprise Demo Mode** from the dashboard to generate one of four fully synthetic environments:

- Financial Services
- Healthcare
- B2B SaaS
- Fortune 500 / diversified enterprise

Each profile creates 80–600 interactive sample records. Weighted records represent an enterprise estate ranging from roughly 87,000 to 1.2 million assets, so the dashboard presents credible scale without overwhelming a laptop. Profiles include industry-specific filenames, business domains, source distributions, data ages, ownership, sensitivity, lifecycle recommendations, connector health, AI access decisions, and estimated storage savings.

The data is deterministic for a given profile, sample count, and seed. It contains no real customer, employee, patient, credential, or company information.

API example:

```bash
curl -X POST http://localhost:8080/api/v1/demo/generate \
  -H 'Content-Type: application/json' \
  -d '{"profile":"financial-services","samples":240,"seed":41}'
```
