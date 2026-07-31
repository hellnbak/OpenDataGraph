# Policy as Code

OpenDataGraph loads deterministic YAML policy definitions from `ODG_POLICY_DIRECTORY`.

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

v1.2 adds `tenant-context` to standard controls and stores policy audits in the authenticated tenant.

## Simulation

`POST /api/v1/policy/simulate` evaluates the current bundle without recording an enforcement audit. Asset and agent lookups remain tenant-scoped.
