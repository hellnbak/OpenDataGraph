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
- `POST|GET /api/v1/policy/bundles`
- `POST /api/v1/policy/bundles/{bundle_id}/submit`
- `POST /api/v1/policy/bundles/{bundle_id}/approve`
- `POST /api/v1/policy/bundles/{bundle_id}/activate`
- `POST /api/v1/policy/bundles/{bundle_id}/rollback`
- `GET /api/v1/policy/bundles/{bundle_id}/diff`
- `POST|GET /api/v1/policy/approver-delegations`
- `DELETE /api/v1/policy/approver-delegations/{delegation_id}`
- `POST|GET /api/v1/policy/exceptions`
- `DELETE /api/v1/policy/exceptions/{exception_id}`
- `POST /api/v1/policy/exceptions/{exception_id}/renewal`
- `POST /api/v1/policy/exceptions/{exception_id}/renewal/approve`

## Connectors and jobs

- `POST /api/v1/connectors/s3/scan`
- `POST /api/v1/connectors/google-drive/scan`
- `POST /api/v1/connectors/{connector_type}/scan`
- `POST /api/v1/connectors/{connector_type}/jobs`
- `GET /api/v1/connectors/runs`
- `POST|GET /api/v1/connectors/schedules`
- `PATCH|DELETE /api/v1/connectors/schedules/{schedule_id}`
- `GET /api/v1/connectors/rate-limits`
- `PUT /api/v1/connectors/rate-limits/{provider}`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/jobs/{job_id}/retry`

Synchronous dynamic connector types are `github`, `gitlab`, and `sharepoint`. Queued and scheduled types also include `aws-s3`, `google-drive`, and metadata-only `postgresql` catalog scans.

## Classification review

- `GET /api/v1/classification/reviews`
- `POST /api/v1/classification/reviews/{review_id}`

## AI activity and relationships

- `POST /api/v1/ai-usage/events`
- `GET /api/v1/ai-usage/events`
- `GET /api/v1/graph/relationships`
- `POST /api/v1/lineage/events`
- `GET /api/v1/graph/query`
- `GET /api/v1/graph/paths`
- `GET /api/v1/graph/export`
- `POST|GET /api/v1/graph/exports`
- `GET /api/v1/graph/exports/{export_id}`
- `GET /api/v1/graph/exports/{export_id}/download`
- `GET /api/v1/graph/export-sinks`

## Evidence

- `POST /api/v1/evidence`
- `GET /api/v1/evidence`
- `GET /api/v1/evidence/{evidence_id}/download`
- `PATCH /api/v1/evidence/{evidence_id}/governance`
- `DELETE /api/v1/evidence/{evidence_id}`
- `POST /api/v1/evidence/retention/jobs`
- `POST /api/v1/evidence/{evidence_id}/verify-object-lock`
- `POST /api/v1/evidence/{evidence_id}/dispositions`
- `GET /api/v1/evidence/dispositions`
- `POST /api/v1/evidence/dispositions/{disposition_id}/approve`
- `POST /api/v1/evidence/dispositions/{disposition_id}/reject`

## Integrations

- `POST|GET /api/v1/integrations`
- `DELETE /api/v1/integrations/{endpoint_id}`
- `POST /api/v1/integrations/{endpoint_id}/test`
- `GET /api/v1/integrations/deliveries`
- `GET /api/v1/integrations/dashboard`
- `POST /api/v1/integrations/deliveries/{delivery_id}/replay`

Endpoints choose `native`, `cloudevents`, `cef`, or `splunk-hec` event format. Existing endpoints default to `native`.

## Service accounts

- `POST|GET /api/v1/service-accounts`
- `GET /api/v1/service-accounts/lifecycle`
- `GET /api/v1/service-accounts/{account_id}`
- `POST /api/v1/service-accounts/{account_id}/rotate`
- `POST /api/v1/service-accounts/rotations/{rotation_id}/complete`
- `DELETE /api/v1/service-accounts/{account_id}`

Creation and rotation return a clear credential exactly once. Read responses never expose credential salts or verifiers.

## Governance and ownership

- `GET /api/v1/governance/reviews`
- `PATCH /api/v1/governance/reviews/{task_id}/assign`
- `GET /api/v1/governance/sla`
- `POST /api/v1/governance/notifications/jobs`
- `GET /api/v1/governance/analytics`
- `POST|GET /api/v1/governance/evidence-packages`
- `GET /api/v1/governance/evidence-packages/{package_id}`
- `GET /api/v1/governance/evidence-packages/{package_id}/download`
- `POST|GET /api/v1/ownership/campaigns`
- `GET /api/v1/ownership/campaigns/{campaign_id}`
- `POST /api/v1/ownership/campaigns/{campaign_id}/launch`
- `GET /api/v1/ownership/campaigns/{campaign_id}/assignments`
- `POST /api/v1/ownership/assignments/{assignment_id}/attest`
- `PATCH /api/v1/ownership/assignments/{assignment_id}/remediation`
- `POST /api/v1/ownership/assignments/{assignment_id}/resolve`
- `POST|GET /api/v1/ownership/schedules`
- `PATCH|DELETE /api/v1/ownership/schedules/{schedule_id}`

## Authentication

- `GET /api/v1/auth/configuration`

When authentication is enabled, send a tenant-bound key in `X-API-Key`, a service-account credential in `X-Service-Account-Key`, a signed human bearer token from a configured OIDC provider, or a short-lived signed token in `X-Workload-Identity-Token`. Workload providers fix the tenant and role. Data-bearing APIs never accept tenant selection from the request.

SCIM provisioning uses dedicated `/scim/v2/Users`, `/scim/v2/Groups`, and `/scim/v2/Bulk` endpoints with a separate tenant-bound bearer token. It never accepts a tenant header. Auditors inspect durable user offboarding through `GET /api/v1/identity/deprovisioning`.
