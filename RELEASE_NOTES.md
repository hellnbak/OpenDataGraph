# OpenDataGraph v1.1.0

OpenDataGraph v1.1 moves the project from a demonstration foundation toward design-partner testing with real enterprise metadata and observed AI activity.

## Added

### Connector SDK

The reusable SDK normalizes asset records and represents scan batches with completion state and an incremental cursor. Connector runs record source, account, status, imported and updated counts, cursor progression, timestamps, and safe error details.

Included connectors:

- AWS S3
- Google Drive
- GitHub, including configurable API URLs
- GitLab, including self-managed API URLs
- SharePoint / OneDrive through Microsoft Graph drive delta

### Classification workflow

The pipeline combines filename, path, MIME type, deterministic secret indicators, PII indicators, financial-data indicators, optional sampled content, and optional local-model output. Every result includes sensitivity, labels, business domain, an explanation, and confidence. Low-confidence results enter a review queue where an analyst can approve, reject, or correct them.

### Policy as code

YAML policies under `policies/` cover restricted data sent to public AI, unapproved agents, and training or fine-tuning requests. The API supports policy simulation without recording an enforcement audit.

### Authentication and roles

API-key authentication supports read-only, auditor, analyst, connector operator, data owner, and administrator roles. Development authentication remains disabled by default. OIDC issuer and audience settings define the integration boundary for provider-specific validation planned for a later release.

### AI usage events

AI gateways, agents, MCP clients, and internal applications can submit stable event IDs, identity, asset, model, destination, purpose, action, timestamp, and metadata. Events are idempotent, correlated with policy, and recorded with decision and risk context.

### Knowledge graph

Relational edges represent relationships such as:

```text
asset -> owned_by -> identity
asset -> belongs_to -> business-domain
agent -> accessed -> asset
repository -> contains -> asset
```

This keeps the preview simple while exposing graph-oriented data through the API.

### Operational experience

The console now surfaces connector activity, classification review volume, AI usage events, and graph-edge volume alongside catalog, lifecycle, sensitivity, agent, and policy views. The MCP server adds AI usage and relationship tools.

## Compatibility and limitations

- PostgreSQL or SQLite remains the system of record.
- OpenSearch is available in the development stack but is not the authoritative query backend.
- Connectors are metadata-first and only use sampled content when explicitly supplied.
- API-key authentication is a foundation, not a complete enterprise identity platform.
- OIDC configuration is an integration boundary; provider-specific JWT verification is not included.
- Schema migrations are not yet managed by Alembic.

## Validation

The release includes nine automated tests plus lint, Python compilation, dependency audit, secret scan, container build, and SBOM jobs in CI.
