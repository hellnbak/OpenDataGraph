import json
import logging
import sys
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .config import settings


REQUESTS = Counter(
    "odg_http_requests_total",
    "HTTP requests handled by OpenDataGraph",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "odg_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
)
JOBS = Counter(
    "odg_background_jobs_total",
    "Background job outcomes",
    ["job_type", "status"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status_code", "duration_ms", "job_id", "job_type"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def configure_observability(app: FastAPI) -> None:
    configure_logging()

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            _record_request(request, 500, started, request_id)
            raise
        response.headers["X-Request-ID"] = request_id
        _record_request(request, response.status_code, started, request_id)
        return response

    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        def metrics():
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    if settings.otel_exporter_otlp_endpoint:
        _configure_tracing(app)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)


def _record_request(request: Request, status_code: int, started: float, request_id: str) -> None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    duration = time.perf_counter() - started
    REQUESTS.labels(request.method, route_path, str(status_code)).inc()
    LATENCY.labels(request.method, route_path).observe(duration)
    logging.getLogger("opendatagraph.request").info(
        "request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": route_path,
            "status_code": status_code,
            "duration_ms": round(duration * 1000, 2),
        },
    )


def _configure_tracing(app: FastAPI) -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")
    if not endpoint.endswith("/v1/traces"):
        endpoint = f"{endpoint}/v1/traces"
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": settings.version,
                "deployment.environment.name": settings.environment,
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/ready,/metrics")
