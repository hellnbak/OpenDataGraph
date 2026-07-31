import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GovernanceOutboxEvent, utc_now
from app.observability import OUTBOX_DISPATCH
from app.services.connectors import safe_connector_error


FORBIDDEN_KEYS = {
    "authorization",
    "credential",
    "credentials",
    "password",
    "prompt",
    "response",
    "secret",
    "token",
}


def queue_outbox_event(
    db: Session,
    tenant_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> GovernanceOutboxEvent:
    payload_json = _bounded_payload(payload)
    if idempotency_key:
        existing = db.scalar(
            select(GovernanceOutboxEvent).where(
                GovernanceOutboxEvent.tenant_id == tenant_id,
                GovernanceOutboxEvent.idempotency_key == idempotency_key,
            )
        )
        if existing:
            if (
                existing.event_type != event_type
                or existing.aggregate_type != aggregate_type
                or existing.aggregate_id != aggregate_id
                or existing.payload_json != payload_json
            ):
                raise ValueError("Outbox idempotency key has conflicting event data")
            return existing
    event = GovernanceOutboxEvent(
        tenant_id=tenant_id,
        event_id=str(uuid4()),
        idempotency_key=idempotency_key,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload_json=payload_json,
    )
    db.add(event)
    return event


def dispatch_outbox_events(
    db: Session,
    limit: int | None = None,
    tenant_id: str | None = None,
) -> dict:
    from app.services.integrations import queue_integration_event

    bounded_limit = min(
        max(1, limit or settings.governance_outbox_batch_size),
        1000,
    )
    now = utc_now()
    stale_cutoff = now - timedelta(seconds=settings.worker_claim_timeout_seconds)
    stale_conditions = [
            GovernanceOutboxEvent.status == "dispatching",
            GovernanceOutboxEvent.claimed_at < stale_cutoff,
            GovernanceOutboxEvent.attempts
            < settings.governance_outbox_max_attempts,
    ]
    if tenant_id:
        stale_conditions.append(GovernanceOutboxEvent.tenant_id == tenant_id)
    db.execute(
        update(GovernanceOutboxEvent)
        .where(*stale_conditions)
        .values(
            status="pending",
            claimed_at=None,
            available_at=now,
            last_error="Recovered after outbox claim timeout",
        )
    )
    db.commit()
    pending_conditions = [
        GovernanceOutboxEvent.status == "pending",
        GovernanceOutboxEvent.available_at <= now,
    ]
    if tenant_id:
        pending_conditions.append(GovernanceOutboxEvent.tenant_id == tenant_id)
    candidate_ids = list(
        db.scalars(
            select(GovernanceOutboxEvent.id)
            .where(*pending_conditions)
            .order_by(GovernanceOutboxEvent.created_at)
            .limit(bounded_limit)
        ).all()
    )
    dispatched = retried = failed = 0
    for event_id in candidate_ids:
        claimed = db.execute(
            update(GovernanceOutboxEvent)
            .where(
                GovernanceOutboxEvent.id == event_id,
                GovernanceOutboxEvent.status == "pending",
                *(
                    (GovernanceOutboxEvent.tenant_id == tenant_id,)
                    if tenant_id
                    else ()
                ),
            )
            .values(
                status="dispatching",
                claimed_at=utc_now(),
                attempts=GovernanceOutboxEvent.attempts + 1,
            )
        )
        db.commit()
        if claimed.rowcount != 1:
            continue
        event = db.get(GovernanceOutboxEvent, event_id)
        try:
            queue_integration_event(
                db,
                event.tenant_id,
                event.event_type,
                json.loads(event.payload_json),
                created_by="governance-outbox",
                idempotency_key=event.event_id,
            )
            event.status = "dispatched"
            event.dispatched_at = utc_now()
            event.claimed_at = None
            event.last_error = None
            dispatched += 1
        except Exception as exc:
            event.last_error = safe_connector_error(exc)
            event.claimed_at = None
            if event.attempts >= settings.governance_outbox_max_attempts:
                event.status = "failed"
                failed += 1
            else:
                event.status = "pending"
                event.available_at = utc_now() + timedelta(
                    seconds=min(300, 2**event.attempts)
                )
                retried += 1
        db.commit()
    for outcome, count in (
        ("dispatched", dispatched),
        ("retried", retried),
        ("failed", failed),
    ):
        if count:
            OUTBOX_DISPATCH.labels(outcome).inc(count)
    return {
        "claimed": dispatched + retried + failed,
        "dispatched": dispatched,
        "retried": retried,
        "failed": failed,
    }


def outbox_response(event: GovernanceOutboxEvent) -> dict:
    return {
        "event_id": event.event_id,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "event_type": event.event_type,
        "status": event.status,
        "attempts": event.attempts,
        "available_at": event.available_at,
        "last_error": event.last_error,
        "created_at": event.created_at,
        "dispatched_at": event.dispatched_at,
    }


def _bounded_payload(payload: dict) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Outbox payload must be an object")

    def inspect(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower().replace("-", "_") in FORBIDDEN_KEYS:
                    raise ValueError("Outbox payload contains a forbidden field")
                inspect(item)
        elif isinstance(value, list):
            if len(value) > 1000:
                raise ValueError("Outbox payload list exceeds 1000 items")
            for item in value:
                inspect(item)
        elif isinstance(value, str) and len(value) > 4000:
            raise ValueError("Outbox payload string exceeds 4000 characters")
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("Outbox payload contains an unsupported value")

    inspect(payload)
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    if len(serialized.encode()) > 64 * 1024:
        raise ValueError("Outbox payload exceeds 64 KiB")
    return serialized
