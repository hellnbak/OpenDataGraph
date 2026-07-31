# API Guide

Interactive OpenAPI documentation is available at `/docs`.

## Operations

- `GET /health`
- `GET /ready`
- `GET /metrics`

Health and readiness do not expose tenant counts. Restrict metrics at the network layer.

## Catalog and summary

- `GET /api/v1/assets`
- `GET /api/v1/assets/{id}`
- `GET /api/v1/summary`
- `POST /api/v1/search/reindex`

The `search` parameter uses OpenSearch when configured and database fallback otherwise.

## Agents and policy

- `GET|POST /api/v1/agents`
- `POST /api/v1/policy/evaluate`
- `POST /api/v1/policy/simulate`
- `GET /api/v1/policy/audit`

## Connectors and jobs

- `POST /api/v1/connectors/s3/scan`
- `POST /api/v1/connectors/google-drive/scan`
- `POST /api/v1/connectors/{connector_type}/scan`
- `POST /api/v1/connectors/{connector_type}/jobs`
- `GET /api/v1/connectors/runs`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/jobs/{job_id}/retry`

Synchronous dynamic connector types are `github`, `gitlab`, and `sharepoint`. Queued types also include `aws-s3` and `google-drive`.

## Classification review

- `GET /api/v1/classification/reviews`
- `POST /api/v1/classification/reviews/{review_id}`

## AI activity and relationships

- `POST /api/v1/ai-usage/events`
- `GET /api/v1/ai-usage/events`
- `GET /api/v1/graph/relationships`

## Evidence

- `POST /api/v1/evidence`
- `GET /api/v1/evidence`
- `GET /api/v1/evidence/{evidence_id}/download`

## Authentication

- `GET /api/v1/auth/configuration`

When authentication is enabled, send the key in `X-API-Key`. The key determines role and tenant. Data-bearing APIs never accept tenant selection from the request.
