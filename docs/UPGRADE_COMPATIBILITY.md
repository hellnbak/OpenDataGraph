# Upgrade Compatibility

OpenDataGraph supports forward-only Alembic upgrades. Back up and stop API and worker processes before schema changes. Downgrade migrations are not supported; rollback restores a verified pre-upgrade database and object-storage snapshot.

## Matrix

| From | To | Database path | API compatibility | Required review |
| --- | --- | --- | --- | --- |
| 1.2.x | 1.9.0 | Run migrations 0002 through 0008 | Existing v1.2 APIs remain | Review every intermediate release, then enforcement, rollout, telemetry, outbox, MCP, and scale budgets |
| 1.3.x | 1.9.0 | Run migrations 0003 through 0008 | Existing v1.3 APIs remain | Review v1.4 through v1.8 controls, then v1.9 production-enforcement settings |
| 1.4.x | 1.9.0 | Run migrations 0004 through 0008 | Existing v1.4 APIs remain | Review v1.5 through v1.8 lifecycle, identity, assurance, runtime, and scale controls, then v1.9 |
| 1.5.0 | 1.9.0 | Run migrations 0005 through 0008 | Existing v1.5 APIs remain | Review federation, schedules, packages, connector permissions, signing, runtime governance, and enforcement |
| 1.6.0 | 1.9.0 | Run migrations 0006 through 0008 | Existing v1.6 APIs remain | Review v1.7 assurance, v1.8 runtime governance, then v1.9 fleet controls |
| 1.7.0 | 1.9.0 | Run migrations 0007 and 0008 | Existing v1.7 APIs remain | Review runtime receipts and lineage before rollout, enforcement, telemetry, and outbox |
| 1.8.0 | 1.9.0 | Run migration 0008 | Existing v1.8 APIs remain | Search pagination, PEP SDKs, rollout, OTLP, outbox, MCP, and framework coverage |
| 1.9.0 | 1.9.0 | No schema change | Native | Configuration and qualification only |

SQLite is supported for local development, deterministic tests, and controlled single-worker evaluation. PostgreSQL is recommended for shared deployments, runtime authorization, multiple workers, schedules, larger estates, and long-running qualification.

## v1.9 schema changes

Migration `20260731_0008` adds:

- receipt replay context, replay eligibility, rollout identity, stage, and baseline-versus-candidate decisions;
- tenant-scoped enforcement events;
- policy rollout and replay summaries;
- metadata-only GenAI telemetry events;
- transactional governance outbox events and dispatch indexes.

The v1.8 migration `20260731_0007` remains part of the forward path and adds:

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
4. Review `ODG_PUBLIC_BASE_URL`, database pool bounds, runtime and rollout cache, batch and search limits, pagination secret, receipt retention, signer and trust profiles, telemetry and outbox batches, and local and remote MCP agent identity.
5. Apply `alembic upgrade head`.
6. Deploy the same v1.9 image and connector plugin set to API, migration, and worker roles.
7. Verify `/health`, `/ready`, AuthZEN metadata, and Alembic revision `20260731_0008`.
8. Test an existing authentication flow and tenant isolation for receipts, enforcement, rollouts, telemetry, outbox, AI resources, relationships, and observations.
9. Exercise AuthZEN allow, conditional, and deny outcomes, all three batch semantics, and each search endpoint with opaque pagination.
10. If signing is enabled, verify one synthetic receipt moves from pending to signed and validates against a separate trust profile.
11. Register synthetic AI resources, declare an expected relationship, ingest expected and unexpected observations, and inspect drift and graph projection.
12. Run a synthetic replay, shadow request, canary transition, and promotion; verify baseline-versus-candidate receipt evidence.
13. Apply all obligations through a test PEP, record enforcement evidence, and verify missing handlers fail closed.
14. Ingest synthetic OTLP GenAI metadata with a content attribute, verify content discard, model review state, and lineage projection.
15. Verify outbox fan-out and downstream idempotency; test the remote MCP preview only if enabled.
16. Generate a governance package containing `runtime-decisions` and `ai-lineage`, then inspect NIST AI RMF evidence gaps.
17. Capture runtime authorization benchmarks and representative PostgreSQL query plans against accepted budgets.
18. Resume normal workloads only after receipt signing, telemetry, outbox, purge, pool, and worker queues remain within thresholds.

## Rollback

Do not run an Alembic downgrade. Stop v1.9 processes, restore the complete verified pre-upgrade state, and redeploy the matching prior application and connector plugin versions. Outbox deliveries and objects written to external sinks or package storage are outside database rollback and require their own governed cleanup procedure.
