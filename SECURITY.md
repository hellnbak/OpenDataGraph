# Security Policy

## Supported version

Only the latest Ecosystem and Scale Preview release receives security fixes.

## Reporting

Report suspected vulnerabilities through a monitored private security contact. Do not disclose suspected vulnerabilities in a public issue or discussion.

## Deployment warning

OpenDataGraph v1.6 adds workload federation, ownership automation, governance packages, HTTPS export sinks, PostgreSQL cataloging, and larger-estate qualification, but it remains a preview. Do not expose it directly to the public internet or connect sensitive production sources without TLS, identity-aware ingress, external secret management, network restrictions, tested backups, centralized telemetry, and reviewed identity, retention, ownership, export, package, connector, and integration configuration.

## Credentials

- Prefer short-lived workload identity and least-privilege provider roles.
- Do not place tokens in `.env`, screenshots, request examples, job payloads, logs, database rows, evidence metadata, or source history.
- Synchronous scan tokens are used only for the request.
- Queued scans store only `env:` or `file:` secret references.
- Limit `ODG_SECRET_FILE_ROOTS` to read-only mounted secret directories.
- Keep provider-specific endpoint allowlists narrow and align them with outbound network policy.
- Keep integration hosts allowlisted and resolve webhook signing secrets only in workers.
- Restrict OIDC discovery to configured issuer hosts and explicitly approve different JWKS hosts.
- Store `ODG_SCIM_TOKENS_JSON` and OIDC provider configuration through approved secret management.
- Fix each workload identity provider to one tenant and least-privileged role, require tokens no longer than one hour, and never log `X-Workload-Identity-Token`.
- Store one-time service-account keys directly in approved secret management, assign the least-privileged role, monitor expiry and inactivity, and use bounded rotation overlap.
- Treat Splunk HEC references as authorization tokens and do not reuse webhook HMAC secrets.
- Rotate credentials after suspected disclosure.

## Tenant isolation

- Bind every API key to a single `tenant_id`.
- Never trust a caller-supplied tenant header or request field.
- Preserve tenant filters on object lookup, listing, idempotency, graph traversal and export, jobs, evidence retrieval and disposition, integration replay, service accounts, governance reviews and packages, ownership campaigns and schedules, and identity workflows.
- Use separate databases for strict regulatory or cryptographic isolation requirements.

## Data handling

Connectors are metadata-first. Sampled content remains disabled unless source scope, byte limits, processing location, retention, and access are explicitly approved. The PostgreSQL connector does not query table rows and must use least-privilege metadata visibility. OpenSearch documents exclude sampled content. Evidence uploads are bounded, retention-governed, and should contain only approved audit material. Governance packages include selected metadata only. Application legal hold and disposition approval do not replace provider Object Lock; verification must succeed before operators rely on storage enforcement.

## Operational endpoints

`/metrics` contains aggregate process telemetry and must be network-restricted in shared deployments. Structured logs exclude bodies and credentials. OTLP collectors must use TLS and approved authentication. `/health` and `/ready` do not expose tenant counts.

## Authentication

`ODG_AUTH_DISABLED=true` is trusted local-development behavior only. Shared deployments must enable authentication, configure exact human and workload OIDC issuer, audience, JWKS, tenant, and role trust, and keep SCIM credentials separate. API keys and service accounts remain available for bounded service integrations. Service-account verifiers are not recoverable credentials, but database access still requires strong protection.

## Outbound integrations

Webhook destinations require HTTPS and exact host allowlisting. Signing secrets are never persisted; workers resolve references after URL validation. Receivers must authenticate signatures, deduplicate delivery IDs, validate tenant context, and independently authorize any enforcement action.

Graph export sinks require explicit S3 bucket or HTTPS host allowlisting, contain no embedded credentials, and use workload identity. HTTPS delivery reads a mounted short-lived token at execution time and does not follow redirects. Treat exported graph metadata as sensitive governance data, apply destination encryption and retention, and manage external cleanup independently of database rollback.
