# Authentication and Tenancy

OpenDataGraph v1.2 binds each API-key principal to a role and tenant.

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

Every key is bound to one tenant. The application does not accept a caller-selected tenant header or tenant request field.

## Isolation behavior

Tenant filters apply to assets, agents, policy audits, connector runs, classification reviews, AI usage events, graph edges, jobs, and evidence. Cross-tenant object identifiers return `404` rather than revealing that the object exists.

Use separate databases when policy requires physical, cryptographic, regional, or customer-managed-key isolation.

## OIDC boundary

`ODG_OIDC_ISSUER` and `ODG_OIDC_AUDIENCE` describe the intended identity provider and audience. v1.2 exposes this integration boundary but does not perform provider-specific JWT validation. Shared deployments must use a validating identity-aware gateway until application validation is implemented.
