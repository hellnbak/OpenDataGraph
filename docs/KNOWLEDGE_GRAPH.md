# Knowledge Graph

OpenDataGraph stores directed, tenant-scoped relationships in the primary relational database.

Common relationships include:

```text
asset -> belongs_to -> business-domain
agent -> accessed -> asset
repository -> contains -> asset
lineage-run -> instance_of -> lineage-job
dataset -> input_to -> lineage-job
lineage-job -> produces -> dataset
dataset -> transforms_into -> dataset
```

Each edge contains tenant, source type and ID, relationship, target type and ID, bounded JSON metadata, and creation time. Composite indexes cover tenant/source, tenant/target, and tenant/relationship lookups for larger estates.

## Queries

- `GET /api/v1/graph/relationships` lists recent edges and filters by asset or agent.
- `GET /api/v1/graph/query` performs bounded inbound, outbound, or bidirectional traversal with optional relationship filters.
- `GET /api/v1/graph/paths` finds bounded paths between two typed nodes.

Path results preserve each underlying edge and explain how the current node reaches the next node. `ODG_GRAPH_MAX_DEPTH` caps traversal regardless of the requested depth.

## Export

`GET /api/v1/graph/export` returns tenant graph edges as:

- `format=json`
- `format=csv`
- `format=graphml`

`relationships` optionally filters edge types. `limit` is bounded by `ODG_GRAPH_MAX_EXPORT_EDGES`. CSV and GraphML responses use attachment headers. Export never includes another tenant's edges.

The relational design avoids a mandatory graph database. Bounded traversal and export are not a replacement for external graph analytics at unbounded scale. See [OpenLineage](OPENLINEAGE.md).
