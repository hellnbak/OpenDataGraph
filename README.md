# OpenDataGraph

OpenDataGraph is a source-available data intelligence and AI policy platform. It catalogs enterprise data, explains sensitivity and lifecycle findings, evaluates AI data-use policy, records observed AI activity, and exposes governed context through REST APIs, an operational console, and an MCP server.

> Release: **v1.9.0 Production Enforcement and Fleet Governance Preview**. Shared deployments require authentication, tenant-bound identities, TLS, external secret management, migrations, backups, network controls, and reviewed runtime authorization, enforcement, rollout, telemetry, MCP, connector, integration, workload-identity, evidence-package, and export configuration.

## Platform capabilities

- Enterprise metadata catalog with ownership, source identity, timestamps, exposure, encryption, lifecycle posture, and AI access context
- Metadata-first connectors for AWS S3, Google Drive, GitHub, GitLab, SharePoint / OneDrive, and PostgreSQL catalogs through a normalized cursor-aware connector SDK with versioned capability manifests, conformance checks, an allowlisted plugin registry, and tenant policy enforcement
- Deterministic classification, optional bounded enrichment, confidence and explanations, human review, and lifecycle recommendations
- Explainable AI data-use decisions, YAML rules, versioned policy bundles, simulation, diffs, delegated approvals, renewable exceptions, activation, rollback, and audit history
- AuthZEN-compatible single, bounded batch, and subject/resource/action search authorization, observe/warn/enforce deployment modes, policy obligations, idempotency, append-only decision receipts, retention, deferred Ed25519/AWS KMS/Sigstore signing, and independent verification
- Python and TypeScript policy-enforcement-point SDKs with fail-closed obligation handlers, receipt-linked enforcement outcomes, and metadata-only evidence
- Governed policy rollout with replay, shadow comparison, deterministic canary routing, pause, promotion, and per-receipt baseline-versus-candidate evidence
- AI agent registry, idempotent AI usage events, policy correlation, indexed relational graph edges, OpenLineage ingestion, path explanations, bounded multi-hop queries, synchronous export, and asynchronous large-estate export jobs
- First-class model, prompt, vector-index, tool, endpoint, and AI-system registry with expected AI relationships, idempotent runtime observations, drift detection, graph projection, and metadata-only OpenTelemetry GenAI model discovery
- Tenant-bound API keys, signed provider-specific OIDC validation with cached discovery, fixed-trust short-lived workload federation, SCIM user, group, and bulk provisioning, deprovisioning workflows, service accounts with one-time credentials and controlled rotation, ordered roles, and tenant-scoped APIs
- Durable database-backed jobs, interval or time-zone-aware cron connector and ownership schedules, maintenance windows, shared provider request budgets, governance notifications, evidence-package and export execution, retries, cancellation, stale-claim recovery, and reference-only secrets
- OpenSearch-backed metadata indexing with database fallback and tenant-scoped search
- Bounded local or S3-compatible evidence storage with SHA-256 integrity, retention dates, object-lock verification, disposition approvals, governed deletion, and legal hold
- Transactional governance outbox and signed outbound alert, decision, governance, and export events with explicit host allowlists, native, CloudEvents, Kafka REST, CEF, and Splunk HEC formats, delivery dashboards, dead-letter state, controlled replay, and worker retries
- Unified policy and evidence review queue with assignment, deadlines, overdue notifications, and tenant SLA metrics
- Catalog ownership campaigns with bounded scope, recurring schedules, durable escalation stages, selected notification destinations, immutable assignment snapshots, owner attestations, owner correction, remediation deadlines, completion tracking, and trend analytics
- Governance analytics with SLA, aging, ownership, evidence, identity, and policy-decision posture; NIST AI RMF evidence coverage and gap reporting; and integrity-checked metadata-only evidence packages with optional Ed25519, AWS KMS, or Sigstore signing and independent trust verification
- Pluggable graph export sinks for allowlisted S3, HTTPS, Google Cloud Storage, and Azure Blob destinations, using temporary workload exchange without persisted sink credentials
- Alembic migrations, SQLite and PostgreSQL backup/restore, configurable PostgreSQL connection pools, cached policy definitions, runtime authorization and receipt benchmarks, read-only query-plan capture, regression baselines, readiness checks, Prometheus metrics, JSON logs, request IDs, and optional OTLP tracing
- Operational console, REST API, local MCP server, opt-in stateless remote MCP preview, Docker Compose, HA-oriented Helm chart, and AWS backing-service templates

## New in v1.9

- AuthZEN subject, resource, and action search with opaque tenant- and request-bound pagination tokens
- Receipt-linked enforcement outcome evidence and Python and TypeScript PEP SDKs that reject unknown required obligations
- Replayable shadow and deterministic canary policy rollout with explicit promotion and complete audit context
- Metadata-only OTLP/HTTP GenAI span ingestion, review-state model discovery, and agent-to-model lineage observation; prompt and response content is discarded
- Transactional governance outbox delivery and Kafka REST-compatible CloudEvents envelopes
- Opt-in, OIDC-protected, stateless remote MCP preview with discovery, bounded tools, no server session, and configured agent identity
- NIST AI RMF evidence coverage reports that expose evidence counts and gaps without claiming certification or compliance

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

Review `.env.example` before running outside local development. Important settings include `ODG_DATABASE_URL`, database pool limits, `ODG_DEFAULT_TENANT`, `ODG_PUBLIC_BASE_URL`, runtime authorization, AuthZEN search, policy rollout, receipt lifecycle, enforcement telemetry, outbox, remote MCP, human and workload identity providers, cloud workload exchange profiles, service-account lifetimes, `ODG_SEARCH_BACKEND`, evidence and governance-package storage and signing, governance SLAs, `ODG_SECRET_FILE_ROOTS`, connector capability policy and host allowlists, graph export storage and sink allowlists, and `OTEL_EXPORTER_OTLP_ENDPOINT`.

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
- [Runtime authorization](docs/RUNTIME_AUTHORIZATION.md)
- [Production enforcement](docs/PRODUCTION_ENFORCEMENT.md)
- [Policy rollouts](docs/POLICY_ROLLOUTS.md)
- [GenAI telemetry](docs/GENAI_TELEMETRY.md)
- [Governance frameworks](docs/GOVERNANCE_FRAMEWORKS.md)
- [AI usage events](docs/AI_USAGE_EVENTS.md)
- [AI resource lineage](docs/AI_RESOURCE_LINEAGE.md)
- [Knowledge graph](docs/KNOWLEDGE_GRAPH.md)
- [Export sinks](docs/EXPORT_SINKS.md)
- [Performance qualification](docs/PERFORMANCE.md)
- [Scaling](docs/SCALING.md)
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

OpenDataGraph v1.9.0 is source-available under the [Functional Source License, Version 1.1, ALv2 Future License](LICENSE) (`FSL-1.1-ALv2`). Internal use, non-commercial education and research, and qualifying professional services are permitted. Competing commercial products and services are not permitted.

The v1.9.0 release becomes available under Apache License 2.0 on July 31, 2028. Earlier releases remain available under the terms distributed with those releases. Contact the licensor for commercial terms not granted by FSL.
