# Policy as Code

OpenDataGraph loads deterministic YAML policy definitions from `ODG_POLICY_DIRECTORY` when no database-backed policy bundle is active.

```yaml
id: deny-restricted-data-to-public-ai
version: 1
description: Prevent restricted data from being sent to public AI services.
match:
  sensitivity:
    - Restricted
  destination_type:
    - public_ai
decision: deny
risk_score: 95
reason: Restricted data cannot be sent to an unapproved public AI destination.
controls:
  - use-approved-private-model
  - require-security-review
```

## Matching and decisions

The engine supports asset sensitivity, destination type, agent status, action, and purpose. Multiple fields use AND behavior; list values match any listed option.

Decisions are ordered `allow < conditional < deny`. Matched rules contribute reasons, controls, and risk. The result also considers agent approval, sensitivity ceiling, domain scope, destination approval, and asset exposure.

Standard controls include `tenant-context`, and policy audits and runtime receipts remain in the authenticated tenant. v1.8 retains versioned bundles, structured diffs, delegated review, activation, rollback, expiring exceptions, renewal, unified operational review tasks, analytics, and signed metadata-only evidence packaging.

AuthZEN runtime evaluation maps subject, resource, action, and context attributes into the same deterministic policy context. Registered agent and data-asset pairs use the full existing AI data-use evaluation path. Conditional runtime results return obligations for the policy-enforcement point. Effective definitions are cached for `ODG_POLICY_CACHE_SECONDS`; active-bundle activation invalidates the local process immediately and other replicas observe the change after their bounded interval.

See [Policy governance](POLICY_GOVERNANCE.md) and [Runtime authorization](RUNTIME_AUTHORIZATION.md).

## Simulation

`POST /api/v1/policy/simulate` evaluates the active database bundle, or the YAML fallback, without recording an enforcement audit. Asset and agent lookups remain tenant-scoped.
