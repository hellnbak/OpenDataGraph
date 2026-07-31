# Identity Provisioning

## OIDC

Set `ODG_AUTH_DISABLED=false` and supply provider objects in `ODG_OIDC_PROVIDERS_JSON` through external secret management:

```json
{
  "enterprise-idp": {
    "issuer": "https://identity.example.test/tenant",
    "audience": "opendatagraph",
    "jwks_url": "https://identity.example.test/tenant/keys",
    "algorithms": ["RS256"],
    "subject_claim": "sub",
    "tenant_claim": "tenant_id",
    "role_claim": "roles",
    "role_mapping": {
      "ODG.Reader": "read-only",
      "ODG.Admin": "administrator"
    }
  }
}
```

Bearer tokens are accepted only when signature, algorithm, issuer, audience, issued-at, expiry, subject, tenant, and role validation succeeds. Tenant values must match the platform tenant identifier format.

## SCIM

Set tenant-bound credentials through `ODG_SCIM_TOKENS_JSON` using external secret management:

```json
{
  "replace-with-tenant-a-secret": {
    "tenant_id": "tenant-a",
    "subject": "tenant-a-scim-client"
  }
}
```

SCIM requests send only `Authorization: Bearer <tenant-bound-secret>`. The application derives tenant context from the credential and never accepts caller-selected tenant context. `ODG_SCIM_BEARER_TOKEN` remains a single-tenant compatibility setting bound to `ODG_DEFAULT_TENANT`.

Supported endpoints:

- `GET|POST /scim/v2/Users`
- `GET|PUT|PATCH|DELETE /scim/v2/Users/{id}`
- `GET|POST /scim/v2/Groups`
- `GET|PUT|PATCH|DELETE /scim/v2/Groups/{id}`

Filters support `userName`, `externalId`, or `displayName` equality. Payloads are limited to 64 KiB and password attributes are rejected. Rotate the SCIM token independently from API keys and OIDC signing keys.
