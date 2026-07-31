# OpenDataGraph v1.8.0

OpenDataGraph v1.8 adds runtime governance and scale controls: AuthZEN-compatible policy decisions, enforceable obligations, durable decision receipts, deferred cryptographic signing, governed MCP context access, first-class AI resources, expected-versus-observed AI lineage, and expanded performance qualification.

All v1.1 through v1.7 capabilities remain part of the platform. The README lists cumulative platform capabilities separately from release-specific additions.

## Runtime authorization

The policy decision point accepts OpenID AuthZEN Authorization API 1.0 single and bounded batch request shapes at `/access/v1/evaluation` and `/access/v1/evaluations`. Well-known metadata advertises only the implemented evaluation endpoints. Existing OpenDataGraph policy APIs remain available.

`enforce` blocks policy denials, while conditional decisions are returned as permits with explicit obligations for the policy-enforcement point. `warn` and `observe` preserve the underlying policy decision and obligations but permit the request. Shared deployments default to `enforce` and must authenticate the caller with at least the analyst role.

Every completed evaluation creates a tenant-scoped receipt containing subject, action, and resource identifiers; digests of request properties and context; the policy result; obligations; enforcement mode; and retention. Raw property and context values are not copied into the signed manifest. `X-Request-ID` is correlated and optional `Idempotency-Key` reuse is accepted only for the same request digest.

## Receipt assurance

Receipt creation and the authorization response use one synchronous database transaction. This makes authorization evidence durable before the permit or deny is returned, but database commit latency is part of the hot path.

When configured, workers claim pending receipts and sign canonical manifests outside the request path with the existing Ed25519, AWS KMS, or Sigstore profiles. Claims recover after timeout and failures retry with bounded backoff. Verification reports stored digest validity, cryptographic signature validity, and configured trust separately. Expired completed receipts are deleted in bounded worker batches.

## Governed AI resources and lineage

Tenants can register models, prompts, vector indexes, tools, endpoints, and AI systems with owners, provider, region, status, risk tier, and bounded metadata. Runtime authorization denies access to missing or unapproved AI resources.

Data owners declare expected relationships across AI resources, agents, data assets, and datasets. Analysts ingest idempotent observations. A new or inactive relationship is marked as drift, while an expected active relationship updates observation counts and timestamps without drift. Relationships project into the existing graph for bounded traversal and export.

## Governed MCP

Read-oriented MCP tools now act as policy-enforcement points and request a runtime decision before catalog, summary, AI activity, or relationship access. `ODG_MCP_AGENT_KEY` identifies the registered agent and `ODG_MCP_AUTHORIZATION_REQUIRED=true` keeps governance enabled. The existing `authorize_ai_data_use` tool remains compatible; new tools expose generic runtime evaluation and receipt inspection.

The local MCP server still uses the SDK default transport. v1.8 does not add a public remote MCP authorization server or claim MCP OAuth conformance.

## Scale characteristics

The request path performs no KMS, Sigstore, connector, search, webhook, or cloud exchange call. Active policy definitions are cached per process for a bounded interval, batch requests reuse repeated entity lookups, and batch receipts commit together. PostgreSQL connection pool bounds are configurable per process.

Migration `20260731_0007` adds lean tenant-leading receipt, subject, resource, decision, AI resource, relationship, drift, signing-queue, retention, and policy-exception indexes without redundant field indexes on high-write tables. Benchmarks now measure durable single authorization and ten-item batch throughput. Read-only PostgreSQL plan capture covers receipt lookup, signing claims, retention cleanup, and lineage drift.

OpenDataGraph does not publish a universal capacity claim. Durable receipt writes make PostgreSQL commit throughput the principal authorization limit. Signing throughput depends on signer latency and worker count. Operators must qualify representative policy, exception, batch, receipt-retention, database, and signer distributions against explicit p95 and error-rate budgets.

## Upgrade

1. Stop API and worker processes.
2. Create and verify database, evidence, graph-export, and governance-package backups.
3. Review `ODG_PUBLIC_BASE_URL`, database pool bounds, authorization mode, batch limit, receipt retention, signing profile, signing batch size, and purge batch size.
4. Run `alembic upgrade head`.
5. Start migration, API, and worker roles from the same v1.8 image and connector plugin set.
6. Verify `/health`, `/ready`, Alembic revision `20260731_0007`, tenant isolation, and AuthZEN metadata.
7. Exercise allow, conditional, and deny evaluations plus `execute_all`, `deny_on_first_deny`, and `permit_on_first_permit` batches.
8. If signing is enabled, confirm a receipt progresses from pending to signed and verifies against an independent trust profile.
9. Register synthetic AI resources, declare one expected relationship, and verify an unexpected observation appears as drift.
10. Run runtime authorization benchmarks and inspect representative PostgreSQL plans before accepting production traffic.

Downgrades are not supported. Restore the verified pre-upgrade database and object-storage state if rollback is required.

## Compatibility and limitations

- Existing APIs and v1.1 through v1.7 workflows remain available.
- AuthZEN subject, action, resource, context, decision, batch defaults, and batch semantics are implemented; AuthZEN search APIs and signed PDP metadata are not implemented.
- The well-known PDP identifier must be an externally reachable HTTPS URL in shared deployments; configure `ODG_PUBLIC_BASE_URL` behind proxies.
- Conditional decisions require the policy-enforcement point to understand and apply returned obligations or reject the operation.
- Receipt signing is eventually completed. A successful decision can initially reference a pending or unsigned receipt.
- Receipts retain identifiers, decisions, reasons, obligations, and request-property digests. Do not place prompts, responses, credentials, or customer content in authorization identifiers.
- AI lineage drift means an observed relationship was not declared active and expected; it is not proof of malicious activity.
- The MCP server remains a trusted local process and requires a registered, least-privileged AI agent identity.
- SQLite remains suitable for local development and tests, not high-concurrency authorization.
- Benchmarks and plan fingerprints are environment-specific evidence, not certified capacity.

## License

OpenDataGraph v1.8.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 31, 2028. Earlier releases retain the terms distributed with those releases.
