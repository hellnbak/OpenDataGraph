# Connector SDK

The connector SDK defines:

- `AssetRecord`: normalized metadata for a catalog asset
- `ScanBatch`: records, next cursor, and completion state
- `Connector`: a provider adapter with `source`, `account`, and `scan`
- `ConnectorCapabilities`: declared content, cursor, rate-limit, timestamp, exposure, and mutation behavior
- `ConnectorManifest`: versioned permissions, egress, capabilities, SDK version, and canonical digest

## Normalized record

Every adapter provides source identity, external ID, name, path, MIME type, size, owner, timestamps, exposure, encryption context, provider metadata, and an optional bounded sample.

Connector-specific values belong in `metadata`. Credentials, authorization headers, secret references, and tenant identifiers must never be returned in a record. Ingestion supplies trusted tenant context.

## Cursor behavior

`scan(cursor, max_items)` returns one bounded `ScanBatch`. A non-empty `next_cursor` can be supplied to the next scan. `complete` indicates whether the current listing or delta has been exhausted.

Cursor values are opaque provider state. Applications and workers must not parse, normalize, truncate, or rewrite them.

## Run and job behavior

Synchronous and queued scans produce the same connector-run records. Queued scans additionally produce a durable job record containing non-secret configuration, attempts, state, safe error, and final result.

Every run records connector version, manifest digest, and the tenant capability-policy version used for execution. The registry enforces policy when work is accepted and again when a worker builds the connector.

## Registration and conformance

Built-in adapters register through `ConnectorRegistration`. External packages can expose the `opendatagraph.connectors` Python entry-point group, but only names in `ODG_CONNECTOR_PLUGIN_ALLOWLIST` load. Plugins are trusted in-process code, not sandboxed adapters.

Use `python -m connectors.conformance` to inspect installed manifest declarations. Deterministic adapter tests should also call `run_connector_conformance`. See [Connector conformance and capability policy](CONNECTOR_CONFORMANCE.md).

## Adapter requirements

- Use least-privilege metadata permissions.
- Follow provider pagination and rate-limit guidance.
- Distinguish created, modified, last-accessed, and observed timestamps.
- Document public-access interpretation.
- Keep content retrieval disabled by default.
- Bound every page and optional sample.
- Return imported and updated counts.
- Add deterministic tests without live provider calls.
