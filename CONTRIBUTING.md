# Contributing

Thank you for helping build an open data intelligence layer for enterprise AI.

1. Describe the problem, expected behavior, security impact, tenant impact, migration impact, and compatibility considerations.
2. Keep changes focused and include deterministic tests for behavior changes.
3. Run tests, Ruff, Python compilation, migration validation, and affected deployment checks before submitting a change.
4. Never include credentials, real customer data, proprietary schemas, access tokens, databases, evidence objects, or copied vendor code.
5. Connector changes must document permissions, pagination, rate limits, cursor semantics, timestamps, public-access interpretation, imported and updated counts, and whether content is retrieved.
6. Policy changes must include matching and non-matching tests and explain new controls.
7. Schema changes require an Alembic migration that works with PostgreSQL and SQLite.
8. Tenant-aware models and endpoints must filter every lookup, list, mutation, idempotency check, and relationship.

Lifecycle findings remain advisory until an explicitly authorized workflow performs an external action.

## Contribution terms

OpenDataGraph v1.7.0 is distributed under `FSL-1.1-ALv2`. By submitting a contribution, you represent that you have the right to provide it and agree that it may be distributed under the project license.

The project does not yet include a contributor license agreement. External code contributions must not be merged until contribution terms supporting both the source-available project and potential commercial licensing have been reviewed and documented. This protects contributors, users, and the licensor from ambiguous rights.
