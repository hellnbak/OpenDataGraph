# Policy Rollouts

OpenDataGraph v1.9 provides a tenant-scoped rollout workflow for approved policy bundles. Only one rollout can be active per tenant.

## Stages

- `shadow`: evaluate baseline and candidate policies, enforce the baseline, and record both outcomes.
- `canary`: deterministically select the configured 1–99 percent of canonical request digests for candidate enforcement; the same request remains in the same bucket.
- `paused`: enforce the baseline while retaining rollout state.
- `enforce`: activate the approved candidate bundle, retire the previous active bundle, and complete the rollout.
- `completed`: close the rollout without activating the candidate.

Allowed transitions prevent direct shadow-to-enforce promotion. Administrators must move through canary before enforcement. Rollout configuration is cached per process for `ODG_POLICY_ROLLOUT_CACHE_SECONDS`; local changes invalidate the local cache immediately, while other replicas converge after the configured interval.

## Replay

`POST /api/v1/policy/rollouts/{rollout_id}/replays` re-evaluates a bounded set of recent receipts against the candidate bundle without creating new authorization receipts or enforcement events. Receipts retain only an allowlisted replay context and are marked replayable only for registered AI-agent requests targeting cataloged assets or governed AI resources.

Replay uses current catalog, agent, AI-resource, and exception state. It is change-impact simulation, not forensic reproduction of historical state. Results report evaluated, changed, newly denied, newly permitted, and incomplete counts plus at most 100 changed examples.

## APIs and roles

- `POST /api/v1/policy/rollouts`: `administrator`
- `GET /api/v1/policy/rollouts`: `auditor`
- `GET /api/v1/policy/rollouts/{rollout_id}`: `auditor`
- `POST /api/v1/policy/rollouts/{rollout_id}/replays`: `administrator`
- `GET /api/v1/policy/rollouts/{rollout_id}/replays`: `auditor`
- `POST /api/v1/policy/rollouts/{rollout_id}/advance`: `administrator`

Before promotion, review replay deltas, shadow receipts, canary denials, enforcement failures, database latency, outbox lag, and application-specific error budgets. Rollback after activation uses the existing policy-bundle rollback workflow; completed rollout records remain audit evidence.
