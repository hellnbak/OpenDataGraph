# Identity Provisioning

OpenDataGraph validates end-user OIDC bearer tokens separately from SCIM provisioning credentials. Every accepted identity is bound to one tenant.

## OIDC providers

Configure providers in `ODG_OIDC_PROVIDERS_JSON`. Each provider requires an exact HTTPS issuer and audience. Supply either:

- `jwks_url`, or
- optional `discovery_url`; otherwise discovery uses `{issuer}/.well-known/openid-configuration`

Discovery must use the issuer host. The discovered issuer must match exactly. The discovered JWKS host must match the issuer host unless explicitly listed in `jwks_allowed_hosts`. Documents are bounded to 64 KiB and cached for `ODG_OIDC_DISCOVERY_CACHE_SECONDS`.

Example:

```json
{
  "workforce": {
    "issuer": "https://identity.example.test",
    "audience": "opendatagraph",
    "tenant_claim": "tenant_id",
    "role_claim": "roles",
    "role_mapping": {
      "ODG.Auditor": "auditor",
      "ODG.Admin": "administrator"
    }
  }
}
```

Only configured asymmetric JWT algorithms are accepted. Signature, issuer, audience, expiry, issued-at, subject, tenant, and role validation are mandatory.

## SCIM credentials

`ODG_SCIM_TOKENS_JSON` maps each bearer token to a fixed tenant and optional subject:

```json
{
  "replace-with-secret": {
    "tenant_id": "example-tenant",
    "subject": "identity-platform"
  }
}
```

SCIM never accepts tenant context from a header, path, or body. Store tokens in approved secret management and rotate them independently of API keys and OIDC credentials.

## Resources and Bulk

Supported resources:

- `/scim/v2/Users`
- `/scim/v2/Groups`
- `/scim/v2/Bulk`

Users and groups support list, equality filters, create, replace, patch, and delete semantics. Payloads are limited to 64 KiB and password attributes are rejected.

Bulk requests are limited by `ODG_SCIM_BULK_MAX_OPERATIONS` and 1 MiB total size. Operations execute sequentially and return individual status values. `bulkId:` references can point to resources created earlier in the same request. `failOnErrors` stops processing after the requested error count; completed operations are not rolled back.

## Deprovisioning

Disabling a user through replace or patch, or deleting a user, creates a durable `identity.deprovision` workflow instead of hard-deleting the SCIM record. The worker:

1. confirms the user is inactive;
2. removes the user from tenant SCIM groups;
3. records completion and the requesting identity;
4. optionally emits `identity.deprovisioned` to subscribed integrations.

`GET /api/v1/identity/deprovisioning` exposes workflow state to auditors. Downstream identity and application systems remain responsible for revoking their own access when they receive the event.
