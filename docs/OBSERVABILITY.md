# Observability

OpenDataGraph v1.3 exposes health, readiness, metrics, structured logs, and optional traces.

## Endpoints

- `/health` verifies the process and database connection.
- `/ready` verifies the database, evidence backend, and required search backend.
- `/metrics` exposes Prometheus text metrics when `ODG_METRICS_ENABLED=true`.

Restrict `/metrics` at the network layer in shared deployments.

## Logs

`ODG_LOG_FORMAT=json` emits timestamp, level, logger, message, request ID, route, status, and duration. Request and response bodies, headers, API keys, connector tokens, evidence content, and job secret values are not logged.

Clients may supply `X-Request-ID`; otherwise the API generates one and returns it.

## Tracing

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable OTLP HTTP trace export. `OTEL_SERVICE_NAME` controls the service resource name. Send traces only to an approved TLS-protected collector.

The FastAPI instrumentation excludes health, readiness, and metrics paths. OpenDataGraph does not attach prompts, responses, tool arguments, evidence bytes, or credentials to spans.
