# Performance Qualification

OpenDataGraph includes deterministic benchmark and bounded read-only soak tools. No certified throughput, latency, estate-size, or concurrency numbers are bundled because results depend on database sizing, indexes, network placement, data distribution, worker capacity, OpenSearch, and object storage.

## Local benchmark

Run:

```bash
python -m app.benchmark --assets 10000 --edges 25000 --iterations 50
```

The command creates an isolated in-memory SQLite schema, loads synthetic assets and graph edges, then reports p50, p95, maximum latency, and operations per second for:

- filtered catalog reads;
- bounded graph traversal.

Inputs are bounded. The result is useful for code-change comparison on the same machine; it is not a production capacity result.

## Read-only soak

Run against an approved test environment:

```bash
ODG_SOAK_API_KEY='secret-from-approved-store' \
python -m app.soak \
  --base-url https://opendatagraph.example.test \
  --duration 3600 \
  --concurrency 8 \
  --requests-per-second 25
```

Use `ODG_SOAK_SERVICE_ACCOUNT_KEY` instead when testing service-account authentication. The tool reads `/health`, `/ready`, and `/api/v1/summary`; it performs no mutation. It reports request counts, status counts, success rate, and p50, p95, and maximum latency without recording credentials or response bodies.

Bounds:

- duration: 1 second to 24 hours;
- concurrency: 1 to 64;
- target rate: greater than 0 and at most 1000 requests per second.

## Release qualification

For a production-like qualification:

1. Use PostgreSQL, the intended OpenSearch topology, representative graph and catalog distributions, and production-like object storage.
2. Run migrations and warm search indexes before measurement.
3. Exercise API and worker replicas separately and together.
4. Measure connector schedules, governance notifications, integration delivery, evidence operations, and graph exports with synthetic metadata.
5. Monitor database connections, query latency, worker queue depth, retries, memory, CPU, storage latency, and external rate limits.
6. Run a read-only soak for the intended observation period and a separate approved workload test for mutation paths.
7. Record environment, data volume, configuration, commit or release version, result, and acceptance threshold.

Do not use live provider calls, customer content, credentials, or destructive source actions in qualification fixtures.
