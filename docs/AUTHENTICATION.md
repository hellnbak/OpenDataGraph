# Authentication and Tenancy

OpenDataGraph v1.3 binds each API-key or validated OIDC principal to a role and tenant.

## Local mode

`ODG_AUTH_DISABLED=true` grants a development administrator principal in `ODG_DEFAULT_TENANT`. Use this only on a trusted local machine.

## API keys

Set `ODG_AUTH_DISABLED=false` and provide a JSON object through an approved secret mechanism:

```json
{
  "replace-with-secret-value": {
    "subject": "connector-service",
    "role": "connector-operator",
    "tenant_id": "example-tenant"
  }
}
```

Send the key in `X-API-Key`.

Roles, from least to most privileged:

1. read-only
2. auditor
3. analyst
4. connector-operator
5. data-owner
6. administrator

Every principal is bound to one tenant. Data-bearing APIs do not accept a caller-selected tenant header or tenant request field.

## OIDC validation

`ODG_OIDC_PROVIDERS_JSON` configures one or more providers with exact issuer, audience, HTTPS JWKS URL, accepted asymmetric algorithms, claim paths, and optional role mapping. Bearer tokens are rejected unless signature, issuer, audience, lifetime, subject, tenant, and supported role validation succeeds.

Keep the identity provider, ingress, and application validation aligned. Do not allow unsigned tokens, symmetric algorithms, caller-selected tenants, or unrestricted JWKS locations.

## SCIM

SCIM provisioning uses separate bearer tokens bound to tenants in `ODG_SCIM_TOKENS_JSON`. It never accepts caller-selected tenant context or reuses end-user OIDC tokens or API keys. See [Identity provisioning](IDENTITY_PROVISIONING.md).

## Isolation behavior

Tenant filters apply to assets, agents, policy audits and bundles, exceptions, connector runs and schedules, classification reviews, AI usage events, lineage, graph edges, jobs, evidence, integrations, and SCIM resources. Cross-tenant object identifiers return `404` rather than revealing that the object exists.

Use separate databases when policy requires physical, cryptographic, regional, or customer-managed-key isolation.
