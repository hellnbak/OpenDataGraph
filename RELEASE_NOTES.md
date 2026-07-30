# OpenDataGraph v1.0.0-RC1 — Phase 1

This release candidate consolidates the first complete, runnable OpenDataGraph foundation.

## Included

- FastAPI application and dashboard
- PostgreSQL and SQLite support
- OpenSearch development service
- Enterprise synthetic demo generator
- Explainable classification and lifecycle scoring
- AI agent registry
- Audited policy decision engine
- AWS S3 and Google Drive metadata connectors
- MCP server
- Docker Compose
- Test suite and CI
- GitHub community and security documentation

## Known limitations

- OpenSearch is deployed for integration testing but PostgreSQL remains the authoritative catalog and current API query backend.
- Connectors are metadata-first and do not perform deep content inspection.
- Google Drive relies on administrator-provided service-account configuration.
- Authentication and RBAC are not included in Phase 1; do not expose the service directly to the public internet.
- Schema migrations are not yet managed by Alembic.
- Policy logic is intentionally understandable and deterministic; it is not a replacement for legal or compliance review.
