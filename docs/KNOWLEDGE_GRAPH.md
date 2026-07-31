# Knowledge Graph

OpenDataGraph v1.3 stores tenant-scoped directed relationships and OpenLineage-derived edges in the primary relational database.

```text
asset -> owned_by -> identity
asset -> belongs_to -> business-domain
agent -> accessed -> asset
repository -> contains -> asset
dataset -> input_to -> lineage-job
lineage-job -> produces -> dataset
dataset -> transforms_into -> dataset
```

Each edge contains tenant, source type and ID, relationship, target type and ID, optional JSON metadata, and creation time. Connector and lineage ingestion avoid duplicate structural edges while AI usage may record multiple event-specific access edges.

`GET /api/v1/graph/relationships` lists recent edges and can filter by `asset_id` or `agent_key`. Every query is restricted to the authenticated tenant.

`GET /api/v1/graph/query` performs bounded inbound, outbound, or bidirectional traversal with optional relationship filters. `ODG_GRAPH_MAX_DEPTH` provides an operator cap. See [OpenLineage](OPENLINEAGE.md).

The relational design avoids a mandatory graph database while the query model evolves. OpenSearch does not replace graph-edge persistence, and bounded traversal does not replace external graph analytics for very large estates.
