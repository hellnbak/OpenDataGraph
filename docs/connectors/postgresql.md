# PostgreSQL Catalog Connector

The PostgreSQL connector inventories relation metadata visible to an approved database identity. It does not read table rows or retrieve sampled content.

## Job configuration

Use connector type `postgresql` with:

- `account`: a non-secret logical catalog name;
- `secret_ref`: an `env:` or approved `file:` reference containing a PostgreSQL or `postgresql+psycopg` DSN;
- `schemas`: optional list of at most 100 schema names;
- `cursor`: opaque cursor returned by the previous batch;
- `max_items`: 1 through 5000.

The DSN is resolved only in the worker. It is not stored in job payloads, assets, run history, graph metadata, or errors.

## Least privilege

Grant:

- `CONNECT` on the approved database;
- `USAGE` on approved schemas;
- metadata visibility for approved relations.

Data-table `SELECT`, write privileges, superuser, `pg_read_all_data`, and destructive privileges are not required. `information_schema` returns only objects visible to the connector identity.

## Pagination and rate limits

The adapter orders by schema and relation name and returns one bounded page plus an opaque next cursor. OpenDataGraph stores and replays that cursor without interpretation. Provider request budgets apply under provider name `postgresql`.

Each scan opens a bounded metadata connection, executes one catalog query, and closes the engine. Database-side connection and statement limits remain the operator's responsibility.

## Normalization

Each record includes:

- schema and table or view name;
- table type;
- estimated rows from `pg_class`;
- relation owner;
- column count;
- `content_retrieved=false`;
- `public_access_evidence=not-evaluated`;
- `transport_encryption_evidence=not-evaluated`;
- `timestamp_provenance=catalog-scan-time`.

`public_access` remains false because database network exposure and grants are not inferred. Encryption is `Not evaluated` because transport and storage controls cannot be proven from this metadata path. `modified_at` remains unset because PostgreSQL does not provide a reliable relation-content modification timestamp here. None of these values proves that a relation is private, encrypted, or unchanged.

Errors are bounded and scrubbed of the resolved DSN. Use TLS parameters appropriate to the deployment in the secret DSN and restrict network egress to approved database hosts.
