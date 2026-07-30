# Deployment

## Docker Compose

`docker compose up --build` starts PostgreSQL, OpenSearch, and the application.

## Production warning

Phase 1 has no authentication or RBAC. Place it behind an identity-aware reverse proxy, use managed PostgreSQL/OpenSearch, external secret management, TLS, network restrictions, backups, and centralized logging before any shared deployment.

## Environment variables

- `ODG_DATABASE_URL`
- `ODG_AUTO_SEED_DEMO`
- `ODG_CLASSIFICATION_MODE`
- `ODG_OLLAMA_URL`
- `ODG_OLLAMA_MODEL`
- `ODG_OPENSEARCH_URL`
