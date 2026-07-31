# Scheduling and Provider Budgets

OpenDataGraph v1.3 manages recurring connector ingestion through durable interval schedules.

## Schedules

Schedules store tenant, connector type, account, fixed interval, next run time, non-secret connector configuration, and an `env:` or `file:` secret reference. Workers atomically advance due schedules before creating `connector.scan` jobs, preventing duplicate enqueue across worker replicas.

Intervals range from 60 seconds to seven days. Pause a schedule before rotating its secret reference or changing provider scope.

APIs:

- `POST /api/v1/connectors/schedules`
- `GET /api/v1/connectors/schedules`
- `PATCH /api/v1/connectors/schedules/{schedule_id}`
- `DELETE /api/v1/connectors/schedules/{schedule_id}`

## Provider budgets

Administrators configure a maximum number of provider requests in a time window:

- `PUT /api/v1/connectors/rate-limits/{provider}`
- `GET /api/v1/connectors/rate-limits`

Budgets are tenant and provider scoped but shared by all schedules, synchronous scans, jobs, and worker replicas in that tenant. Each provider API call consumes one unit. Exhausted jobs return to `pending` until the window resets; synchronous requests receive `429` and `Retry-After`.

Provider budgets supplement, rather than replace, provider response headers and backoff requirements.
