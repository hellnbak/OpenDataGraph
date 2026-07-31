# Workload Identity Federation

OpenDataGraph v1.9 accepts short-lived signed workload tokens without creating or storing an application credential.

## Trust model

Configure providers in `ODG_WORKLOAD_IDENTITY_PROVIDERS_JSON`. Each provider fixes the OpenDataGraph tenant and maximum role. The token cannot select or elevate either value.

```json
{
  "deployment": {
    "issuer": "https://identity.example.test",
    "audience": "opendatagraph",
    "jwks_url": "https://identity.example.test/keys",
    "tenant_id": "example-tenant",
    "role": "connector-operator",
    "subject_claim": "sub",
    "max_token_seconds": 900
  }
}
```

An explicit HTTPS `jwks_url` or the same bounded discovery configuration used for human OIDC providers is supported. Accepted algorithms are asymmetric RSA or ECDSA algorithms only.

Set `ODG_WORKLOAD_IDENTITY_MAX_TOKEN_SECONDS` from 60 through 3600. A provider may set a smaller `max_token_seconds`. OpenDataGraph rejects tokens whose `exp - iat` exceeds the provider limit.

## Request authentication

Send the JWT in:

```text
X-Workload-Identity-Token: signed-jwt
```

Validation requires signature, exact issuer, exact audience, `iat`, `exp`, `sub`, and the configured lifetime. The principal subject is recorded as `workload:<subject>`. Tokens are request-scoped and are not written to databases, jobs, evidence, integration payloads, or logs.

Do not send multiple authentication mechanisms in one request. Human OIDC bearer authentication remains in `Authorization`; application-managed automation remains in `X-Service-Account-Key`; static tenant-bound keys remain in `X-API-Key`.

## Operational guidance

- Use issuer and audience values dedicated to OpenDataGraph workloads.
- Configure the least-privileged fixed role and one tenant per provider entry.
- Prefer five- to fifteen-minute tokens; never exceed one hour.
- Restrict JWKS and discovery egress at the network layer.
- Monitor rejected issuer, signature, audience, and lifetime validation without logging token values.
- Rotate provider signing keys through JWKS and retain overlap only for the minimum required period.

Inbound authentication validates externally issued tokens and does not issue or refresh them. Separately configured outbound [cloud workload exchange](WORKLOAD_EXCHANGE.md) can exchange a referenced subject token for temporary provider credentials without persisting either token.
