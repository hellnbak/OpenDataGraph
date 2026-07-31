# Upgrade Compatibility

OpenDataGraph supports forward-only Alembic upgrades. Back up and stop API and worker processes before schema changes. Downgrade migrations are not supported; rollback restores a verified pre-upgrade database and object-storage snapshot.

## Matrix

| From | To | Database path | API compatibility | Required review |
| --- | --- | --- | --- | --- |
| 1.2.x | 1.5.0 | Run migrations 0002 through 0004 | Existing v1.2 APIs remain | OIDC and SCIM, schedules, retention, integrations, v1.4 governance, then v1.5 identity and export settings |
| 1.3.x | 1.5.0 | Run migrations 0003 and 0004 | Existing v1.3 APIs remain | Cron and discovery, disposition and replay, then service accounts, governance SLAs, formats, ownership, and exports |
| 1.4.x | 1.5.0 | Run migration 0004 | Existing v1.4 APIs remain | Service-account lifetimes, governance notifications, event formats, ownership, graph export storage and sinks |
| 1.5.0 | 1.5.0 | No schema change | Native | Configuration and qualification only |

SQLite is supported for local development, deterministic tests, and controlled single-worker evaluation. PostgreSQL is recommended for shared deployments, multiple workers, schedules, larger estates, and long-running qualification.

## v1.5 schema changes

Migration `20260730_0004` adds:

- service accounts, credentials, and credential rotations;
- governance review tasks;
- ownership campaigns and assignments;
- asynchronous graph export records;
- `integration_endpoints.event_format`, defaulting existing rows to `native`.

The migration is idempotent for fresh schemas created through earlier migration behavior.

## Procedure

1. Record the current application and Alembic versions.
2. Stop API and worker processes.
3. Verify database and evidence backups; include local graph-export storage if it must survive rollback.
4. Apply `alembic upgrade head`.
5. Deploy the same v1.5 image to API, migration, and worker roles.
6. Verify `/health`, `/ready`, and the Alembic head.
7. Test an existing API-key or OIDC flow and one existing native integration.
8. Test service-account creation and rotation with synthetic credentials.
9. Submit and complete a synthetic governance review.
10. Launch and complete a bounded synthetic ownership campaign.
11. Execute and integrity-check a small graph export.
12. Run focused tenant-isolation checks before enabling normal workloads.

## Rollback

Do not run an Alembic downgrade. Stop v1.5 processes, restore the complete verified pre-upgrade state, and redeploy the matching prior application version. Objects written to an external export sink are outside database rollback and require their own governed cleanup procedure.
