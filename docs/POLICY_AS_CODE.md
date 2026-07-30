# Policy as Code

OpenDataGraph loads YAML policy definitions from `ODG_POLICY_DIRECTORY`.

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

## Match fields

The v1.1 engine supports asset sensitivity, destination type, agent status, action, and purpose. Multiple fields use AND behavior; list values match any listed option.

## Decisions

Policy decisions are ordered by severity:

```text
allow < conditional < deny
```

Matched policies contribute reasons, controls, and risk. The most severe matched decision is combined with agent approval, sensitivity ceiling, domain scope, destination approval, and asset exposure.

## Simulation

`POST /api/v1/policy/simulate` evaluates the current policy bundle without recording an enforcement audit. Use simulation to validate expected outcomes before activating policy changes.
