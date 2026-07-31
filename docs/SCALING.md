# Scaling

OpenDataGraph v1.9 extends the scale-oriented runtime path with rollout comparison, enforcement evidence, telemetry ingestion, and a transactional outbox, but it does not publish universal throughput or estate-size claims. Capacity depends on PostgreSQL commit latency, pool sizing, policy and exception distributions, batch shape, rollout stage, signer latency, telemetry cardinality, outbox fan-out, worker count, storage, and deployment topology.

## Authorization hot path

A registered AI-agent and data-asset evaluation normally performs:

1. tenant-scoped agent lookup;
2. tenant-scoped asset lookup;
3. effective policy lookup from the bounded in-process cache;
4. indexed active exception lookup;
5. append-only receipt and transactional outbox inserts followed by database commit.

The request path does not call connectors, OpenSearch, object storage, webhooks, workload exchange, KMS, Sigstore, or another policy service. Deferred signing keeps external signer latency out of authorization p95. Durable receipt and outbox commit remains intentionally synchronous, so PostgreSQL write latency is part of every response. Shadow and canary rollouts also evaluate the candidate policy and should be qualified with representative bundle sizes.

Batch requests reuse repeated agent, asset, and AI resource lookups and commit their receipts together. Use AuthZEN boxcarring when a policy-enforcement point has related checks and can accept all receipts sharing one transaction boundary. The default batch limit is 100; larger batches increase transaction duration, rollback cost, response size, and lock retention.

## Database pools

Each non-SQLite process configures:

- `ODG_DATABASE_POOL_SIZE`, default 10;
- `ODG_DATABASE_MAX_OVERFLOW`, default 20;
- `ODG_DATABASE_POOL_TIMEOUT_SECONDS`, default 30;
- `ODG_DATABASE_POOL_RECYCLE_SECONDS`, default 1800.

Worst-case application connections are approximately:

```text
(API replicas + worker replicas) × (pool size + max overflow)
```

Keep that total below the database connection budget with room for migrations, administration, monitoring, failover, and autoscaling overlap. A pool timeout is backpressure, not extra database capacity. Do not solve saturation only by increasing connections; inspect transaction duration, commit I/O, indexes, and query plans first.

SQLite serializes writes and is limited to local development, tests, and controlled single-worker evaluation.

## Index strategy

Migrations `20260731_0007` and `20260731_0008` add:

- tenant and creation order for recent receipts;
- tenant, subject, and creation order;
- tenant, resource, and creation order;
- tenant, decision, and creation order;
- tenant, signing state, and creation order for receipt filtering;
- global signing status, availability, and creation order for worker claims;
- retention time and signing state for bounded purge work;
- tenant, type, and status for AI resources;
- tenant-leading source, target, and expected-state relationship indexes;
- tenant, drift state, and observation time;
- tenant, relationship, and observation time;
- tenant, active state, and expiry for policy exceptions.
- tenant and rollout order for receipt comparison;
- tenant-leading enforcement, rollout, replay, telemetry, and outbox indexes;
- a global outbox dispatch queue index for bounded worker claims.

The high-write receipt and observation tables intentionally avoid redundant single-column indexes. This reduces index maintenance, write-ahead-log volume, storage, and vacuum work while retaining indexes for documented access paths.

`python -m app.query_plans` captures read-only PostgreSQL plans for receipt subject lookup, signing claims, lineage drift, catalog, graph, governance, and ownership queries. Review real row distributions; an index being present does not guarantee it is selective or chosen.

## Policy cache consistency

Effective policy definitions are cached per process and tenant for `ODG_POLICY_CACHE_SECONDS`. Local activation invalidates the local process immediately. Other API replicas observe a new active bundle after the cache interval. Set a smaller interval when cross-replica activation propagation is more important than reducing bundle queries. Setting zero disables reuse.

The cache stores policy definitions only. Agent state, AI resource status, assets, and exceptions remain database reads so approvals, disables, and exception expiry are not hidden behind the policy cache.

## Receipt growth and signing

Estimate raw receipt volume before indexes, write-ahead logs, replicas, and backups:

```text
decisions per second × retained seconds × measured average row bytes
```

Measure row and index size in the target PostgreSQL version; do not infer them from JSON request size. Receipt manifests omit property and context values but retain identifiers, reasons, obligations, and digests.

Workers remove expired completed receipts in bounded batches. `ODG_RUNTIME_RECEIPT_PURGE_BATCH_SIZE` must exceed the number of receipts expiring per maintenance interval or backlog will grow. Pending and in-progress signing rows are not purged.

At very high sustained volume, qualify an environment-specific PostgreSQL time-partitioning or archive design before production. The bundled migration creates portable non-partitioned tables for SQLite and PostgreSQL compatibility. Converting an active table to partitioning is an operator-owned migration requiring backups, write coordination, plan review, and rollback; it is not automatic in v1.9.

Signing workers claim rows atomically. Add worker replicas when signer throughput is below receipt arrival rate, but account for KMS quotas, Sigstore availability, key policy, and cost. Keep signing batch size small enough that connector, export, governance, and integration jobs are not starved. Failed signatures retry with bounded backoff and stop after the configured maximum.

## Telemetry and outbox

OTLP JSON requests are bounded to 2 MiB and at most `ODG_GENAI_TELEMETRY_BATCH_MAX` spans. Ingestion performs tenant-scoped idempotency and discovery lookups per GenAI span, then commits the batch once. Use collector-side batching, sampling, retry, and backpressure; do not route unrestricted fleet telemetry directly to the API.

The worker claims at most `ODG_GOVERNANCE_OUTBOX_BATCH_SIZE` events per loop. Each outbox event can fan out to every matching integration endpoint and each delivery creates a background job. Qualify endpoint count, subscription distribution, downstream latency, retry storms, and dead-letter growth. Scale workers only after confirming PostgreSQL claims and destination quotas remain healthy.

## Benchmarks

`python -m app.benchmark` now reports:

- `catalog_filter`;
- `graph_traversal`;
- `runtime_authorization`, including one durable receipt commit;
- `runtime_authorization_batch_10`, including ten evaluations and one commit.

The SQLite local profile is a regression signal for the same machine, not a production estimate. PostgreSQL profiles require an isolated approved database and explicit fixture-write acknowledgement. Compare equivalent topology, fixture size, warm-up, policy set, exception count, receipt signing configuration, and database durability.

Use `python -m app.benchmark_baselines` to enforce p95 and throughput regression budgets. Capture multiple runs and inspect variance. Use a separate approved workload generator for concurrent AuthZEN traffic because the built-in benchmark is deterministic and sequential.

## Qualification matrix

At minimum, test:

- expected peak and sustained single-decision rates;
- realistic batch sizes and short-circuit semantics;
- allow, conditional, and deny distributions;
- active policy bundles at representative rule counts;
- zero, typical, and worst-case active exception counts;
- receipt signing disabled and each intended signer profile enabled;
- signer outage, retry, and recovery;
- receipt retention expiry and purge backlog;
- API and worker horizontal scaling;
- database failover, pool exhaustion, lock waits, WAL growth, replica lag, and backup impact;
- tenant skew where one tenant dominates traffic;
- lineage observation and drift ingestion rates;
- evidence-package windows containing runtime decisions and lineage.

Define acceptance budgets before testing: p50, p95, p99, error rate, timeout rate, receipt durability, signing lag, purge lag, database CPU and I/O, connections, lock waits, worker backlog, and recovery time. See [Performance qualification](PERFORMANCE.md), [Performance baselines](PERFORMANCE_BASELINES.md), and [PostgreSQL query plans](QUERY_PLANS.md).
