# Policy Governance

OpenDataGraph v1.3 adds database-backed lifecycle state around deterministic policy definitions.

## Lifecycle

1. A data owner creates a `draft` bundle.
2. The author submits it to `pending`.
3. An administrator approves it.
4. An administrator activates it, retiring the previous active bundle.
5. An approved or retired bundle can be selected as a rollback target.

Outside local development, the approving identity must differ from the author. Policy simulation evaluates the active bundle without creating a decision audit.

## Exceptions

Administrators can create expiring exceptions scoped by one or more of policy ID, agent, asset, destination, action, or purpose. Exceptions may override to `allow` or `conditional`, include a reason, and add required controls. Expired or revoked exceptions do not match.

## APIs

- `POST|GET /api/v1/policy/bundles`
- `POST /api/v1/policy/bundles/{bundle_id}/submit`
- `POST /api/v1/policy/bundles/{bundle_id}/approve`
- `POST /api/v1/policy/bundles/{bundle_id}/activate`
- `POST /api/v1/policy/bundles/{bundle_id}/rollback`
- `POST|GET /api/v1/policy/exceptions`
- `DELETE /api/v1/policy/exceptions/{exception_id}`

Keep policy changes small, deterministic, reviewed, and covered by matching and non-matching tests.
