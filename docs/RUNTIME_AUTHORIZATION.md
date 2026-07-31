# Runtime Authorization

OpenDataGraph v1.9 exposes a policy-decision point using the subject, resource, action, context, decision, default-value, batch-semantics, and search shapes from the [OpenID AuthZEN Authorization API 1.0](https://openid.net/specs/authorization-api-1_0.html).

## Endpoints

- `GET /.well-known/authzen-configuration`
- `POST /access/v1/evaluation`
- `POST /access/v1/evaluations`
- `POST /access/v1/search/subject`
- `POST /access/v1/search/resource`
- `POST /access/v1/search/action`
- `GET /api/v1/runtime/decision-receipts`
- `GET /api/v1/runtime/decision-receipts/{receipt_id}`
- `POST /api/v1/runtime/decision-receipts/{receipt_id}/verify`
- `POST|GET /api/v1/runtime/enforcement-events`

The well-known document advertises implemented evaluation and search endpoints. Signed PDP metadata is not implemented. Configure `ODG_PUBLIC_BASE_URL` to the externally reachable HTTPS PDP identifier in shared deployments.

Evaluation requires the `analyst` role. Receipt listing and verification require `auditor`. The normal tenant-bound API key, service account, human OIDC, or workload identity mechanisms authenticate the PDP request; authorization transport is separate from the access decision itself.

## Single evaluation

```json
{
  "subject": {
    "type": "ai_agent",
    "id": "customer-support-copilot"
  },
  "resource": {
    "type": "data_asset",
    "id": "42"
  },
  "action": {
    "name": "send"
  },
  "context": {
    "destination": "internal-rag",
    "purpose": "customer-support"
  }
}
```

The response preserves the required boolean decision and uses AuthZEN decision context for OpenDataGraph extensions:

```json
{
  "decision": true,
  "context": {
    "policy_decision": "conditional",
    "enforcement_mode": "enforce",
    "risk_score": 70,
    "policy_version": "1.9.0",
    "matched_policies": ["require-approval-for-training"],
    "reasons": ["Training use requires explicit data-owner approval and a documented retention boundary."],
    "obligations": [
      {
        "id": "data-owner-approval",
        "required": true,
        "enforced_by": "policy-enforcement-point"
      }
    ],
    "receipt": {
      "id": "receipt-uuid",
      "sha256": "manifest-digest",
      "signing_status": "pending",
      "signing_profile": "runtime-signing",
      "retention_until": "2026-10-29T12:00:00"
    }
  }
}
```

A conditional policy result is a permit with obligations. A policy-enforcement point that does not understand or cannot satisfy a required obligation should reject the operation. A deny remains an HTTP `200` response with `"decision": false`; transport and validation errors use error status codes.

`X-Request-ID` is copied into receipt correlation metadata and echoed by the HTTP middleware. `Idempotency-Key` is an OpenDataGraph transport extension. Reusing it with the same canonical request returns the original decision and receipt; reuse with a different request digest returns `409`.

## Batch evaluation

`/access/v1/evaluations` accepts top-level default subject, resource, action, and context values plus per-item overrides. It supports:

- `execute_all`
- `deny_on_first_deny`
- `permit_on_first_permit`

The default limit is 100 evaluations, the hard limit is 1,000, each resolved evaluation is limited to 64 KiB, and the complete batch is limited to 2 MiB. A batch commits all generated receipts in one transaction and reuses repeated subject, data asset, and AI resource lookups within the request. Indexed receipt and request identifiers receive an item suffix.

## Search

Search endpoints return subjects, resources, or actions that receive a non-deny policy result for the supplied fixed entities and context. They create no decision receipt and are discovery aids rather than enforcement evidence. Results are bounded by `ODG_AUTHZEN_SEARCH_MAX`; pagination tokens are opaque, authenticated, and bound to the tenant, search kind, complete request, and offset. Shared deployments must provide a strong externally managed `ODG_AUTHZEN_PAGINATION_SECRET`.

## Enforcement modes

`ODG_RUNTIME_AUTHORIZATION_MODE` controls only the final boolean decision; the receipt always preserves the underlying policy result.

| Mode | Policy allow | Policy conditional | Policy deny |
| --- | --- | --- | --- |
| `enforce` | permit | permit with obligations | deny |
| `warn` | permit | permit with obligations | permit with denial warning |
| `observe` | permit | permit with obligations | permit with observed denial |

Shared deployments should use `enforce`. `warn` and `observe` are migration and discovery modes, not equivalent enforcement.

## Resource resolution

- `ai_agent` or `agent` subjects must identify a registered tenant AI agent. Missing or unapproved agents are denied.
- `data_asset` or `asset` resources resolve by numeric database ID or connector external ID. Missing assets are denied.
- `model`, `prompt`, `vector-index`, `tool`, `endpoint`, and `ai-system` resources must be registered and approved.
- Other subject and resource types use deterministic policy context without an inventory lookup.

For registered agent and data-asset pairs, the existing AI data-use policy path remains authoritative, including sensitivity ceilings, destination boundaries, training controls, active bundles, and scoped exceptions.

## Decision receipts

Receipt creation is part of the authorization database transaction. The receipt contains entity identifiers, request and manifest digests, policy result, mode, risk, reasons, obligations, retention, and assurance state. The canonical manifest contains SHA-256 digests of subject, resource, action properties, and context rather than their raw values.

Do not place credentials, authorization headers, prompts, responses, file content, or customer records in identifiers. Properties and context are processed in memory and can still reach policy logic; request logging must remain body-free.

When `ODG_RUNTIME_RECEIPT_SIGNING_PROFILE` selects a configured governance signing profile, the initial receipt is `pending`. Workers atomically claim pending rows and sign outside the request path. Ed25519, AWS KMS, and Sigstore use the same external reference and independent trust profiles as governance packages. Signing failure retries with bounded backoff and stale claims recover after the worker timeout.

Verification reports:

- stored manifest digest validity;
- signed versus unsigned state;
- cryptographic signature validity;
- trust against the selected verification profile.

Unsigned or pending receipts can be integrity-valid without being cryptographically signed or trusted.

v1.9 receipt manifest format 2 also records a digest of an allowlisted replay context and rollout baseline-versus-candidate results. The relational receipt records replay eligibility and the bounded context used for simulation. Replay context excludes arbitrary properties and content. Existing format 1 receipts remain verifiable. See [Policy rollouts](POLICY_ROLLOUTS.md) and [Production enforcement](PRODUCTION_ENFORCEMENT.md).

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `ODG_PUBLIC_BASE_URL` | derived request URL | External PDP identifier and endpoint base |
| `ODG_RUNTIME_AUTHORIZATION_MODE` | `enforce` | Observe, warn, or enforce |
| `ODG_RUNTIME_AUTHORIZATION_BATCH_MAX` | `100` | Accepted batch evaluations, hard-capped at 1,000 |
| `ODG_AUTHZEN_SEARCH_MAX` | `100` | Search results per page, hard-capped at 500 |
| `ODG_AUTHZEN_PAGINATION_SECRET` | empty | HMAC secret required for shared AuthZEN search pagination |
| `ODG_POLICY_CACHE_SECONDS` | `5` | Per-process effective-policy cache interval |
| `ODG_POLICY_ROLLOUT_CACHE_SECONDS` | `5` | Per-process active rollout cache interval |
| `ODG_RUNTIME_RECEIPT_RETENTION_DAYS` | `90` | Receipt retention from issuance |
| `ODG_RUNTIME_RECEIPT_SIGNING_PROFILE` | empty | Deferred signer profile |
| `ODG_RUNTIME_RECEIPT_SIGNING_BATCH_SIZE` | `100` | Maximum claims per worker pass |
| `ODG_RUNTIME_RECEIPT_SIGNING_MAX_ATTEMPTS` | `3` | Signing attempts before failure |
| `ODG_RUNTIME_RECEIPT_PURGE_BATCH_SIZE` | `10000` | Expired completed receipts removed per maintenance pass |

See [Scaling](SCALING.md), [Policy as code](POLICY_AS_CODE.md), [Evidence signing](EVIDENCE_SIGNING.md), and [Authentication](AUTHENTICATION.md).
