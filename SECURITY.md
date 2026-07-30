# Security Policy

## Supported version

Only the latest Community Preview release receives security fixes.

## Reporting

Use the repository host's private vulnerability-reporting feature or a monitored private security contact. Do not disclose suspected vulnerabilities in a public issue.

## Deployment warning

OpenDataGraph v1.1 includes API-key roles but is still a preview. Do not expose it directly to the public internet or connect sensitive production sources without TLS, identity-aware ingress, external secret management, network restrictions, backups, centralized logging, and provider-specific OIDC validation.

## Credentials

- Prefer short-lived workload identity and least-privilege provider roles.
- Do not place tokens in `.env`, screenshots, sample payloads, logs, database rows, or source history.
- Connector scan tokens are used for the request and are not written to connector-run records.
- Rotate credentials after suspected disclosure.

## Data handling

Connectors are metadata-first. Sampled content should be disabled unless the organization has approved the source, size limit, retention policy, and processing boundary. Never use real customer data in the synthetic demo.

## Authentication

`ODG_AUTH_DISABLED=true` is only for trusted local development. Shared deployments must enable authentication, define role-scoped API keys, and place OIDC validation or another approved identity layer in front of the service.
