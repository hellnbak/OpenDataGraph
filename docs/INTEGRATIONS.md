# Alert and Enforcement Integrations

OpenDataGraph sends bounded policy, identity, governance, graph-export, and test events to approved HTTPS webhooks. It does not mutate source systems.

## Endpoint controls

Administrators create endpoints with an allowlisted URL, `observe` or `enforce` mode, subscribed event names, event format, and optional worker-resolved secret. `ODG_INTEGRATION_ALLOWED_HOSTS` must contain every permitted destination host.

Events are limited to 256 KiB before delivery records and jobs are created. Supported formats are:

- `native`: canonical OpenDataGraph JSON;
- `cloudevents`: CloudEvents 1.0 structured JSON;
- `cef`: Common Event Format text with escaped extension values;
- `splunk-hec`: Splunk HTTP Event Collector JSON.
- `kafka-rest`: CloudEvents 1.0 values wrapped in a Kafka REST Proxy JSON `records` request and keyed by tenant.

Secrets use `env:` or `file:` references and are never stored in delivery payloads. Native, CloudEvents, and CEF workers sign the exact request body using HMAC-SHA256 in `X-OpenDataGraph-Signature`. Splunk HEC uses the resolved secret in `Authorization: Splunk ...`; use a dedicated least-privilege HEC token.

Every delivery includes `X-OpenDataGraph-Delivery`, `X-OpenDataGraph-Event`, `X-OpenDataGraph-Mode`, and `X-OpenDataGraph-Format`.

## Transactional governance outbox

Runtime authorization, enforcement, rollout, and GenAI telemetry operations add bounded metadata-only events to `governance_outbox_events` in the same transaction as their authoritative record. Workers atomically claim pending events, recover stale claims, retry with bounded backoff, and stop at `ODG_GOVERNANCE_OUTBOX_MAX_ATTEMPTS`. The outbox creates normal integration deliveries with event-level idempotency, so existing delivery retries and dead-letter controls still apply.

Outbox payloads reject secret-, credential-, prompt-, response-, and token-named fields and are limited to 64 KiB. Auditors can inspect outbox state; administrators can request bounded manual dispatch for operational recovery.

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
- `GET /api/v1/integrations/outbox`
- `POST /api/v1/integrations/outbox/dispatch`

The dashboard reports tenant-wide status counts, success rate, and endpoint totals. Restrict endpoint management and replay to administrators and review dead-letter alerts operationally.

`enforce` marks a decision as authoritative for an approved downstream enforcement point. OpenDataGraph itself performs no destructive source-system action.
