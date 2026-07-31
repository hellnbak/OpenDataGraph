# Security Policy

## Supported version

Only the latest Community Preview release receives security fixes.

## Reporting

Report suspected vulnerabilities through a monitored private security contact. Do not disclose suspected vulnerabilities in a public issue or discussion.

## Deployment warning

OpenDataGraph v1.2 adds tenant-bound API keys, durable workers, evidence storage, migrations, and observability, but it remains a Community Preview. Do not expose it directly to the public internet or connect sensitive production sources without TLS, identity-aware ingress, external secret management, network restrictions, tested backups, centralized telemetry, and an approved identity validation layer.

## Credentials

- Prefer short-lived workload identity and least-privilege provider roles.
- Do not place tokens in `.env`, screenshots, request examples, job payloads, logs, database rows, evidence metadata, or source history.
- Synchronous scan tokens are used only for the request.
- Queued scans store only `env:` or `file:` secret references.
- Limit `ODG_SECRET_FILE_ROOTS` to read-only mounted secret directories.
- Keep provider-specific endpoint allowlists narrow and align them with outbound network policy.
- Rotate credentials after suspected disclosure.

## Tenant isolation

- Bind every API key to a single `tenant_id`.
- Never trust a caller-supplied tenant header or request field.
- Preserve tenant filters on object lookup, listing, idempotency, graph traversal, jobs, and evidence retrieval.
- Use separate databases for strict regulatory or cryptographic isolation requirements.

## Data handling

Connectors are metadata-first. Sampled content remains disabled unless source scope, byte limits, processing location, retention, and access are explicitly approved. OpenSearch documents exclude sampled content. Evidence uploads are bounded and should contain only approved audit material.

## Operational endpoints

`/metrics` contains aggregate process telemetry and must be network-restricted in shared deployments. Structured logs exclude bodies and credentials. OTLP collectors must use TLS and approved authentication. `/health` and `/ready` do not expose tenant counts.

## Authentication

`ODG_AUTH_DISABLED=true` is trusted local-development behavior only. Shared deployments must enable authentication, bind role-scoped keys to tenants, and place provider-specific OIDC validation or another approved identity layer in front of the service.
