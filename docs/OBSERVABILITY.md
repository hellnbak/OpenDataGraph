# Observability

OpenDataGraph v1.9 exposes health, readiness, metrics, structured logs, delivery and outbox state, governance SLA, framework coverage, posture and ownership trend analytics, lifecycle reporting, runtime authorization telemetry, and optional trace export.

## Endpoints

- `/health` verifies the process and database connection.
- `/ready` verifies the database, evidence backend, and required search backend.
- `/metrics` exposes Prometheus text metrics when `ODG_METRICS_ENABLED=true`.

Restrict `/metrics` at the network layer in shared deployments.

Runtime metrics include `odg_runtime_authorization_decisions_total{mode,policy_decision,decision}`, `odg_runtime_authorization_evaluation_seconds`, `odg_runtime_enforcement_events_total{outcome}`, `odg_policy_rollout_events_total{event,stage}`, `odg_genai_telemetry_spans_total{result}`, and `odg_governance_outbox_events_total{outcome}`. HTTP request latency includes receipt and outbox commit time; the policy-evaluation histogram does not.

## Logs

`ODG_LOG_FORMAT=json` emits timestamp, level, logger, message, request ID, route, status, and duration. Request and response bodies, headers, API keys, connector tokens, evidence content, and job secret values are not logged.

Clients may supply `X-Request-ID`; otherwise the API generates one and returns it.

## Tracing

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable OTLP HTTP trace export. `OTEL_SERVICE_NAME` controls the service resource name. Send traces only to an approved TLS-protected collector.

The FastAPI instrumentation excludes health, readiness, and metrics paths. OpenDataGraph does not attach prompts, responses, tool arguments, evidence bytes, or credentials to spans. Inbound GenAI telemetry at `/v1/traces` is separate from application trace export; see [GenAI telemetry](GENAI_TELEMETRY.md).

## Operational dashboards

`GET /api/v1/integrations/dashboard` returns tenant-scoped delivery totals, status counts, success rate, and endpoint summaries. `GET /api/v1/integrations/outbox` exposes governance event dispatch state. `GET /api/v1/telemetry/genai/events` exposes metadata-only model activity. `GET /api/v1/governance/sla` reports review deadlines and resolution time. `GET /api/v1/service-accounts/lifecycle` reports stale accounts, expiry, and rotations. Framework coverage reports expose evidence gaps without compliance claims.

Alert on dead letters, failed or stale outbox claims, permitted receipts missing enforcement evidence, enforcement failures, rollout deny deltas, telemetry rejection and discovery backlogs, overdue governance reviews, repeatedly failed governance or export jobs, stale service accounts, expiring credentials, stalled deprovisioning workflows, growing disposition or remediation queues, and export storage failures.
