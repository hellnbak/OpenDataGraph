import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BackgroundJob, IntegrationDelivery, IntegrationEndpoint, utc_now
from app.services.connectors import safe_connector_error
from connectors.security import validate_https_url


INTEGRATION_EVENT_FORMATS = {"native", "cloudevents", "cef", "splunk-hec"}
MAX_INTEGRATION_PAYLOAD_BYTES = 256 * 1024


def create_endpoint(
    db: Session,
    tenant_id: str,
    name: str,
    mode: str,
    url: str,
    secret_ref: str | None,
    events: list[str],
    enabled: bool,
    created_by: str,
    event_format: str = "native",
) -> IntegrationEndpoint:
    if not settings.integration_allowed_hosts:
        raise ValueError("ODG_INTEGRATION_ALLOWED_HOSTS must be configured")
    if event_format not in INTEGRATION_EVENT_FORMATS:
        raise ValueError("Unsupported integration event format")
    validated_url = validate_https_url(url, settings.integration_allowed_hosts)
    endpoint = IntegrationEndpoint(
        tenant_id=tenant_id,
        endpoint_id=str(uuid4()),
        name=name,
        mode=mode,
        event_format=event_format,
        url=validated_url,
        secret_ref=secret_ref,
        events_json=json.dumps(sorted(set(events))),
        enabled=enabled,
        created_by=created_by,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return endpoint


def queue_integration_event(
    db: Session,
    tenant_id: str,
    event_type: str,
    payload: dict,
    created_by: str,
    endpoint_ids: set[str] | None = None,
) -> list[IntegrationDelivery]:
    from app.services.jobs import enqueue_job

    payload_json = _serialize_payload(payload)
    endpoints = list(
        db.scalars(
            select(IntegrationEndpoint).where(
                IntegrationEndpoint.tenant_id == tenant_id,
                IntegrationEndpoint.enabled.is_(True),
            )
        ).all()
    )
    deliveries = []
    for endpoint in endpoints:
        if endpoint_ids is not None and endpoint.endpoint_id not in endpoint_ids:
            continue
        events = json.loads(endpoint.events_json or "[]")
        if endpoint_ids is None and "*" not in events and event_type not in events:
            continue
        delivery = IntegrationDelivery(
            tenant_id=tenant_id,
            delivery_id=str(uuid4()),
            endpoint_id=endpoint.endpoint_id,
            event_type=event_type,
            payload_json=payload_json,
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        enqueue_job(
            db,
            tenant_id=tenant_id,
            job_type="integration.deliver",
            payload={"delivery_id": delivery.delivery_id},
            created_by=created_by,
            max_attempts=5,
        )
        deliveries.append(delivery)
    return deliveries


def deliver_integration(db: Session, tenant_id: str, delivery_id: str) -> dict:
    import httpx

    from app.services.jobs import resolve_secret

    delivery = db.scalar(
        select(IntegrationDelivery).where(
            IntegrationDelivery.tenant_id == tenant_id,
            IntegrationDelivery.delivery_id == delivery_id,
        )
    )
    if not delivery:
        raise ValueError("Integration delivery not found")
    endpoint = db.scalar(
        select(IntegrationEndpoint).where(
            IntegrationEndpoint.tenant_id == tenant_id,
            IntegrationEndpoint.endpoint_id == delivery.endpoint_id,
            IntegrationEndpoint.enabled.is_(True),
        )
    )
    if not endpoint:
        raise ValueError("Integration endpoint is missing or disabled")
    url = validate_https_url(endpoint.url, settings.integration_allowed_hosts)
    event_format, content_type, body = _format_delivery(endpoint, delivery)
    headers = {
        "Content-Type": content_type,
        "X-OpenDataGraph-Delivery": delivery.delivery_id,
        "X-OpenDataGraph-Event": delivery.event_type,
        "X-OpenDataGraph-Mode": endpoint.mode,
        "X-OpenDataGraph-Format": event_format,
    }
    if endpoint.secret_ref:
        secret = resolve_secret(endpoint.secret_ref)
        if event_format == "splunk-hec":
            headers["Authorization"] = f"Splunk {secret}"
        else:
            digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-OpenDataGraph-Signature"] = f"sha256={digest}"
    delivery.attempts += 1
    delivery.last_attempted_at = utc_now()
    db.commit()
    try:
        response = httpx.post(
            url,
            content=body,
            headers=headers,
            timeout=settings.integration_timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:
        delivery.status = "failed"
        delivery.response_code = getattr(getattr(exc, "response", None), "status_code", None)
        delivery.error = safe_connector_error(exc)
        db.commit()
        raise RuntimeError(delivery.error) from None
    delivery.status = "delivered"
    delivery.response_code = response.status_code
    delivery.error = None
    delivery.dead_lettered_at = None
    delivery.delivered_at = utc_now()
    db.commit()
    return {
        "delivery_id": delivery.delivery_id,
        "endpoint_id": endpoint.endpoint_id,
        "status": delivery.status,
        "response_code": delivery.response_code,
        "mode": endpoint.mode,
        "event_format": event_format,
    }


def _format_delivery(
    endpoint: IntegrationEndpoint,
    delivery: IntegrationDelivery,
) -> tuple[str, str, bytes]:
    event_format = endpoint.event_format or "native"
    if event_format not in INTEGRATION_EVENT_FORMATS:
        raise ValueError("Unsupported integration event format")
    payload = json.loads(delivery.payload_json)
    timestamp = delivery.created_at.replace(tzinfo=UTC).isoformat()
    if event_format == "native":
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return event_format, "application/json", body
    if event_format == "cloudevents":
        envelope = {
            "specversion": "1.0",
            "id": delivery.delivery_id,
            "source": "urn:opendatagraph:integration",
            "type": f"com.opendatagraph.{delivery.event_type}",
            "subject": endpoint.endpoint_id,
            "time": timestamp,
            "datacontenttype": "application/json",
            "data": payload,
        }
        body = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
        return event_format, "application/cloudevents+json", body
    if event_format == "splunk-hec":
        envelope = {
            "time": delivery.created_at.replace(tzinfo=UTC).timestamp(),
            "host": "opendatagraph",
            "source": "opendatagraph",
            "sourcetype": f"opendatagraph:{delivery.event_type}",
            "event": payload,
            "fields": {
                "tenant_id": delivery.tenant_id,
                "delivery_id": delivery.delivery_id,
                "endpoint_id": endpoint.endpoint_id,
            },
        }
        body = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
        return event_format, "application/json", body
    extension = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    cef = (
        "CEF:0|OpenDataGraph|OpenDataGraph|1.5.0|"
        f"{_cef_escape(delivery.event_type)}|{_cef_escape(delivery.event_type)}|5|"
        f"rt={_cef_escape(timestamp)} "
        f"externalId={_cef_escape(delivery.delivery_id)} "
        f"cs1Label=tenantId cs1={_cef_escape(delivery.tenant_id)} "
        f"cs2Label=payload cs2={_cef_escape(extension)}"
    )
    return event_format, "text/plain; charset=utf-8", cef.encode()


def _cef_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("=", "\\=")


def _json_default(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _serialize_payload(payload: dict) -> str:
    payload_json = json.dumps(
        payload,
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(payload_json.encode()) > MAX_INTEGRATION_PAYLOAD_BYTES:
        raise ValueError("Integration event payload exceeds 256 KiB")
    return payload_json


def mark_delivery_dead_letter(
    db: Session,
    tenant_id: str,
    delivery_id: str,
    error: str,
) -> IntegrationDelivery:
    delivery = db.scalar(
        select(IntegrationDelivery).where(
            IntegrationDelivery.tenant_id == tenant_id,
            IntegrationDelivery.delivery_id == delivery_id,
        )
    )
    if not delivery:
        raise ValueError("Integration delivery not found")
    delivery.status = "dead-letter"
    delivery.error = error
    delivery.dead_lettered_at = utc_now()
    return delivery


def replay_delivery(
    db: Session,
    tenant_id: str,
    delivery_id: str,
    requested_by: str,
    reason: str,
) -> IntegrationDelivery:
    from app.services.jobs import enqueue_job

    original = db.scalar(
        select(IntegrationDelivery).where(
            IntegrationDelivery.tenant_id == tenant_id,
            IntegrationDelivery.delivery_id == delivery_id,
        )
    )
    if not original:
        raise ValueError("Integration delivery not found")
    if original.status not in {"failed", "dead-letter"}:
        raise ValueError("Only failed or dead-letter deliveries can be replayed")
    active_job = db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type == "integration.deliver",
            BackgroundJob.status.in_(("pending", "running")),
            BackgroundJob.payload_json == json.dumps({"delivery_id": delivery_id}),
        )
    )
    if active_job:
        raise ValueError("Integration delivery is still being attempted")
    endpoint = db.scalar(
        select(IntegrationEndpoint).where(
            IntegrationEndpoint.tenant_id == tenant_id,
            IntegrationEndpoint.endpoint_id == original.endpoint_id,
            IntegrationEndpoint.enabled.is_(True),
        )
    )
    if not endpoint:
        raise ValueError("Integration endpoint is missing or disabled")
    payload = json.loads(original.payload_json)
    replay_metadata = payload.setdefault("_opendatagraph", {})
    if isinstance(replay_metadata, dict):
        replay_metadata.update(
            {
                "replayed_from": original.delivery_id,
                "replay_reason": reason,
                "replayed_by": requested_by,
            }
        )
    payload_json = _serialize_payload(payload)
    delivery = IntegrationDelivery(
        tenant_id=tenant_id,
        delivery_id=str(uuid4()),
        endpoint_id=original.endpoint_id,
        event_type=original.event_type,
        payload_json=payload_json,
        replayed_from=original.delivery_id,
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    enqueue_job(
        db,
        tenant_id=tenant_id,
        job_type="integration.deliver",
        payload={"delivery_id": delivery.delivery_id},
        created_by=requested_by,
        max_attempts=5,
    )
    return delivery


def delivery_dashboard(db: Session, tenant_id: str) -> dict:
    deliveries = list(
        db.scalars(
            select(IntegrationDelivery).where(IntegrationDelivery.tenant_id == tenant_id)
        ).all()
    )
    statuses: dict[str, int] = {}
    endpoints: dict[str, dict] = {}
    for delivery in deliveries:
        statuses[delivery.status] = statuses.get(delivery.status, 0) + 1
        endpoint = endpoints.setdefault(
            delivery.endpoint_id,
            {
                "endpoint_id": delivery.endpoint_id,
                "total": 0,
                "delivered": 0,
                "failed": 0,
                "dead_letter": 0,
            },
        )
        endpoint["total"] += 1
        if delivery.status == "delivered":
            endpoint["delivered"] += 1
        elif delivery.status == "dead-letter":
            endpoint["dead_letter"] += 1
        elif delivery.status == "failed":
            endpoint["failed"] += 1
    delivered = statuses.get("delivered", 0)
    total = len(deliveries)
    return {
        "total": total,
        "statuses": statuses,
        "success_rate": round(delivered / total, 4) if total else 1.0,
        "endpoints": sorted(endpoints.values(), key=lambda item: item["endpoint_id"]),
    }
