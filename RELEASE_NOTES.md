# OpenDataGraph v1.5.0

OpenDataGraph v1.5 adds the commercial-readiness control plane: automation identities, unified governance operations, catalog ownership campaigns, interoperable security events, scalable graph exports, and repeatable deployment qualification.

All v1.1 through v1.4 capabilities remain part of the platform. The README lists cumulative platform capabilities separately from release-specific additions.

## Service accounts

Administrators can create tenant-scoped service accounts with an existing ordered platform role. Creation returns one credential exactly once. OpenDataGraph stores a random salt and PBKDF2-HMAC-SHA256 verifier, never the clear credential.

Service-account callers authenticate with `X-Service-Account-Key`. Rotation issues a new one-time credential and gives the old credential a bounded grace period. Administrators can complete rotation early or disable the account, which revokes its active credentials. Lifecycle reports show never-used and stale accounts, credential expiry, and active rotation counts without exposing verifiers.

## Governance operations

Policy bundle submission, policy exception renewal, and evidence disposition now create tenant-scoped review tasks. Approval or rejection completes the corresponding task. Data owners can assign open work; auditors can list tasks and inspect open, overdue, due-soon, completed, and average-resolution metrics.

An administrator can enqueue a `governance.sla-notify` job. It emits `governance.review.overdue` only through subscribed allowlisted integration endpoints and records successful notification state.

## Event interoperability

Integration endpoints choose one event format:

- native OpenDataGraph JSON;
- CloudEvents 1.0 structured JSON;
- Common Event Format text;
- Splunk HTTP Event Collector JSON.

All event payloads remain bounded to 256 KiB. Native, CloudEvents, and CEF deliveries use the existing optional HMAC signature. Splunk HEC uses the worker-resolved secret as its authorization token. Delivery IDs, event types, endpoint mode, and selected format remain explicit headers.

## Ownership campaigns

Data owners can create campaigns scoped by source, business domain, sensitivity, or current owner. Launch snapshots up to the requested bounded number of tenant assets. Assignees can confirm ownership, correct the catalog owner, or require a remediation action and future deadline. Resolving the final remediation or attestation completes the campaign.

Campaign assignment records preserve original and attested ownership, notes, accountable identities, remediation state, and timestamps.

## Scalable graph exports

The existing bounded synchronous graph export remains available. v1.5 adds durable `graph.export` jobs for larger estates. Jobs serialize tenant edges to JSON, CSV, or GraphML, enforce edge and byte limits, record truncation state, SHA-256, and size, and store artifacts locally or in S3-compatible storage.

An optional external sink must be an `s3://bucket/key` URI whose bucket is explicitly configured in `ODG_GRAPH_EXPORT_ALLOWED_SINK_BUCKETS`. Credentials and query parameters are rejected; workers use workload identity. Completed exports may emit `graph.export.completed`.

## Qualification

`python -m app.benchmark` runs deterministic SQLite catalog-filter and graph-traversal measurements. `python -m app.soak` performs a bounded read-only health, readiness, and summary soak against a running environment. Neither tool claims certified capacity; use representative infrastructure and data for release qualification.

See `docs/UPGRADE_COMPATIBILITY.md` and `docs/PERFORMANCE.md`.

## Upgrade

1. Stop API and worker processes.
2. Create and verify database, evidence, and graph-export backups as applicable.
3. Review service-account lifetimes, governance SLAs, integration formats, graph-export storage, and sink allowlists.
4. Run `alembic upgrade head`.
5. Start API and workers.
6. Verify `/ready`, service-account rotation, governance task creation, an ownership campaign, each enabled integration format, graph export and download, and tenant isolation.

Downgrades are not supported. Restore the verified pre-upgrade backup if rollback is required.

## Compatibility and limitations

- Existing API keys, OIDC providers, SCIM resources, direct scans, schedules, jobs, evidence workflows, native integrations, and synchronous graph export remain available.
- Existing integration endpoints migrate to `event_format=native`.
- Service-account credentials are application-managed long-lived secrets; prefer the shortest practical lifetime and external secret distribution.
- Governance notifications require a subscribed enabled integration endpoint. Open tasks remain visible even when no notification destination exists.
- Ownership campaigns snapshot matching assets at launch; newly discovered assets require another campaign.
- External graph sinks support allowlisted S3 URIs only. They do not accept embedded credentials.
- The bundled benchmark is comparative and the soak tool is read-only; neither replaces production load testing or capacity engineering.
- PostgreSQL is recommended for shared, scheduled, multi-worker, and larger-estate deployments.

## License

OpenDataGraph v1.5.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 30, 2028. Earlier releases retain the terms distributed with those releases.
