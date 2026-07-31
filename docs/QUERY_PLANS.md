# PostgreSQL Query Plans

OpenDataGraph v1.7 includes read-only PostgreSQL plan capture for representative catalog, graph, governance, and ownership queries.

Run against an approved non-production or read-only diagnostic endpoint:

```bash
python -m app.query_plans \
  --database-url 'postgresql+psycopg://user:password@database.example.test/opendatagraph' \
  --tenant example-tenant
```

The command uses `EXPLAIN (FORMAT JSON)` without `ANALYZE`. It does not execute the query plan, create fixtures, mutate tables, or print the database URL. Output contains the tenant identifier and provider plan JSON; treat it as operational metadata because relation sizes, indexes, predicates, and topology can be sensitive.

Review plans for:

- expected tenant-leading index use;
- unexpected sequential scans on large tables;
- sort and row-estimate growth;
- graph traversal fan-out;
- governance and ownership deadline filtering.

Migration `20260731_0005` adds composite indexes for service-account credential expiry, governance due work, ownership campaigns and assignments, and asynchronous graph export status. Validate index value with representative distributions before adding environment-specific indexes.

Query plans are diagnostic evidence, not capacity certification. Compare them with measured latency, buffer and I/O telemetry, connection saturation, and worker queue behavior.

`python -m app.benchmark_baselines` can derive structural fingerprints that retain operator, relation, index, join, and strategy fields while discarding costs, estimates, and timing. Fingerprint drift is review evidence, not proof of regression. See [Performance baselines](PERFORMANCE_BASELINES.md).
