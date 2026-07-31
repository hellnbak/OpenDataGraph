# OpenDataGraph v1.6.0

OpenDataGraph v1.6 adds ecosystem and scale controls: recurring ownership campaigns, short-lived workload federation, pluggable governed export sinks, governance evidence packages, PostgreSQL catalog coverage, and larger-estate qualification tooling.

All v1.1 through v1.5 capabilities remain part of the platform. The README lists cumulative platform capabilities separately from release-specific additions.

## Ownership automation

Data owners can schedule bounded ownership campaigns on fixed intervals or five-field cron calendars with IANA time zones and maintenance windows. Each due occurrence enqueues an idempotent `ownership.campaign.launch` job that creates one campaign snapshot with a configured due period and asset limit.

Schedules can target selected enabled integration endpoints. Campaign launch, remediation-required, and completion events also support ordinary event subscriptions.

## Workload identity federation

External automation can authenticate with `X-Workload-Identity-Token`. Each configured provider fixes the tenant and maximum platform role; caller claims cannot elevate either boundary. Tokens require asymmetric signature, exact issuer and audience, expiry and issued-at claims, a valid subject, and a configured lifetime of no more than one hour.

Workload tokens are validated per request and never stored. Existing API keys, human OIDC bearer tokens, and application-managed service accounts remain available.

## Export sink adapters

Asynchronous graph exports now dispatch through a sink registry. Existing allowlisted S3 sinks remain compatible. HTTPS sinks require an exact host allowlist, reject credentials, query parameters, fragments, and redirects, and read a mounted short-lived bearer token only when the worker pushes an export.

HTTPS sinks are push-only and cannot be downloaded through OpenDataGraph. Local and S3-backed export artifacts remain integrity-checkable and retrievable.

## Governance analytics and evidence packages

The governance analytics API reports review aging and SLA compliance, ownership remediation posture, evidence and disposition activity, service-account credential posture, and policy decision counts.

Auditors can enqueue metadata-only governance evidence packages for a bounded time window and record limit. Packages can include review, ownership, evidence-integrity, policy-bundle, service-account, and graph-export metadata. They exclude evidence object bytes, policy definitions, governance details, connector secrets, prompts, and responses. Packages are stored locally or in S3-compatible storage with SHA-256 integrity.

## PostgreSQL catalog connector

The new queued and scheduled `postgresql` connector inventories visible tables and views through `information_schema` and `pg_catalog`. It records schema, table type, estimated rows, owner, and column count with opaque bounded pagination. It does not query table rows, infer public exposure, or claim a source modification timestamp.

Use a secret reference containing a PostgreSQL DSN. Grant only `CONNECT`, schema `USAGE`, and visibility required for approved catalog objects; data-table `SELECT` is not required.

## Scale qualification

`python -m app.benchmark` now includes `local`, `postgres-small`, and `postgres-large` profiles. External database profiles require PostgreSQL and an explicit fixture-write acknowledgement, use a unique synthetic tenant, and remove their fixture rows after measurement.

`python -m app.query_plans` captures read-only `EXPLAIN (FORMAT JSON)` output for catalog, graph, governance, and ownership queries. It never uses `ANALYZE`. Composite tenant/status/time indexes accompany the new migration.

These tools provide comparative evidence, not certified capacity claims.

## Upgrade

1. Stop API and worker processes.
2. Create and verify database, evidence, graph-export, and governance-package backups as applicable.
3. Review workload identity providers, campaign schedules, notification destinations, export sink allowlists, mounted identity tokens, package storage, and PostgreSQL connector permissions.
4. Run `alembic upgrade head`.
5. Start the API and workers from the same v1.6 image.
6. Verify `/health`, `/ready`, the Alembic head, tenant isolation, one scheduled ownership launch, one short-lived workload token, one enabled export sink, one evidence package, and one bounded PostgreSQL catalog scan.

Downgrades are not supported. Restore the verified pre-upgrade state if rollback is required.

## Compatibility and limitations

- Existing APIs and v1.1 through v1.5 workflows remain available.
- Ownership campaign schedules snapshot matching assets at launch; later assets require a later occurrence or campaign.
- Scheduled campaign jobs fail safely when a scope matches no assets and follow normal bounded retry behavior.
- Workload providers assign a fixed tenant and role. Dynamic tenant or role trust from workload claims is intentionally unsupported.
- HTTPS export sinks require a mounted token under an approved secret-file root and do not follow redirects.
- Governance packages contain governed metadata, not evidence object content or complete audit-source records.
- PostgreSQL public exposure and modification timestamps are not inferred; metadata explicitly records those limits.
- PostgreSQL benchmark profiles write synthetic fixtures and must run only against an approved isolated qualification database.

## License

OpenDataGraph v1.6.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 31, 2028. Earlier releases retain the terms distributed with those releases.
