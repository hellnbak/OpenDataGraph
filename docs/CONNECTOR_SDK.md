# Connector SDK

The connector SDK defines:

- `AssetRecord`: normalized metadata for a catalog asset
- `ScanBatch`: records, next cursor, and completion state
- `Connector`: a provider adapter with `source`, `account`, and `scan`

## Normalized record

Every adapter provides source identity, external ID, name, path, MIME type, size, owner, timestamps, exposure, encryption context, provider metadata, and an optional bounded sample.

Connector-specific values belong in `metadata`. Credentials, authorization headers, secret references, and tenant identifiers must never be returned in a record. Ingestion supplies trusted tenant context.

## Cursor behavior

`scan(cursor, max_items)` returns one bounded `ScanBatch`. A non-empty `next_cursor` can be supplied to the next scan. `complete` indicates whether the current listing or delta has been exhausted.

Cursor values are opaque provider state. Applications and workers must not parse, normalize, truncate, or rewrite them.

## Run and job behavior

Synchronous and queued scans produce the same connector-run records. Queued scans additionally produce a durable job record containing non-secret configuration, attempts, state, safe error, and final result.

## Adapter requirements

- Use least-privilege metadata permissions.
- Follow provider pagination and rate-limit guidance.
- Distinguish created, modified, last-accessed, and observed timestamps.
- Document public-access interpretation.
- Keep content retrieval disabled by default.
- Bound every page and optional sample.
- Return imported and updated counts.
- Add deterministic tests without live provider calls.
