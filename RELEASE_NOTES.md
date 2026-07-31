# OpenDataGraph v1.2.0

OpenDataGraph v1.2 turns the design-partner foundation into an enterprise-deployment preview. Catalog, policy, connector, AI-usage, graph, job, and evidence paths now share tenant context, durable operational state, migrations, and production-oriented telemetry.

## Durable work

Connector scans can be submitted to a database-backed queue and executed by one or more workers. Jobs support bounded payloads, retries with backoff, cancellation requests, stale-claim recovery, safe errors, and result records.

Queued connectors never store provider credentials. A job stores only an `env:` or `file:` reference, and the worker resolves the credential at execution time from approved secret roots. Provider endpoints require HTTPS and provider-specific host allowlists before worker-held secrets are used. AWS S3 uses the ambient boto3 credential chain.

## Search and evidence

OpenSearch can index catalog metadata and serve tenant-scoped text search. PostgreSQL or SQLite remains authoritative. Indexing failures fall back to database search unless OpenSearch is required. Search documents exclude sampled content, prompts, responses, credentials, and authorization headers.

Authorized data owners can attach bounded evidence objects to internal subjects. Object bytes are stored locally or in S3-compatible storage; the database stores metadata, location, size, content type, SHA-256 digest, creator, tenant, and timestamps.

## Tenant isolation

API-key identities are bound to a tenant. Every data-bearing API filters by that tenant, including object lookups and idempotency checks. Local authentication-disabled mode uses `ODG_DEFAULT_TENANT`.

Provider-specific OIDC validation and SCIM remain future work. Shared deployments must use an approved identity-aware gateway if API keys are not sufficient.

## Operations

- Alembic migrations for fresh and v1.1 databases
- `/health`, `/ready`, and Prometheus `/metrics`
- Structured JSON request logs with request IDs and no body or credential logging
- Optional OTLP HTTP trace export
- SQLite online backup and PostgreSQL `pg_dump` / `pg_restore` integration
- Docker Compose API and worker services
- Helm HA deployment templates
- AWS managed PostgreSQL, OpenSearch, S3, and runtime IAM templates

## Compatibility and limitations

- Existing synchronous connector endpoints remain available.
- PostgreSQL is recommended for shared and multi-worker deployments; SQLite remains intended for local development and tests.
- The migration assigns existing v1.1 records to `ODG_DEFAULT_TENANT`; review that value before upgrading.
- The queue does not yet provide managed schedules or provider-wide rate-limit budgets.
- OIDC settings remain an integration boundary rather than application JWT validation.
- Evidence deletion and legal hold workflows remain future work.
- OpenSearch is a derived index and never the system of record.

## Upgrade

1. Stop API and worker processes.
2. Create and verify a backup.
3. Set `ODG_DATABASE_URL` and `ODG_DEFAULT_TENANT`.
4. Run `alembic upgrade head`.
5. Start the API and worker.
6. Submit `POST /api/v1/search/reindex`.
7. Verify `/ready`, worker completion, tenant isolation, and evidence access.

Downgrades are not supported. Restore the verified pre-upgrade backup if rollback is required.

## License

OpenDataGraph v1.2.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 30, 2028. Earlier releases retain the terms distributed with those releases.
