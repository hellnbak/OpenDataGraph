# OpenLineage

OpenDataGraph v1.8 accepts bounded OpenLineage run events through:

```text
POST /api/v1/lineage/events
```

The endpoint supports `START`, `RUNNING`, `COMPLETE`, `ABORT`, `FAIL`, and `OTHER` events with run, job, input dataset, and output dataset identity. Canonical event hashes provide tenant-scoped idempotency.

Ingestion creates relational edges:

```text
lineage-run -> instance_of -> lineage-job
dataset -> input_to -> lineage-job
lineage-job -> produces -> dataset
dataset -> transforms_into -> dataset
```

Use `GET /api/v1/graph/query` for bounded traversal, `GET /api/v1/graph/paths` for path explanations, and `GET /api/v1/graph/export` for bounded JSON, CSV, or GraphML output. `ODG_GRAPH_MAX_DEPTH` and `ODG_GRAPH_MAX_EXPORT_EDGES` cap work regardless of the requested values.

Events are limited to 1 MiB and 1,000 inputs or outputs. Dataset facets remain in the retained event payload; source data is not retrieved.
