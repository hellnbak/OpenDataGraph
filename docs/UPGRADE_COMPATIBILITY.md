# Upgrade Compatibility

OpenDataGraph supports forward-only Alembic upgrades. Back up and stop API and worker processes before schema changes. Downgrade migrations are not supported; rollback restores a verified pre-upgrade database and object-storage snapshot.

## Matrix

| From | To | Database path | API compatibility | Required review |
| --- | --- | --- | --- | --- |
| 1.2.x | 1.7.0 | Run migrations 0002 through 0006 | Existing v1.2 APIs remain | Review each intermediate release, then v1.7 signing, plugins, exchange, sinks, escalation, and baselines |
| 1.3.x | 1.7.0 | Run migrations 0003 through 0006 | Existing v1.3 APIs remain | Review v1.4 through v1.6 controls, then v1.7 trust and routing configuration |
| 1.4.x | 1.7.0 | Run migrations 0004 through 0006 | Existing v1.4 APIs remain | Review v1.5 and v1.6 lifecycle and scale controls, then v1.7 settings |
| 1.5.0 | 1.7.0 | Run migrations 0005 and 0006 | Existing v1.5 APIs remain | Review v1.6 federation, schedules, packages, connector permissions, then v1.7 controls |
| 1.6.0 | 1.7.0 | Run migration 0006 | Existing v1.6 APIs remain | Signing trust, connector capability policy, cloud exchange, sink allowlists, escalation routing, and baseline budgets |
| 1.7.0 | 1.7.0 | No schema change | Native | Configuration and qualification only |

SQLite is supported for local development, deterministic tests, and controlled single-worker evaluation. PostgreSQL is recommended for shared deployments, multiple workers, schedules, larger estates, and long-running qualification.

## v1.7 schema changes

Migration `20260731_0006` adds:

- connector capability policy records;
- connector run manifest version, digest, and policy provenance;
- evidence-package signing profile, signature type, and key identity;
- ownership escalation policies and durable stage events;
- escalation policy references on campaigns and schedules;
- integration delivery idempotency keys and endpoint-scoped uniqueness.

The migration is idempotent for fresh schemas created through earlier migration behavior.

## Procedure

1. Record the current application and Alembic versions.
2. Stop API and worker processes.
3. Verify database, evidence, graph-export, and governance-package backups as applicable.
4. Review signing and verification profiles, connector plugin packages and capability policy, cloud exchange profiles, all sink allowlists and projected token paths, escalation routing, package storage, and baseline budgets.
5. Apply `alembic upgrade head`.
6. Deploy the same v1.7 image and plugin set to API, migration, and worker roles.
7. Verify `/health`, `/ready`, and Alembic revision `20260731_0006`.
8. Test an existing authentication flow and one short-lived workload identity with synthetic claims.
9. Inspect connector manifests, run conformance, exercise one capability-policy denial, and complete a metadata-only scan.
10. Generate a bounded signed governance package and verify it with a separate trust profile and the offline verifier.
11. Test each exchange profile and execute a small export through every enabled sink type.
12. Launch one synthetic ownership campaign with a due escalation stage and confirm only one delivery is queued per endpoint.
13. Capture and compare one benchmark baseline against the intended regression budget.
14. Run focused tenant-isolation checks before enabling normal workloads.

## Rollback

Do not run an Alembic downgrade. Stop v1.7 processes, restore the complete verified pre-upgrade state, and redeploy the matching prior application and plugin versions. Objects written to external export sinks and package storage are outside database rollback and require their own governed cleanup procedure.
