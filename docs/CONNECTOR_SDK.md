# Connector SDK

The connector SDK defines three primitives:

- `AssetRecord`: normalized metadata for a catalog asset
- `ScanBatch`: records, next cursor, and completion state
- `Connector`: a provider adapter with `source`, `account`, and `scan`

## Normalized record

Every adapter provides source identity, external ID, name, path, MIME type, size, owner, timestamps, exposure, encryption context, provider metadata, and an optional bounded sample.

Connector-specific values belong in `metadata`. Credentials and authorization headers must never be returned in a record.

## Cursor behavior

`scan(cursor, max_items)` returns a `ScanBatch`. A non-empty `next_cursor` can be supplied to the next scan. `complete` indicates whether the provider's current listing or delta has been exhausted.

Cursor values are opaque provider state. Applications must not parse or rewrite them.

## Run history

Ingestion records:

- source and account
- running, completed, or failed status
- incoming and next cursor
- imported and updated counts
- start and finish timestamps
- bounded safe error text

## Adapter requirements

- Use provider pagination and rate-limit guidance.
- Distinguish created, modified, and last-accessed evidence.
- Keep content retrieval disabled by default.
- Bound every page and sample.
- Use short-lived, least-privilege credentials.
- Add deterministic tests without live provider calls.
