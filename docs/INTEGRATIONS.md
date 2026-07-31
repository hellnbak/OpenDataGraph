# Alert and Enforcement Integrations

OpenDataGraph v1.3 delivers policy decision events to approved HTTPS webhooks.

## Safety

- Configure exact destination hosts in `ODG_INTEGRATION_ALLOWED_HOSTS`.
- Store optional signing secrets as `env:` or `file:` references.
- Workers validate the URL before resolving a secret.
- Payloads contain decision context, not connector credentials, prompts, responses, or source content.
- Receivers should deduplicate using `X-OpenDataGraph-Delivery`.

When a signing secret is configured, the worker sends `X-OpenDataGraph-Signature: sha256=<digest>` over the exact request body.

## Modes

- `observe` is intended for alerts, tickets, and monitoring.
- `enforce` marks an authoritative decision for an approved downstream gateway or control point.

OpenDataGraph does not delete, quarantine, or mutate source data. Any downstream enforcement action requires separate authorization and controls.

## APIs

- `POST|GET /api/v1/integrations`
- `DELETE /api/v1/integrations/{endpoint_id}`
- `POST /api/v1/integrations/{endpoint_id}/test`
- `GET /api/v1/integrations/deliveries`

Deliveries use durable jobs with bounded retries and safe error text.
