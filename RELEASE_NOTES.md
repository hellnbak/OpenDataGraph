# OpenDataGraph v1.4.0

OpenDataGraph v1.4 hardens continuous operation and governed recovery. It adds calendar-aware scheduling, identity lifecycle workflows, integration dead letters, delegated policy governance, evidence disposition approval, and explainable graph export.

All v1.1, v1.2, and v1.3 capabilities remain part of the platform. The README keeps cumulative platform capabilities separate from release-specific additions.

## Schedule calendars

Connector schedules support fixed intervals or five-field cron expressions. Cron evaluation uses an IANA time zone and stores the resulting run time in UTC. Recurring maintenance windows use local weekday and `HH:MM` boundaries; eligible runs skip those windows. Existing interval schedules continue to run unchanged.

## Identity lifecycle

OIDC providers may use a configured HTTPS JWKS URL or same-host OpenID Connect discovery. Discovery documents are bounded, issuer-checked, JWKS-host checked, and cached for a configurable period.

SCIM adds bounded Bulk requests with sequential `bulkId` reference resolution and partial error responses. Disabling or deleting a SCIM user creates a durable deprovisioning workflow. The worker deactivates the user, removes group memberships, records completion, and emits an optional integration event. SCIM credentials remain bound to one tenant and no tenant header is accepted.

## Integration recovery

Webhook deliveries that exhaust worker retries enter `dead-letter` state. The delivery dashboard summarizes tenant-wide and endpoint-level success, failure, and dead-letter counts. Administrators may replay only failed or dead-letter deliveries; the new delivery records its origin, operator, and reason.

Downstream receivers must continue deduplicating by `X-OpenDataGraph-Delivery`.

## Policy governance

Policy bundle diffs report added, removed, and field-level changed policies. Administrators can delegate bundle or exception-renewal approval to a named tenant identity, optionally limited to one bundle name and always bounded by expiry.

Active policy exceptions can request a later expiry. Approval requires an administrator or delegated approver and a different identity from the requester outside development mode.

## Evidence disposition

Evidence records track object-lock verification state. Local storage reports object lock as not applicable. S3 verification reads object retention and legal-hold state without retrieving object content.

Data owners can request evidence disposition. An independent administrator approves or rejects the request; approval queues worker execution. The worker rechecks application legal hold and S3 object-lock state before deleting. `ODG_EVIDENCE_DISPOSITION_APPROVAL_REQUIRED=true` changes retention cleanup from direct deletion to pending disposition creation.

## Graph explanations and export

Composite tenant/source, tenant/target, and tenant/relationship indexes improve larger relational graph queries. The path endpoint returns bounded paths with a human-readable explanation for each step. Tenant graph edges can be exported as bounded JSON, CSV, or GraphML.

## Upgrade

1. Stop API and worker processes.
2. Create and verify database and evidence backups.
3. Review cron, OIDC discovery, SCIM Bulk, disposition, integration replay, and graph export settings.
4. Run `alembic upgrade head`.
5. Start the API and workers.
6. Verify `/ready`, one cron schedule, OIDC discovery, SCIM deprovisioning, dead-letter replay, disposition approval, and tenant isolation.

Downgrades are not supported. Restore the verified pre-upgrade backup if rollback is required.

## Compatibility and limitations

- Existing interval schedules, direct scans, queued jobs, and v1.3 APIs remain available.
- Cron supports five numeric fields with lists, ranges, and steps; named months and weekdays are not accepted.
- OIDC discovery must use the configured issuer host. A different JWKS host must be explicitly listed in `jwks_allowed_hosts`.
- SCIM Bulk processes operations sequentially and returns per-operation status; it is not an all-or-nothing transaction.
- Identity deprovisioning removes OpenDataGraph SCIM group memberships and emits an event; approved downstream systems remain responsible for their own access revocation.
- Integration delivery is at least once. Replay creates a new delivery ID and never mutates the original dead letter.
- Object-lock verification depends on storage permissions and reports `unavailable` when state cannot be confirmed.
- Graph path and export operations remain bounded relational queries rather than an external graph analytics engine.
- PostgreSQL is recommended for shared, scheduled, and multi-worker deployments.

## License

OpenDataGraph v1.4.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 30, 2028. Earlier releases retain the terms distributed with those releases.
