# Authentication and Roles

OpenDataGraph v1.1 includes API-key authentication and an OIDC integration boundary.

## Local mode

`ODG_AUTH_DISABLED=true` grants a development administrator principal. Use it only on a trusted local machine.

## API keys

Set `ODG_AUTH_DISABLED=false` and provide a JSON object in `ODG_API_KEYS_JSON`.

```json
{
  "replace-with-secret-value": {
    "subject": "connector-service",
    "role": "connector-operator"
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

Keep key material in an approved secret manager. Never store real keys in configuration examples, source files, logs, or screenshots.

## OIDC boundary

`ODG_OIDC_ISSUER` and `ODG_OIDC_AUDIENCE` describe the intended identity provider and audience. v1.1 exposes this configuration but does not perform provider-specific JWT validation. A shared deployment must use a validating identity-aware gateway until application validation is added.
