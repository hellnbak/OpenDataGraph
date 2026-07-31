# Background Jobs

OpenDataGraph v1.2 stores durable jobs in the primary database and executes them with `python -m app.worker`.

## Supported jobs

- `connector.scan`
- `catalog.reindex`

Submit connector work through:

```text
POST /api/v1/connectors/{connector_type}/jobs
```

Supported queued connector types are `aws-s3`, `google-drive`, `github`, `gitlab`, and `sharepoint`.

## Credentials

Job payloads reject inline token, password, authorization, credential, and secret fields. Use `env:VARIABLE_NAME` or `file:/run/secrets/name`.

The file must be within `ODG_SECRET_FILE_ROOTS`. The worker resolves the value only when the job executes. AWS S3 uses the standard boto3 credential chain and does not require `secret_ref`.

## Lifecycle

Jobs move through `pending`, `running`, `completed`, `failed`, or `cancelled`. Failed jobs retry with bounded exponential backoff until `max_attempts`. Worker startup recovers claims older than `ODG_WORKER_CLAIM_TIMEOUT_SECONDS`.

Cancellation is cooperative. A pending job cancels immediately; a running connector page completes before final state is observed.

## APIs

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/jobs/{job_id}/retry`

All job operations are tenant-scoped. Connector operators can control connector jobs; catalog reindex cancellation and retry require an administrator. PostgreSQL is recommended for multiple workers.
