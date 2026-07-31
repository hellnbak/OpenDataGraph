# Search

OpenDataGraph v1.9 supports database search, optional OpenSearch metadata indexing, and separate receipt-free AuthZEN authorization search.

## Configuration

```text
ODG_SEARCH_BACKEND=opensearch
ODG_OPENSEARCH_URL=https://search.example.invalid
ODG_OPENSEARCH_INDEX_PREFIX=opendatagraph
ODG_OPENSEARCH_REQUIRED=true
```

PostgreSQL or SQLite remains authoritative. OpenSearch stores derived catalog metadata and can be rebuilt.

## Indexed fields

Search documents include tenant, source, account, external ID, name, path, MIME type, owner, domain, sensitivity, classification explanation, lifecycle, exposure, encryption, AI access, and last-seen time.

Search documents exclude sampled content, prompts, responses, credentials, authorization headers, and raw provider metadata.

## Reindex

`POST /api/v1/search/reindex` creates a tenant-scoped durable job. Reindexing deletes only that tenant's derived documents before writing the current catalog state.

If OpenSearch is optional and unavailable, asset queries fall back to bounded database matching. If `ODG_OPENSEARCH_REQUIRED=true`, readiness fails and search errors are not hidden.
