# Security Policy

## Supported version

Only the latest Community Preview release receives security fixes.

## Reporting

Report suspected vulnerabilities through a monitored private security contact. Do not disclose suspected vulnerabilities in a public issue or discussion.

## Deployment warning

OpenDataGraph v1.3 adds signed OIDC validation, SCIM provisioning, schedules, evidence governance, policy lifecycle, and outbound integrations, but it remains a Community Preview. Do not expose it directly to the public internet or connect sensitive production sources without TLS, identity-aware ingress, external secret management, network restrictions, tested backups, centralized telemetry, and reviewed identity and integration configuration.

## Credentials

- Prefer short-lived workload identity and least-privilege provider roles.
- Do not place tokens in `.env`, screenshots, request examples, job payloads, logs, database rows, evidence metadata, or source history.
- Synchronous scan tokens are used only for the request.
- Queued scans store only `env:` or `file:` secret references.
- Limit `ODG_SECRET_FILE_ROOTS` to read-only mounted secret directories.
- Keep provider-specific endpoint allowlists narrow and align them with outbound network policy.
- Keep integration hosts allowlisted and resolve webhook signing secrets only in workers.
- Store `ODG_SCIM_TOKENS_JSON` and OIDC provider configuration through approved secret management.
- Rotate credentials after suspected disclosure.

## Tenant isolation

- Bind every API key to a single `tenant_id`.
- Never trust a caller-supplied tenant header or request field.
- Preserve tenant filters on object lookup, listing, idempotency, graph traversal, jobs, and evidence retrieval.
- Use separate databases for strict regulatory or cryptographic isolation requirements.

## Data handling

Connectors are metadata-first. Sampled content remains disabled unless source scope, byte limits, processing location, retention, and access are explicitly approved. OpenSearch documents exclude sampled content. Evidence uploads are bounded, retention-governed, and should contain only approved audit material. Legal hold prevents application deletion but must be aligned with object-store retention.

## Operational endpoints

`/metrics` contains aggregate process telemetry and must be network-restricted in shared deployments. Structured logs exclude bodies and credentials. OTLP collectors must use TLS and approved authentication. `/health` and `/ready` do not expose tenant counts.

## Authentication

`ODG_AUTH_DISABLED=true` is trusted local-development behavior only. Shared deployments must enable authentication, configure exact OIDC issuer, audience, JWKS, tenant, and role mappings, and keep SCIM credentials separate. API keys remain available for bounded service integrations.

## Outbound integrations

Webhook destinations require HTTPS and exact host allowlisting. Signing secrets are never persisted; workers resolve references after URL validation. Receivers must authenticate signatures, deduplicate delivery IDs, validate tenant context, and independently authorize any enforcement action.
