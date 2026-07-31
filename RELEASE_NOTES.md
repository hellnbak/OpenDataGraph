# OpenDataGraph v1.9.0

OpenDataGraph v1.9 moves runtime governance closer to application enforcement and fleet operations. It adds receipt-linked enforcement evidence, fail-closed Python and TypeScript PEP SDKs, measured policy rollout, AuthZEN search, metadata-only GenAI telemetry, a transactional governance outbox, Kafka REST CloudEvents delivery, a stateless remote MCP preview, and NIST AI RMF evidence-gap reporting.

All v1.1 through v1.8 capabilities remain part of the platform. The README contains the cumulative capability list; this document describes only v1.9 additions and changed operational requirements.

## Production enforcement

Applications can report `applied`, `rejected`, or `failed` outcomes against a durable runtime receipt. The API verifies tenant ownership, permit state, required obligations, and idempotency, and stores only a digest of caller metadata. An applied event is rejected unless every required receipt obligation is satisfied.

Reference Python and TypeScript SDKs request AuthZEN decisions, reject denials, reject unknown required obligations, run registered obligation handlers before the protected operation, and report receipt-linked evidence. The SDKs do not implement application-specific controls; operators remain responsible for correct redaction, routing, retention, and audit implementations.

## Policy rollout

Approved policy bundles can be replayed against recent replayable receipts, observed in shadow, routed through deterministic canary buckets, paused, promoted, or completed without promotion. Runtime receipts record rollout identity, stage, selection bucket, and baseline-versus-candidate outcomes.

Replay retains only allowlisted context and evaluates current inventory, identity, resource, and exception state. It is impact simulation, not forensic reconstruction. Only one rollout can be active per tenant, and direct shadow-to-enforce promotion is prohibited.

## AuthZEN search

Subject, resource, and action search endpoints implement the corresponding AuthZEN Authorization API 1.0 shapes. Search creates no receipts. Results are bounded and pagination tokens are opaque, HMAC-authenticated, and bound to tenant, search kind, request, and offset. Shared deployments must configure `ODG_AUTHZEN_PAGINATION_SECRET` through external secret management.

## GenAI telemetry

OTLP/HTTP JSON GenAI spans can be ingested in bounded batches. OpenDataGraph retains normalized provider, model, operation, agent, token, duration, finish-reason, identity, and digest fields. Known prompt, response, message, system-instruction, tool-argument, and tool-result attributes are discarded before persistence.

Unseen models enter the AI resource registry with owner `unassigned`, status `review`, and high risk. Registered agent-to-model activity creates idempotent lineage observations and graph projection. The endpoint is not a general OpenTelemetry collector and does not support protobuf or gRPC.

## Outbox and integrations

Runtime authorization, enforcement, rollout, and telemetry operations enqueue metadata-only events in the same transaction as their authoritative records. Workers atomically claim events, recover stale claims, retry with bounded backoff, and create idempotent integration deliveries.

Integration endpoints can select `kafka-rest`, which wraps a structured CloudEvent in a Kafka REST Proxy JSON records request keyed by tenant. Existing native, CloudEvents, CEF, and Splunk HEC formats remain available.

## Remote MCP preview

An opt-in `POST /mcp` endpoint supports the stateless `2026-07-28` profile for server discovery, tool listing, and a small read and authorization tool catalog. Authenticated deployments require an OIDC bearer token, a registered configured agent, TLS, and ingress rate and size controls. The preview does not claim full remote MCP or Enterprise-Managed Authorization conformance and stores no MCP session.

The existing local MCP server remains available and backward compatible.

## Governance frameworks

A versioned NIST AI RMF 1.0 mapping reports whether tenant inventory, lineage, receipts, enforcement, telemetry, bundles, and rollout evidence exists in a selected window. Reports identify evidence and gaps; they do not certify compliance or assess control effectiveness.

## Scale characteristics

Receipt and outbox writes share the authorization transaction. Shadow and canary traffic evaluates baseline and candidate policy. Telemetry performs per-span idempotency and discovery lookups with one batch commit. Outbox events can fan out to every matching integration endpoint. These changes improve durability and decoupling but add measurable database and worker load.

OpenDataGraph publishes no universal capacity claim. Qualify realistic policy size, rollout percentage, receipt rate, OTLP batch and model cardinality, endpoint fan-out, signer latency, worker count, PostgreSQL durability, and failure recovery against explicit budgets.

## Upgrade

1. Stop API and worker processes and verify backups.
2. Review new AuthZEN search, rollout, telemetry, outbox, MCP, and SDK configuration.
3. Run `alembic upgrade head` to revision `20260731_0008`.
4. Start migration, API, and worker roles from the same v1.9 image and connector plugin set.
5. Verify health, readiness, AuthZEN metadata, enforcement evidence, replay and shadow comparison, telemetry content discard, outbox delivery, and tenant isolation.
6. Enable canary policy or remote MCP traffic only after representative qualification.

Downgrades are not supported. Restore the verified pre-upgrade state to roll back.

## Compatibility and limitations

- Existing APIs and all v1.1 through v1.8 workflows remain available.
- Search results are authorization discovery, not decision or enforcement evidence.
- Conditional permits require a PEP that understands every required obligation and fails closed.
- Replay uses current state and a bounded allowlisted context.
- Remote MCP is disabled by default and is a narrow stateless preview.
- OTLP ingestion is JSON trace metadata only and intentionally discards content.
- Framework coverage is not certification or a compliance determination.
- SQLite remains suitable for local development and tests, not high-concurrency authorization or telemetry.
- Benchmarks and query-plan fingerprints are environment-specific evidence, not certified capacity.

## License

OpenDataGraph v1.9.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 31, 2028. Earlier releases retain the terms distributed with those releases.
