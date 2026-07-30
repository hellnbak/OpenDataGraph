# Architecture

## Design goals

OpenDataGraph is API-first, cloud-neutral, model-agnostic, explainable, and safe by default. It enriches existing security and governance controls rather than replacing storage platforms, identity providers, or enterprise enforcement points.

## Components

1. **Connector SDK** discovers source metadata and emits normalized `AssetRecord` objects in cursor-aware `ScanBatch` results.
2. **Connector ingestion** stores assets, run status, counts, errors, review candidates, and source relationships.
3. **Catalog** stores source identity, ownership, timestamps, security metadata, classification, lifecycle, and AI access context.
4. **Classification** combines deterministic metadata and sampled-content indicators with optional local-model enrichment.
5. **Review workflow** captures low-confidence classifications and records analyst approvals or corrections.
6. **Policy engine** loads YAML definitions and combines matched policy outcomes with agent, destination, and asset context.
7. **Identity boundary** maps API keys to roles and exposes OIDC configuration for a validating gateway or future provider integration.
8. **AI usage ingestion** records observed agent activity with an idempotent event ID and correlated policy result.
9. **Relationship layer** stores directed graph edges in the relational database.
10. **Interfaces** expose the same context through the dashboard, REST API, and MCP server.

## Persistence

PostgreSQL is recommended for shared environments. SQLite supports local development and tests. OpenSearch is present in the development stack for integration work but is not the v1.1 authoritative query backend.

## Trust boundaries

Source credentials remain outside the catalog. Connector tokens are accepted for a scan and are not persisted. API keys identify callers at the application boundary. A production deployment should terminate TLS at an identity-aware ingress, validate OIDC tokens, manage secrets externally, and isolate connector egress.

## Scale path

The v1.2 scope moves connector and enrichment work to background workers, adds queueing, OpenSearch-backed indexing, object evidence storage, migrations, tenant context, observability, and high-availability deployment patterns.
