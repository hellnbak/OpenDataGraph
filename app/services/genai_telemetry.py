import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AIAgent, AIResource, GenAITelemetryEvent
from app.observability import GENAI_TELEMETRY
from app.services.ai_resources import create_ai_resource, observe_relationship
from app.services.evidence_signing import canonical_json
from app.services.outbox import queue_outbox_event


MAX_OTLP_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_OTLP_SPANS = 5000
CONTENT_ATTRIBUTE_PREFIXES = (
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "llm.prompts",
    "llm.completions",
)


def ingest_otlp_genai(
    db: Session,
    tenant_id: str,
    payload: dict,
    recorded_by: str,
) -> dict:
    encoded = json.dumps(payload, separators=(",", ":")).encode()
    if len(encoded) > MAX_OTLP_PAYLOAD_BYTES:
        raise ValueError("OTLP request exceeds 2 MiB")
    spans = list(_spans(payload))
    batch_limit = min(max(1, settings.genai_telemetry_batch_max), MAX_OTLP_SPANS)
    if len(spans) > batch_limit:
        raise ValueError(f"OTLP request exceeds the configured limit of {batch_limit} spans")

    imported = duplicate = ignored = discovered = relationships = 0
    imported_event_ids = []
    content_discarded = 0
    for resource_attributes, scope_attributes, span in spans:
        attributes = {**resource_attributes, **scope_attributes, **_attributes(span.get("attributes", []))}
        if not _is_genai_span(attributes):
            ignored += 1
            continue
        trace_id = _bounded_text(span.get("traceId"), 64)
        span_id = _bounded_text(span.get("spanId"), 64)
        if not trace_id or not span_id:
            ignored += 1
            continue
        event_id = f"otel:{trace_id}:{span_id}"
        existing = db.scalar(
            select(GenAITelemetryEvent).where(
                GenAITelemetryEvent.tenant_id == tenant_id,
                GenAITelemetryEvent.event_id == event_id,
            )
        )
        if existing:
            duplicate += 1
            continue

        metadata, discarded = _metadata_attributes(attributes)
        provider = _first_text(
            attributes,
            "gen_ai.provider.name",
            "gen_ai.system",
        )
        model = _first_text(
            attributes,
            "gen_ai.response.model",
            "gen_ai.request.model",
        )
        agent_key = _first_text(
            attributes,
            "opendatagraph.agent.key",
            "gen_ai.agent.id",
            "gen_ai.agent.name",
        )
        occurred_at = _span_time(span)
        event = GenAITelemetryEvent(
            tenant_id=tenant_id,
            event_id=event_id,
            trace_id=trace_id,
            span_id=span_id,
            operation=_first_text(attributes, "gen_ai.operation.name") or _bounded_text(span.get("name"), 160),
            provider=provider,
            model=model,
            agent_key=agent_key,
            input_tokens=_nonnegative_int(attributes.get("gen_ai.usage.input_tokens")),
            output_tokens=_nonnegative_int(attributes.get("gen_ai.usage.output_tokens")),
            duration_ms=_duration_ms(span),
            finish_reasons_json=json.dumps(_finish_reasons(attributes), separators=(",", ":")),
            attributes_sha256=hashlib.sha256(canonical_json(metadata)).hexdigest(),
            content_discarded=discarded,
            occurred_at=occurred_at,
        )
        db.add(event)
        imported += 1
        imported_event_ids.append(event_id)
        content_discarded += int(discarded)

        resource = None
        if model:
            resource, was_discovered = _discover_model(db, tenant_id, provider, model, recorded_by)
            discovered += int(was_discovered)
        if resource and agent_key and _known_agent(db, tenant_id, agent_key):
            _observation, _relationship, idempotent = observe_relationship(
                db,
                tenant_id,
                event_id,
                {"type": "agent", "id": agent_key},
                "invokes",
                {"type": "model", "id": resource.resource_key},
                occurred_at,
                {"source": "opentelemetry", "provider": provider},
                recorded_by,
                commit=False,
            )
            relationships += int(not idempotent)

    if imported:
        digest = hashlib.sha256(
            canonical_json(
                {
                    "tenant_id": tenant_id,
                    "event_ids": sorted(imported_event_ids),
                }
            )
        ).hexdigest()
        queue_outbox_event(
            db,
            tenant_id,
            aggregate_type="telemetry-batch",
            aggregate_id=digest,
            event_type="telemetry.genai.observed",
            payload={
                "batch_sha256": digest,
                "imported": imported,
                "duplicates": duplicate,
                "ignored": ignored,
                "models_discovered": discovered,
                "relationships_observed": relationships,
                "content_discarded": content_discarded,
            },
            idempotency_key=f"genai-telemetry:{digest}",
        )
    db.commit()
    for result, count in (
        ("imported", imported),
        ("duplicate", duplicate),
        ("ignored", ignored),
        ("content_discarded", content_discarded),
    ):
        if count:
            GENAI_TELEMETRY.labels(result).inc(count)
    return {
        "accepted": True,
        "imported": imported,
        "duplicates": duplicate,
        "ignored": ignored,
        "models_discovered": discovered,
        "relationships_observed": relationships,
        "content_discarded": content_discarded,
    }


def telemetry_response(event: GenAITelemetryEvent) -> dict:
    return {
        "event_id": event.event_id,
        "trace_id": event.trace_id,
        "span_id": event.span_id,
        "operation": event.operation,
        "provider": event.provider,
        "model": event.model,
        "agent_key": event.agent_key,
        "input_tokens": event.input_tokens,
        "output_tokens": event.output_tokens,
        "duration_ms": event.duration_ms,
        "finish_reasons": json.loads(event.finish_reasons_json or "[]"),
        "attributes_sha256": event.attributes_sha256,
        "content_discarded": event.content_discarded,
        "occurred_at": event.occurred_at,
        "created_at": event.created_at,
    }


def _spans(payload: dict):
    resource_spans = payload.get("resourceSpans", [])
    if not isinstance(resource_spans, list):
        raise ValueError("OTLP resourceSpans must be an array")
    for resource_span in resource_spans:
        if not isinstance(resource_span, dict):
            continue
        resource = resource_span.get("resource", {})
        resource_attributes = _attributes(resource.get("attributes", []) if isinstance(resource, dict) else [])
        scope_spans = resource_span.get("scopeSpans", resource_span.get("instrumentationLibrarySpans", []))
        if not isinstance(scope_spans, list):
            continue
        for scope_span in scope_spans:
            if not isinstance(scope_span, dict):
                continue
            scope = scope_span.get("scope", {})
            scope_attributes = _attributes(scope.get("attributes", []) if isinstance(scope, dict) else [])
            spans = scope_span.get("spans", [])
            if not isinstance(spans, list):
                continue
            for span in spans:
                if isinstance(span, dict):
                    yield resource_attributes, scope_attributes, span


def _attributes(values: list) -> dict:
    result = {}
    if not isinstance(values, list):
        return result
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        result[item["key"]] = _any_value(item.get("value"))
    return result


def _any_value(value):
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    if "arrayValue" in value and isinstance(value["arrayValue"], dict):
        return [_any_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value and isinstance(value["kvlistValue"], dict):
        return _attributes(value["kvlistValue"].get("values", []))
    return None


def _is_genai_span(attributes: dict) -> bool:
    return any(key.startswith("gen_ai.") for key in attributes)


def _metadata_attributes(attributes: dict) -> tuple[dict, bool]:
    metadata = {}
    discarded = False
    for key, value in attributes.items():
        if key.startswith(CONTENT_ATTRIBUTE_PREFIXES):
            discarded = True
            continue
        if key.startswith("gen_ai.") or key.startswith("opendatagraph.") or key in {
            "service.name",
            "deployment.environment.name",
            "cloud.region",
        }:
            metadata[key[:160]] = _bounded_value(value)
    return metadata, discarded


def _bounded_value(value):
    if isinstance(value, str):
        return value[:1024]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_bounded_value(item) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key)[:160]: _bounded_value(item) for key, item in list(value.items())[:50]}
    return str(value)[:1024]


def _first_text(attributes: dict, *keys: str) -> str:
    for key in keys:
        value = attributes.get(key)
        if value is not None:
            return _bounded_text(value, 320)
    return ""


def _bounded_text(value, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _nonnegative_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _finish_reasons(attributes: dict) -> list[str]:
    value = attributes.get("gen_ai.response.finish_reasons", [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_bounded_text(item, 80) for item in value[:20] if _bounded_text(item, 80)]


def _span_time(span: dict) -> datetime:
    try:
        nanoseconds = int(span.get("startTimeUnixNano", 0))
    except (TypeError, ValueError):
        nanoseconds = 0
    if nanoseconds <= 0:
        return datetime.now(UTC).replace(tzinfo=None)
    return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=UTC).replace(tzinfo=None)


def _duration_ms(span: dict) -> float:
    try:
        start = int(span.get("startTimeUnixNano", 0))
        end = int(span.get("endTimeUnixNano", 0))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (end - start) / 1_000_000) if end >= start else 0.0


def _resource_key(provider: str, model: str) -> str:
    raw = f"otel-model:{provider or 'unknown'}:{model}"
    if len(raw) <= 320:
        return raw
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"otel-model:{digest}"


def _discover_model(
    db: Session,
    tenant_id: str,
    provider: str,
    model: str,
    recorded_by: str,
) -> tuple[AIResource, bool]:
    resource_key = _resource_key(provider, model)
    existing = db.scalar(
        select(AIResource).where(
            AIResource.tenant_id == tenant_id,
            AIResource.resource_key == resource_key,
        )
    )
    if existing:
        return existing, False
    resource = create_ai_resource(
        db,
        tenant_id,
        {
            "resource_key": resource_key,
            "resource_type": "model",
            "name": model[:240],
            "owner": "unassigned",
            "provider": provider[:160],
            "region": "",
            "status": "review",
            "risk_tier": "high",
            "metadata": {"discovered_by": "opentelemetry"},
        },
        recorded_by,
        commit=False,
    )
    return resource, True


def _known_agent(db: Session, tenant_id: str, agent_key: str) -> bool:
    return db.scalar(
        select(AIAgent.id).where(
            AIAgent.tenant_id == tenant_id,
            AIAgent.key == agent_key,
        )
    ) is not None
