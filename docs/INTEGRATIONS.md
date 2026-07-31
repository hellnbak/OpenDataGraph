# Alert and Enforcement Integrations

OpenDataGraph sends bounded policy, identity, and test events to approved HTTPS webhooks. It does not mutate source systems.

## Endpoint controls

Administrators create endpoints with an allowlisted URL, `observe` or `enforce` mode, subscribed event names, and optional worker-resolved signing secret. `ODG_INTEGRATION_ALLOWED_HOSTS` must contain every permitted destination host.

Secrets use `env:` or `file:` references and are never stored in delivery payloads. When configured, workers sign the exact request body using HMAC-SHA256 in `X-OpenDataGraph-Signature`.

## Delivery lifecycle

Each event creates an immutable delivery ID and a durable `integration.deliver` job. Receivers should deduplicate by `X-OpenDataGraph-Delivery`. Failed requests retry with bounded backoff. After the final job attempt, the delivery enters `dead-letter` state and records the last safe error and timestamp.

Original dead letters are never mutated by replay. `POST /api/v1/integrations/deliveries/{delivery_id}/replay` creates a new pending delivery with:

- the original event and endpoint;
- `replayed_from` provenance;
- operator identity;
- replay reason.

Only failed or dead-letter deliveries can be replayed, and the endpoint must still be enabled.

## Dashboard and APIs

- `POST|GET /api/v1/integrations`
- `DELETE /api/v1/integrations/{endpoint_id}`
- `POST /api/v1/integrations/{endpoint_id}/test`
- `GET /api/v1/integrations/deliveries`
- `GET /api/v1/integrations/dashboard`
- `POST /api/v1/integrations/deliveries/{delivery_id}/replay`

The dashboard reports tenant-wide status counts, success rate, and endpoint totals. Restrict endpoint management and replay to administrators and review dead-letter alerts operationally.

`enforce` marks a decision as authoritative for an approved downstream enforcement point. OpenDataGraph itself performs no destructive source-system action.
