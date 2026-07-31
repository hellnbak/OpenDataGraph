# Service Accounts

Service accounts are tenant-scoped automation identities that use the same ordered roles and authorization checks as human and API-key principals.

## Lifecycle

Administrators create an account through `POST /api/v1/service-accounts`. The response returns:

- account metadata;
- credential metadata;
- one clear `odg_sa_...` key.

The clear key is returned once and cannot be retrieved later. OpenDataGraph stores only a random salt and a PBKDF2-HMAC-SHA256 verifier. Credential responses never include the salt or verifier.

Send the key in `X-Service-Account-Key`. A successful request updates account and credential last-used timestamps. Disabled accounts, revoked credentials, expired credentials, and credentials past their rotation grace period are rejected.

## Rotation

`POST /api/v1/service-accounts/{account_id}/rotate` issues one new key and creates a rotation record. The old credential remains usable until the configured grace deadline unless an administrator completes rotation early:

```text
POST /api/v1/service-accounts/rotations/{rotation_id}/complete
```

Only one unexpired grace-period rotation can be active for an account. A zero-hour grace period revokes the old credential immediately.

`DELETE /api/v1/service-accounts/{account_id}` disables the account and revokes active credentials.

## Reporting

- `GET /api/v1/service-accounts`
- `GET /api/v1/service-accounts/{account_id}`
- `GET /api/v1/service-accounts/lifecycle`

The lifecycle report includes active, disabled, never-used, and stale account counts; active and soon-expiring credentials; and active rotations.

## Configuration

- `ODG_SERVICE_ACCOUNT_CREDENTIAL_DAYS`: default credential lifetime, 1 to 365 days
- `ODG_SERVICE_ACCOUNT_ROTATION_GRACE_HOURS`: default overlap, 0 to 168 hours
- `ODG_SERVICE_ACCOUNT_STALE_DAYS`: inactivity threshold used by lifecycle reporting

## Operational controls

- Assign the least-privileged role.
- Use a named owner and periodically reconcile it with the identity system.
- Deliver the one-time key directly to approved secret management.
- Never place a key in source, job payloads, screenshots, logs, examples, or catalog metadata.
- Rotate before expiry and confirm consumers have moved before completing the grace period.
- Disable unused accounts rather than retaining dormant credentials.
- Treat a copied key as compromised and rotate or disable immediately.

Service accounts do not replace workload identity when a deployment platform can provide short-lived credentials. They provide a tenant-bound application authentication option for OpenDataGraph APIs.
