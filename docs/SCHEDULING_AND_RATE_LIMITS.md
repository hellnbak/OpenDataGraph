# Scheduling and Provider Budgets

OpenDataGraph v1.9 runs tenant-scoped connector scans and ownership campaigns on fixed intervals or five-field cron calendars. Workers atomically claim due schedules and enqueue reference-only `connector.scan` or `ownership.campaign.launch` jobs, then claim due ownership escalation stages and governance outbox events with idempotent integration delivery.

## Schedule types

`POST /api/v1/connectors/schedules` accepts:

- `schedule_type=interval` with `interval_seconds` from 60 seconds through 7 days
- `schedule_type=cron` with `cron_expression` and an IANA `timezone`
- optional recurring `maintenance_windows`
- the existing connector account, cursor, limits, endpoint options, and `secret_ref`

Cron fields are minute, hour, day of month, month, and day of week. Numeric values, lists, ranges, and steps are supported. Named months and weekdays are rejected. Cron Sunday is `0` or `7`; maintenance-window weekdays use Monday `0` through Sunday `6`.

Run times are persisted as UTC. Time-zone conversion occurs when the next cron occurrence is calculated.

## Maintenance windows

Each window contains `days`, `start`, and `end`:

```json
{
  "days": [5, 6],
  "start": "00:00",
  "end": "06:00"
}
```

Windows use the schedule time zone and may cross midnight. Eligible cron occurrences and interval runs skip active windows. At most 20 windows are accepted, and a window cannot cover an entire day with equal start and end values.

## Worker behavior

Each worker checks due schedules before claiming a background job. Database compare-and-update claiming prevents duplicate enqueue by concurrent workers. The next eligible run is persisted before the connector job is created.

Connector schedule payloads retain only secret references. Provider credentials are resolved by the worker at execution time. Ownership schedules contain bounded scope, due days, asset limits, and optional enabled integration endpoint identifiers. Their occurrence timestamp provides idempotent launch retries.

## Provider budgets

Administrators configure tenant/provider request windows through:

- `GET /api/v1/connectors/rate-limits`
- `PUT /api/v1/connectors/rate-limits/{provider}`

Ownership schedule APIs are:

- `POST|GET /api/v1/ownership/schedules`
- `PATCH|DELETE /api/v1/ownership/schedules/{schedule_id}`

Every provider request from synchronous scans or workers consumes the same database-backed budget. Exhaustion returns synchronous requests as `429` with `Retry-After`; jobs return to pending until the current provider window resets.

PostgreSQL is recommended for concurrent workers and schedules.
