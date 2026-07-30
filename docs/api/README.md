# API Guide

Interactive OpenAPI documentation is available at `/docs`.

## Catalog and summary

- `GET /api/v1/assets`
- `GET /api/v1/assets/{id}`
- `GET /api/v1/summary`

## Agents and policy

- `GET|POST /api/v1/agents`
- `POST /api/v1/policy/evaluate`
- `POST /api/v1/policy/simulate`
- `GET /api/v1/policy/audit`

## Connectors

- `POST /api/v1/connectors/s3/scan`
- `POST /api/v1/connectors/google-drive/scan`
- `POST /api/v1/connectors/{connector_type}/scan`
- `GET /api/v1/connectors/runs`

Dynamic connector types are `github`, `gitlab`, and `sharepoint`.

## Classification review

- `GET /api/v1/classification/reviews`
- `POST /api/v1/classification/reviews/{review_id}`

## AI activity and relationships

- `POST /api/v1/ai-usage/events`
- `GET /api/v1/ai-usage/events`
- `GET /api/v1/graph/relationships`

## Authentication

- `GET /api/v1/auth/configuration`

When authentication is enabled, send the API key in `X-API-Key`. Mutation and audit endpoints enforce the role levels described in [Authentication](../AUTHENTICATION.md).
