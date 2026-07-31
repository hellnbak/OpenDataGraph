# Performance Baselines

OpenDataGraph v1.7 turns benchmark reports and optional read-only PostgreSQL plans into portable comparative baselines. Baselines detect regressions; they are not certified capacity claims.

## Reference topologies

Documented examples are under `benchmarks/reference-topologies/` for local, small PostgreSQL, and large PostgreSQL qualification. They record bounded topology facts without connection strings, credentials, tokens, or customer identifiers.

Create benchmark and plan reports using [Performance Qualification](PERFORMANCE.md) and [PostgreSQL Query Plans](QUERY_PLANS.md). Capture a baseline:

```bash
python -m app.benchmark_baselines capture \
  --benchmark benchmark.json \
  --topology benchmarks/reference-topologies/postgres-small.json \
  --query-plans plans.json \
  --output baseline.json
```

The baseline stores application version, profile, p50, p95, maximum latency, throughput, topology metadata, and structural query-plan fingerprints. Plan fingerprints retain operator, relation, index, join, and strategy structure while excluding costs, row estimates, timing, buffers, and literal predicates.

## Regression comparison

```bash
python -m app.benchmark_baselines compare \
  --baseline baseline.json \
  --benchmark current.json \
  --query-plans current-plans.json \
  --max-latency-regression-percent 20 \
  --max-throughput-regression-percent 20 \
  --fail-on-plan-drift
```

The command exits non-zero when a configured budget fails. Latency regression is an increase from baseline; throughput regression is a decrease. Plan drift is reported by default and becomes blocking only with `--fail-on-plan-drift`.

## Qualification discipline

- Compare only equivalent topology, fixture, warm-up, concurrency, and measurement settings.
- Capture multiple runs and investigate environmental variance before accepting a new baseline.
- Review plan drift manually; a changed plan can be beneficial or harmless.
- Keep reports free of credentials and customer data, but protect them as operational metadata.
- Record why a baseline changes and retain the prior accepted result for comparison.
