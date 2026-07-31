# Production Enforcement

OpenDataGraph v1.9 separates policy decision points from policy enforcement points while preserving receipt-linked evidence. A permit is not treated as proof that controls were applied: the enforcement point must apply every required obligation or fail closed and report the outcome.

## Enforcement API

- `POST /api/v1/runtime/enforcement-events` requires `analyst`.
- `GET /api/v1/runtime/enforcement-events` requires `auditor`.

An enforcement event identifies the runtime receipt, PEP, outcome, satisfied obligations, occurrence time, and an SHA-256 digest of bounded metadata. Metadata values are not retained. `applied` is accepted only when the receipt permitted the operation and every required obligation is satisfied. `rejected` and `failed` require a reason. Caller-supplied event IDs are tenant-scoped and idempotent; conflicting reuse returns `409`.

## SDKs

The Python SDK is under `sdks/python` and the TypeScript SDK is under `sdks/typescript`. Both:

1. request an AuthZEN decision;
2. require a durable receipt ID;
3. reject policy denials;
4. execute registered handlers for every required obligation;
5. reject unknown obligations rather than silently ignoring them;
6. run the protected operation only after handlers succeed;
7. report `applied`, `rejected`, or `failed` evidence.

SDKs are reference PEP implementations, not application-specific control libraries. Applications must implement controls such as redaction, private routing, retention, and audit logging in the correct trust boundary and test failure behavior.

## Security

- Use a tenant-bound OIDC workload identity or service account with the least role required.
- Give each enforcement point a stable, non-secret `pep_id`.
- Never place prompts, responses, customer content, tokens, credentials, or secrets in metadata.
- Treat decision expiry and policy context as application requirements; do not cache permits beyond their authorized lifetime.
- Alert when a permitted receipt has no matching enforcement event within the expected application latency.

## Delivery

Authorization and enforcement writes enqueue metadata-only events in the transactional governance outbox. The worker fans those events out to subscribed integration endpoints. Outbox completion means all currently matching delivery records were created; downstream webhook delivery retains its own retry and dead-letter lifecycle.
