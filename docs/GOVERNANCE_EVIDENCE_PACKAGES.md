# Governance Analytics and Evidence Packages

OpenDataGraph v1.6 provides tenant-scoped governance posture analytics and asynchronous metadata-only evidence packages.

## Analytics

`GET /api/v1/governance/analytics?days=30` reports:

- review creation, open and overdue counts, aging, completion, and SLA compliance;
- active ownership campaigns, pending attestations, and remediation posture;
- evidence creation, legal holds, and disposition throughput;
- active service accounts and credentials expiring within 30 days;
- policy decision counts for the selected window.

The window is bounded from 1 through 366 days. Current open and overdue posture is included alongside windowed activity.

## Evidence packages

`POST /api/v1/governance/evidence-packages` enqueues a `governance.evidence-package` job. Requests select a 1- to 366-day window, a bounded record limit, and optional categories:

- `reviews`
- `ownership`
- `evidence`
- `policies`
- `service-accounts`
- `graph-exports`

An empty category list includes every category. Packages include a versioned manifest, analytics snapshot, bounded records, record count, and truncation state.

Packages intentionally exclude evidence object bytes, filenames and storage locations, policy definitions, review detail payloads, ownership identities, connector secrets, API credentials, prompts, responses, and source-system content.

## Storage and integrity

Configure local or S3-compatible storage with:

- `ODG_GOVERNANCE_PACKAGE_BACKEND`
- `ODG_GOVERNANCE_PACKAGE_LOCAL_DIRECTORY`
- `ODG_GOVERNANCE_PACKAGE_BUCKET`
- `ODG_GOVERNANCE_PACKAGE_PREFIX`
- `ODG_GOVERNANCE_PACKAGE_ENDPOINT_URL`
- `ODG_GOVERNANCE_PACKAGE_REGION`
- `ODG_GOVERNANCE_PACKAGE_MAX_BYTES`

Workers record SHA-256 and byte size. Downloads verify the digest before returning content. Local storage is suitable only for controlled single-node evaluation; shared deployments should use private encrypted object storage with workload identity, versioning, retention, and tested restore procedures.

## APIs

- `GET /api/v1/governance/analytics`
- `POST|GET /api/v1/governance/evidence-packages`
- `GET /api/v1/governance/evidence-packages/{package_id}`
- `GET /api/v1/governance/evidence-packages/{package_id}/download`

Completed packages can emit `governance.evidence-package.completed` through subscribed integration endpoints.
