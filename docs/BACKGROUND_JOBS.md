# Background Jobs

OpenDataGraph v1.9 stores durable jobs and governance outbox state in the primary database and executes them with `python -m app.worker`.

## Supported jobs

- `connector.scan`
- `catalog.reindex`
- `evidence.retention`
- `evidence.disposition`
- `identity.deprovision`
- `integration.deliver`
- `governance.sla-notify`
- `graph.export`
- `ownership.campaign.launch`
- `governance.evidence-package`

Submit connector work through:

```text
POST /api/v1/connectors/{connector_type}/jobs
```

Supported queued connector types are `aws-s3`, `google-drive`, `github`, `gitlab`, `sharepoint`, and `postgresql`.

Workers also claim due interval or cron connector and ownership schedules and due ownership escalation stages before selecting the next pending job. Escalation stages queue ordinary idempotent `integration.deliver` jobs. See [Scheduling and provider budgets](SCHEDULING_AND_RATE_LIMITS.md).

Workers claim pending runtime decision receipts separately from the general job table, sign canonical manifests, recover stale signing claims, retry with bounded backoff, and purge expired completed receipts in bounded batches. This avoids one background-job row per authorization decision and keeps external signer latency outside the request path.

## Credentials

Job payloads reject inline token, password, authorization, credential, and secret fields. Use `env:VARIABLE_NAME` or `file:/run/secrets/name`.

The file must be within `ODG_SECRET_FILE_ROOTS`. The worker resolves the value only when the job executes. AWS S3 uses the standard boto3 credential chain by default and can instead use a named temporary workload exchange profile.

## Lifecycle

Jobs move through `pending`, `running`, `completed`, `failed`, or `cancelled`. Failed jobs retry with bounded exponential backoff until `max_attempts`. Worker startup recovers claims older than `ODG_WORKER_CLAIM_TIMEOUT_SECONDS`.

Cancellation is cooperative. A pending job cancels immediately; a running connector page, webhook request, governance notification batch, campaign launch, package generation, or graph serialization completes before final state is observed. Provider-budget exhaustion returns a connector job to pending until its shared window resets. Integration delivery that exhausts attempts becomes a dead letter. Evidence disposition, identity deprovisioning, governance review and package, ownership, and graph export records keep durable domain state separate from job state.

Governance notification payloads contain only a bounded limit. Graph export and governance package payloads contain only a tenant-scoped record identifier. Ownership launch payloads contain only the schedule identifier and stable occurrence timestamp. Configuration, filters, sinks, and bounds are persisted on tenant-scoped domain records.

## APIs

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/jobs/{job_id}/retry`

All job operations are tenant-scoped. Connector operators can control connector jobs; catalog reindex, retention, disposition, identity, and integration control is limited to administrators. PostgreSQL is recommended for multiple workers and managed schedules.
