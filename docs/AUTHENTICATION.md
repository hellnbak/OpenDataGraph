# Authentication and Tenancy

OpenDataGraph v1.9 binds each API-key, service account, validated human OIDC principal, or short-lived workload identity to a role and tenant.

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

## Service accounts

Administrators can issue application-managed automation credentials without editing static API-key configuration. Send the one-time credential in `X-Service-Account-Key`. Accounts use the same roles and tenant authorization boundary as other principals and support bounded expiry, rotation overlap, explicit rotation completion, disabling, and lifecycle reporting.

OpenDataGraph stores only salted PBKDF2 verifiers. It never returns a clear credential after creation or rotation. See [Service accounts](SERVICE_ACCOUNTS.md).

Roles, from least to most privileged:

1. read-only
2. auditor
3. analyst
4. connector-operator
5. data-owner
6. administrator

Every principal is bound to one tenant. Data-bearing APIs do not accept a caller-selected tenant header or tenant request field.

AuthZEN single and batch evaluation requires `analyst`; runtime receipt inspection and verification require `auditor`; AI resource and expected-lineage changes require `data-owner`; lineage observation requires `analyst`. The subject inside an authorization request is policy input and never replaces the authenticated caller or its tenant and role.

## OIDC validation

`ODG_OIDC_PROVIDERS_JSON` configures one or more providers with exact issuer, audience, accepted asymmetric algorithms, claim paths, and optional role mapping. Providers may use an explicit HTTPS JWKS URL or bounded, cached OpenID Connect discovery. Bearer tokens are rejected unless signature, issuer, audience, lifetime, subject, tenant, and supported role validation succeeds.

Discovery uses the configured issuer host and requires an exact issuer match. Explicitly list any different discovered JWKS host in the provider's `jwks_allowed_hosts`. Keep the identity provider, ingress, and application validation aligned. Do not allow unsigned tokens, symmetric algorithms, caller-selected tenants, or unrestricted discovery or JWKS locations.

## Workload identity

`ODG_WORKLOAD_IDENTITY_PROVIDERS_JSON` configures external automation issuers separately from human OIDC. Each provider fixes one tenant and role. Tokens arrive in `X-Workload-Identity-Token`, require the same asymmetric signature, issuer, audience, expiry, and subject validation, and may live for no more than one hour.

Workload tokens are never stored. OpenDataGraph does not exchange or refresh them. See [Workload identity federation](WORKLOAD_IDENTITY.md).

## SCIM

SCIM provisioning uses separate bearer tokens bound to tenants in `ODG_SCIM_TOKENS_JSON`. It never accepts caller-selected tenant context or reuses end-user OIDC tokens or API keys. Bulk provisioning and durable deprovisioning use the same credential boundary. See [Identity provisioning](IDENTITY_PROVISIONING.md).

## Isolation behavior

Tenant filters apply to assets, agents, policy audits, bundles, rollouts and replays, runtime receipts and enforcement events, GenAI telemetry, AI resources and lineage, delegations, exceptions, connector runs and schedules, classification reviews, AI usage events, OpenLineage, graph edges and exports, jobs, evidence and dispositions, integration outbox events and deliveries, SCIM resources and deprovisioning workflows, service accounts, governance reviews and packages, and ownership campaigns and schedules. Cross-tenant object identifiers return `404` rather than revealing that the object exists.

The opt-in remote MCP preview requires an OIDC bearer token in authenticated deployments even if another credential type could satisfy the route role. Configure issuer, audience, tenant claim, role claim, discovery, and JWKS restrictions as described above; the gateway does not perform a separate MCP OAuth flow.

Use separate databases when policy requires physical, cryptographic, regional, or customer-managed-key isolation.
