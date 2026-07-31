import hashlib
import hmac
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BackgroundJob, IntegrationDelivery, IntegrationEndpoint, utc_now
from app.services.connectors import safe_connector_error
from connectors.security import validate_https_url


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
) -> IntegrationEndpoint:
    if not settings.integration_allowed_hosts:
        raise ValueError("ODG_INTEGRATION_ALLOWED_HOSTS must be configured")
    validated_url = validate_https_url(url, settings.integration_allowed_hosts)
    endpoint = IntegrationEndpoint(
        tenant_id=tenant_id,
        endpoint_id=str(uuid4()),
        name=name,
        mode=mode,
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
            payload_json=json.dumps(payload),
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
    body = delivery.payload_json.encode()
    headers = {
        "Content-Type": "application/json",
        "X-OpenDataGraph-Delivery": delivery.delivery_id,
        "X-OpenDataGraph-Event": delivery.event_type,
        "X-OpenDataGraph-Mode": endpoint.mode,
    }
    if endpoint.secret_ref:
        secret = resolve_secret(endpoint.secret_ref)
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
    }


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
    delivery = IntegrationDelivery(
        tenant_id=tenant_id,
        delivery_id=str(uuid4()),
        endpoint_id=original.endpoint_id,
        event_type=original.event_type,
        payload_json=json.dumps(payload),
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
