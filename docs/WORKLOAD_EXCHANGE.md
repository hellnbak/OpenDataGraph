# Cloud Workload Identity Exchange

OpenDataGraph v1.8 exchanges mounted or environment-referenced subject tokens for temporary AWS, Azure, or Google Cloud credentials. It does not persist subject tokens, access tokens, session keys, or returned credentials.

This outbound exchange is separate from inbound workload authentication described in [Workload Identity Federation](WORKLOAD_IDENTITY.md).

## Profiles

Configure `ODG_WORKLOAD_EXCHANGE_PROFILES_JSON` through approved runtime secret management. Every profile requires `provider`, `subject_token_ref`, `audience`, and a maximum lifetime no greater than 3600 seconds.

AWS example:

```json
{
  "aws-export": {
    "provider": "aws",
    "subject_token_ref": "file:/run/secrets/opendatagraph/aws/token",
    "audience": "sts.amazonaws.com",
    "role_arn": "arn:aws:iam::111122223333:role/opendatagraph-export",
    "region": "us-west-2",
    "max_token_seconds": 900
  }
}
```

Azure profiles add `tenant_id`, `client_id`, and optional `scope`. Google Cloud profiles use the workload identity provider resource as `audience` and may override the Cloud Platform scope.

Subject tokens must use `env:` or `file:` references. File references must remain under `ODG_SECRET_FILE_ROOTS`. Kubernetes deployments can project multiple audience-specific service-account tokens with the Helm `workloadIdentityTokens` list. Use a distinct mount directory and DNS-label-compatible name for each token.

## Exchange behavior

- AWS uses `AssumeRoleWithWebIdentity` and enforces a 900- to 3600-second requested session.
- Azure uses the federated client assertion flow against the configured tenant.
- Google Cloud uses RFC 8693 token exchange at the fixed Google STS endpoint.
- HTTP exchanges reject redirects and use `ODG_WORKLOAD_EXCHANGE_HTTP_TIMEOUT_SECONDS`.
- Returned credential expiry is checked against the profile maximum with a small clock-skew allowance.

Administrators can execute a profile test:

```text
POST /api/v1/workload-identity/exchange-profiles/{profile_name}/test
```

Auditors can list non-secret profile metadata at `GET /api/v1/workload-identity/exchange-profiles`. Test responses report provider, subject when supplied by the provider, and expiry but never return credentials.

## Consumers

Named profiles can supply:

- AWS S3 graph export sinks through `ODG_GRAPH_EXPORT_S3_EXCHANGE_PROFILE`;
- Google Cloud Storage sinks through `ODG_GRAPH_EXPORT_GCS_EXCHANGE_PROFILE`;
- Azure Blob sinks through `ODG_GRAPH_EXPORT_AZURE_EXCHANGE_PROFILE`;
- AWS KMS evidence signing through a signing profile's `workload_exchange_profile`.

Use one role, audience, and least-privilege destination scope per purpose. Isolate worker egress to cloud identity and approved storage endpoints, and alert on exchange failures without logging response bodies.
