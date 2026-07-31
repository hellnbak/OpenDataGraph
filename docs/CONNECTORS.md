# Connectors

OpenDataGraph v1.9 includes metadata-first adapters for AWS S3, Google Drive, GitHub, GitLab, SharePoint / OneDrive, and PostgreSQL catalogs.

All connectors normalize source records before tenant-scoped catalog ingestion. Runs record source, account, connector version, capability manifest digest, policy version, status, imported and updated counts, safe errors, timestamps, and opaque cursor progression.

The central registry supports built-in connectors and administrator-allowlisted Python entry-point plugins. Versioned manifests declare permissions, egress, content access, cursor behavior, rate-limit behavior, timestamp provenance, public-access interpretation, and destructive actions. Deployment and tenant capability policies are enforced before execution. See [Connector conformance and capability policy](CONNECTOR_CONFORMANCE.md).

## Execution modes

Synchronous endpoints remain available for compatibility. Durable execution uses:

```text
POST /api/v1/connectors/{connector_type}/jobs
```

Queued connectors support retry, cancellation, stale-claim recovery, and result inspection. They store only non-secret configuration and a secret reference.

Managed interval schedules enqueue the same durable jobs. Tenant/provider request budgets are consumed before provider calls across direct scans, jobs, schedules, and worker replicas.

## Credential principles

- Prefer short-lived workload identity.
- Grant metadata read permissions only for approved sources.
- Never place provider credentials in job payloads, examples, logs, evidence, or run errors.
- Use `env:` or `file:` references for queued credentials, including PostgreSQL DSNs.
- Restrict secret file roots and provider egress with `ODG_GITHUB_ALLOWED_HOSTS`, `ODG_GITLAB_ALLOWED_HOSTS`, and `ODG_SHAREPOINT_ALLOWED_HOSTS`.
- Require HTTPS for provider endpoints and replayed URL cursors.

## Pagination

Provider cursors remain opaque. AWS S3 continuation tokens, Google Drive page tokens, repository page numbers, Microsoft Graph next or delta links, and PostgreSQL catalog positions are stored and replayed without interpretation.

PostgreSQL catalog scans read `information_schema` and `pg_catalog` metadata only. They do not read relation content or infer public exposure. See [PostgreSQL connector](connectors/postgresql.md), [Connector SDK](CONNECTOR_SDK.md), and the provider guides under `docs/connectors/`.
