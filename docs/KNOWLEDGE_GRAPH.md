# Knowledge Graph

OpenDataGraph v1.1 stores directed relationships in the primary relational database.

Examples:

```text
asset -> owned_by -> identity
asset -> belongs_to -> business-domain
agent -> accessed -> asset
repository -> contains -> asset
```

Each edge contains source type and ID, relationship, target type and ID, optional JSON metadata, and creation time.

## API

`GET /api/v1/graph/relationships` lists recent edges. Filter by `asset_id` or `agent_key`.

The relational design avoids a mandatory graph database while the query model is still evolving. A future release can introduce a specialized graph backend without changing the external edge representation.
