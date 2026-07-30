# Deployment

## Docker Compose

```bash
docker compose up --build
```

The stack includes PostgreSQL, OpenSearch, and OpenDataGraph.

Set `ODG_POSTGRES_PASSWORD` in the local environment or an approved secret store before starting the stack.

## Required production controls

- TLS and identity-aware ingress
- `ODG_AUTH_DISABLED=false`
- Role-scoped API keys or an approved OIDC-validating gateway
- Managed PostgreSQL and OpenSearch
- External secret management
- Network restrictions and connector egress controls
- Database backups and tested recovery
- Centralized logs, metrics, and alerts
- Resource limits and health checks

## Environment variables

- `ODG_DATABASE_URL`
- `ODG_AUTO_SEED_DEMO`
- `ODG_CLASSIFICATION_MODE`
- `ODG_CLASSIFICATION_REVIEW_THRESHOLD`
- `ODG_AUTH_DISABLED`
- `ODG_API_KEYS_JSON`
- `ODG_OIDC_ISSUER`
- `ODG_OIDC_AUDIENCE`
- `ODG_POLICY_DIRECTORY`
- `ODG_OPENSEARCH_URL`

OpenDataGraph v1.1 does not include tenant isolation, background workers, managed migrations, or high-availability manifests. Those controls are planned for v1.2.
