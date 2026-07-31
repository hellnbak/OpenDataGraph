# Upgrade Compatibility

OpenDataGraph supports forward-only Alembic upgrades. Back up and stop API and worker processes before schema changes. Downgrade migrations are not supported; rollback restores a verified pre-upgrade database and object-storage snapshot.

## Matrix

| From | To | Database path | API compatibility | Required review |
| --- | --- | --- | --- | --- |
| 1.2.x | 1.6.0 | Run migrations 0002 through 0005 | Existing v1.2 APIs remain | Identity, schedules, retention, integrations, v1.4 governance, v1.5 lifecycle controls, then v1.6 federation, packages, and sinks |
| 1.3.x | 1.6.0 | Run migrations 0003 through 0005 | Existing v1.3 APIs remain | Cron, discovery, disposition, replay, v1.5 ownership and exports, then v1.6 settings |
| 1.4.x | 1.6.0 | Run migrations 0004 and 0005 | Existing v1.4 APIs remain | Service accounts, governance notifications, ownership, exports, workload identity, packages, and PostgreSQL connector configuration |
| 1.5.0 | 1.6.0 | Run migration 0005 | Existing v1.5 APIs remain | Workload providers, ownership schedules, HTTPS sinks, package storage, connector permissions, and qualification tooling |
| 1.6.0 | 1.6.0 | No schema change | Native | Configuration and qualification only |

SQLite is supported for local development, deterministic tests, and controlled single-worker evaluation. PostgreSQL is recommended for shared deployments, multiple workers, schedules, larger estates, and long-running qualification.

## v1.6 schema changes

Migration `20260731_0005` adds:

- ownership campaign schedules;
- governance evidence package records;
- source-schedule and selected-notification metadata on ownership campaigns;
- composite tenant/status/time indexes for service-account credentials, governance reviews, ownership campaigns and assignments, and graph exports.

The migration is idempotent for fresh schemas created through earlier migration behavior.

## Procedure

1. Record the current application and Alembic versions.
2. Stop API and worker processes.
3. Verify database, evidence, graph-export, and governance-package backups as applicable.
4. Review workload identity providers, ownership schedule destinations, HTTPS sink allowlists and projected token paths, package storage, and PostgreSQL connector grants.
5. Apply `alembic upgrade head`.
6. Deploy the same v1.6 image to API, migration, and worker roles.
7. Verify `/health`, `/ready`, and Alembic revision `20260731_0005`.
8. Test an existing authentication flow and one short-lived workload identity with synthetic claims.
9. Launch one scheduled synthetic ownership campaign and inspect its integration event.
10. Generate and integrity-check a bounded governance evidence package.
11. Execute a small export through every enabled sink type.
12. Run a metadata-only PostgreSQL connector scan with a least-privileged synthetic catalog.
13. Run focused tenant-isolation checks before enabling normal workloads.

## Rollback

Do not run an Alembic downgrade. Stop v1.6 processes, restore the complete verified pre-upgrade state, and redeploy the matching prior application version. Objects written to external export sinks and package storage are outside database rollback and require their own governed cleanup procedure.
