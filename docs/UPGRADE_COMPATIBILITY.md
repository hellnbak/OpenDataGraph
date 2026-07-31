# Upgrade Compatibility

OpenDataGraph supports forward-only Alembic upgrades. Back up and stop API and worker processes before schema changes. Downgrade migrations are not supported; rollback restores a verified pre-upgrade database and object-storage snapshot.

## Matrix

| From | To | Database path | API compatibility | Required review |
| --- | --- | --- | --- | --- |
| 1.2.x | 1.8.0 | Run migrations 0002 through 0007 | Existing v1.2 APIs remain | Review every intermediate release, then runtime mode, receipts, signing, AI resources, lineage, pools, and scale budgets |
| 1.3.x | 1.8.0 | Run migrations 0003 through 0007 | Existing v1.3 APIs remain | Review v1.4 through v1.7 controls, then v1.8 runtime and capacity settings |
| 1.4.x | 1.8.0 | Run migrations 0004 through 0007 | Existing v1.4 APIs remain | Review v1.5 through v1.7 lifecycle, identity, assurance, and scale controls, then v1.8 |
| 1.5.0 | 1.8.0 | Run migrations 0005 through 0007 | Existing v1.5 APIs remain | Review federation, schedules, packages, connector permissions, signing, and runtime governance |
| 1.6.0 | 1.8.0 | Run migrations 0006 and 0007 | Existing v1.6 APIs remain | Review v1.7 assurance and extensibility, then v1.8 receipt and lineage controls |
| 1.7.0 | 1.8.0 | Run migration 0007 | Existing v1.7 APIs remain | Authorization mode, public PDP URL, receipt lifecycle and signing, AI resource ownership, drift, pools, and performance budgets |
| 1.8.0 | 1.8.0 | No schema change | Native | Configuration and qualification only |

SQLite is supported for local development, deterministic tests, and controlled single-worker evaluation. PostgreSQL is recommended for shared deployments, runtime authorization, multiple workers, schedules, larger estates, and long-running qualification.

## v1.8 schema changes

Migration `20260731_0007` adds:

- append-only runtime decision receipts, idempotency, manifest digests, retention, signing claims, retry state, and tenant-leading indexes;
- AI resource registry records;
- expected AI resource relationships and graph projection identity;
- idempotent AI lineage observations and drift state;
- an active policy-exception lookup index.

The migration creates portable non-partitioned SQLite and PostgreSQL tables. It does not convert receipt storage to PostgreSQL partitions. Environment-specific partitioning requires a separately qualified operator migration.

## Procedure

1. Record the current application and Alembic versions.
2. Stop API and worker processes.
3. Verify database, evidence, graph-export, and governance-package backups as applicable.
4. Review `ODG_PUBLIC_BASE_URL`, database pool bounds, runtime mode, batch limit, receipt retention, signer and trust profiles, signing and purge batch sizes, and MCP agent identity.
5. Apply `alembic upgrade head`.
6. Deploy the same v1.8 image and connector plugin set to API, migration, and worker roles.
7. Verify `/health`, `/ready`, AuthZEN metadata, and Alembic revision `20260731_0007`.
8. Test an existing authentication flow and tenant isolation for receipts, AI resources, relationships, and observations.
9. Exercise AuthZEN allow, conditional, and deny outcomes plus all three batch semantics.
10. If signing is enabled, verify one synthetic receipt moves from pending to signed and validates against a separate trust profile.
11. Register synthetic AI resources, declare an expected relationship, ingest expected and unexpected observations, and inspect drift and graph projection.
12. Generate a governance package containing `runtime-decisions` and `ai-lineage`, then verify its integrity and signature.
13. Capture runtime authorization benchmarks and representative PostgreSQL query plans against accepted budgets.
14. Resume normal workloads only after receipt signing lag, purge behavior, pool use, and worker queues remain within thresholds.

## Rollback

Do not run an Alembic downgrade. Stop v1.8 processes, restore the complete verified pre-upgrade state, and redeploy the matching prior application and connector plugin versions. Objects written to external export sinks and package storage are outside database rollback and require their own governed cleanup procedure.
