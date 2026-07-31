# Knowledge Graph

OpenDataGraph v1.2 stores tenant-scoped directed relationships in the primary relational database.

```text
asset -> owned_by -> identity
asset -> belongs_to -> business-domain
agent -> accessed -> asset
repository -> contains -> asset
```

Each edge contains tenant, source type and ID, relationship, target type and ID, optional JSON metadata, and creation time. Connector ingestion avoids duplicate structural edges while AI usage may record multiple event-specific access edges.

`GET /api/v1/graph/relationships` lists recent edges and can filter by `asset_id` or `agent_key`. Every query is restricted to the authenticated tenant.

The relational design avoids a mandatory graph database while the query model evolves. OpenSearch does not replace graph-edge persistence.
