# OpenDataGraph v1.3.0

OpenDataGraph v1.3 adds the operational controls needed to run the v1.2 enterprise-deployment foundation continuously: managed ingestion schedules, shared provider budgets, validated federated identity, evidence governance, policy lifecycle, outbound integrations, and lineage-aware graph queries.

All v1.1 and v1.2 capabilities remain part of the platform. The README now separates cumulative platform capabilities from release-specific additions so earlier functionality remains visible.

## Scheduled ingestion

Connector operators can create, list, update, pause, and remove tenant-scoped interval schedules. Workers atomically claim due schedules and enqueue the existing reference-only `connector.scan` jobs.

Administrators can configure request budgets for each tenant and provider. Budgets are stored in the primary database and consumed before provider requests, so multiple schedules and workers share one limit window.

## Identity

Bearer authentication validates configured OIDC providers using signed JWTs and exact issuer, audience, expiry, tenant, subject, and role claims. Provider configuration supports approved algorithms, claim paths, and role mapping.

SCIM 2.0 endpoints provision tenant-scoped users and groups using a dedicated bearer token and tenant header. Password attributes are rejected, payloads are bounded, and SCIM credentials belong in external secret management.

## Evidence governance

New evidence receives the configured default retention period. Data owners can update retention and legal-hold state with an auditable reason. Evidence under legal hold cannot be deleted. Manual deletion removes the object and preserves deletion metadata; retention jobs delete only expired, unheld objects.

## Policy governance

Policy bundles now move through `draft`, `pending`, `approved`, `active`, and `retired`. Activation retires the previous active bundle, and rollback can reactivate an approved or retired version. Non-development approval requires a different identity from the author.

Administrators can create time-bounded, scoped exceptions that override a decision to `allow` or `conditional` and add required controls. Exceptions never create a broader `deny` bypass without an explicit scope and expiry.

## Integrations

Administrators can register allowlisted HTTPS webhook destinations in `observe` or `enforce` mode. Policy audits enqueue non-secret delivery records and worker jobs. Optional secrets are resolved only in the worker and used to create an HMAC-SHA256 signature.

`enforce` mode communicates an authoritative decision to an approved downstream enforcement point; OpenDataGraph does not perform destructive source-system actions.

## Lineage and graph

The OpenLineage endpoint ingests bounded run events idempotently and records run-to-job, input-to-job, job-to-output, and input-to-output relationships. The advanced graph endpoint supports tenant-scoped inbound, outbound, or bidirectional traversal with relationship filters and bounded depth.

## Upgrade

1. Stop API and worker processes.
2. Create and verify a database and evidence backup.
3. Review the new identity, integration, retention, schedule, and graph settings.
4. Run `alembic upgrade head`.
5. Start the API and workers.
6. Configure OIDC, SCIM, and integration secrets outside the ConfigMap.
7. Create provider budgets before enabling connector schedules.
8. Verify `/ready`, schedule execution, policy activation, evidence hold behavior, and tenant isolation.

Downgrades are not supported. Restore the verified pre-upgrade backup if rollback is required.

## Compatibility and limitations

- Existing synchronous connector and v1.2 job endpoints remain available.
- Schedules use bounded fixed intervals; cron expressions and time-zone calendars are not included.
- OIDC providers require an HTTPS JWKS URL and explicit claim mapping.
- SCIM supports users, groups, filtering, replacement, patch, and deletion; bulk operations are not included.
- Integration delivery is at least once and downstream receivers should deduplicate by delivery ID.
- Relational graph traversal is bounded and is not a replacement for an external graph analytics platform.
- PostgreSQL is recommended for shared, scheduled, and multi-worker deployments.

## License

OpenDataGraph v1.3.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 30, 2028. Earlier releases retain the terms distributed with those releases.
