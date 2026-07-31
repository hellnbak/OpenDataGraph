# Policy Governance

Policy bundles use deterministic definitions and the lifecycle `draft`, `pending`, `approved`, `active`, and `retired`.

## Lifecycle

Data owners create and submit bundles. Administrators or eligible delegated approvers approve pending bundles. Outside development mode, an author cannot approve the same bundle. Activation retires the previous active bundle, and rollback reactivates an approved or retired version.

## Change diffs

`GET /api/v1/policy/bundles/{bundle_id}/diff` compares a bundle with the previous version of the same name. `against_bundle_id` selects another tenant bundle explicitly.

Approved bundles can enter the v1.9 shadow, replay, canary, pause, and promotion workflow instead of immediate activation. See [Policy rollouts](POLICY_ROLLOUTS.md). Existing direct activation remains available for compatibility, but shared deployments should prefer measured rollout for material changes.

The response reports added and removed policy definitions plus field-level before and after values for changed policies. Policy IDs remain the stable comparison key.

## Delegated approvers

Administrators manage tenant-scoped delegations through:

- `POST|GET /api/v1/policy/approver-delegations`
- `DELETE /api/v1/policy/approver-delegations/{delegation_id}`

A delegation names one subject, has a mandatory expiry, and grants bundle approval, exception-renewal approval, or both. Bundle approval may be limited to one bundle name. Revoked or expired delegations have no effect.

Delegation does not change the subject's platform role or grant policy editing, activation, rollback, or delegation management.

## Exceptions and renewal

Exceptions remain time-bounded and scoped by one or more policy, agent, asset, destination, action, or purpose fields. An exception may override a matching decision to `allow` or `conditional` and add controls.

An active exception requests a later expiry through:

- `POST /api/v1/policy/exceptions/{exception_id}/renewal`
- `POST /api/v1/policy/exceptions/{exception_id}/renewal/approve`

Approval requires an administrator or delegated exception approver. Outside development mode, the requester and approver must differ. The current expiry remains authoritative until approval succeeds.

Policy simulation evaluates lifecycle, active bundles, and active exceptions without creating an enforcement audit.

Bundle submission and exception renewal also create unified governance review tasks. Approval completes the corresponding task without replacing existing delegation and separation-of-duty checks. See [Governance operations](GOVERNANCE_OPERATIONS.md).
