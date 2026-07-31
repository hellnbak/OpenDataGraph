# Background Jobs

OpenDataGraph v1.3 stores durable jobs in the primary database and executes them with `python -m app.worker`.

## Supported jobs

- `connector.scan`
- `catalog.reindex`
- `evidence.retention`
- `integration.deliver`

Submit connector work through:

```text
POST /api/v1/connectors/{connector_type}/jobs
```

Supported queued connector types are `aws-s3`, `google-drive`, `github`, `gitlab`, and `sharepoint`.

Workers also claim due connector schedules before selecting the next pending job. See [Scheduling and provider budgets](SCHEDULING_AND_RATE_LIMITS.md).

## Credentials

Job payloads reject inline token, password, authorization, credential, and secret fields. Use `env:VARIABLE_NAME` or `file:/run/secrets/name`.

The file must be within `ODG_SECRET_FILE_ROOTS`. The worker resolves the value only when the job executes. AWS S3 uses the standard boto3 credential chain and does not require `secret_ref`.

## Lifecycle

Jobs move through `pending`, `running`, `completed`, `failed`, or `cancelled`. Failed jobs retry with bounded exponential backoff until `max_attempts`. Worker startup recovers claims older than `ODG_WORKER_CLAIM_TIMEOUT_SECONDS`.

Cancellation is cooperative. A pending job cancels immediately; a running connector page or webhook request completes before final state is observed. Provider-budget exhaustion returns a connector job to pending until its shared window resets.

## APIs

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/jobs/{job_id}/retry`

All job operations are tenant-scoped. Connector operators can control connector jobs; catalog reindex, retention, and integration control should be limited to administrators. PostgreSQL is recommended for multiple workers and managed schedules.
