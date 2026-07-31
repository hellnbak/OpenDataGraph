import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnforcementEvent, RuntimeDecisionReceipt
from app.observability import ENFORCEMENT_EVENTS
from app.services.evidence_signing import canonical_json
from app.services.outbox import queue_outbox_event


class EnforcementConflict(ValueError):
    pass


def record_enforcement_event(
    db: Session,
    tenant_id: str,
    values: dict,
    recorded_by: str,
) -> tuple[EnforcementEvent, bool]:
    event_id = values.get("event_id") or str(uuid4())
    existing = db.scalar(
        select(EnforcementEvent).where(
            EnforcementEvent.tenant_id == tenant_id,
            EnforcementEvent.event_id == event_id,
        )
    )
    receipt = db.scalar(
        select(RuntimeDecisionReceipt).where(
            RuntimeDecisionReceipt.tenant_id == tenant_id,
            RuntimeDecisionReceipt.receipt_id == values["receipt_id"],
        )
    )
    if not receipt:
        raise ValueError("Runtime decision receipt not found")
    required = sorted(
        {
            obligation["id"]
            for obligation in json.loads(receipt.obligations_json or "[]")
            if obligation.get("required") and obligation.get("id")
        }
    )
    satisfied = sorted(set(values.get("satisfied_obligations", [])))
    if not set(satisfied) <= set(required):
        raise ValueError("Satisfied obligations must be present in the receipt")
    missing = sorted(set(required) - set(satisfied))
    outcome = values["outcome"]
    if outcome == "applied" and (not receipt.decision or missing):
        raise ValueError(
            "Applied enforcement requires a permitted receipt and every obligation"
        )
    if outcome in {"rejected", "failed"} and not values.get("failure_reason"):
        raise ValueError("Rejected or failed enforcement requires a reason")
    metadata_digest = _metadata_digest(values.get("metadata", {}))
    if existing:
        if (
            existing.receipt_id != receipt.receipt_id
            or existing.pep_id != values["pep_id"]
            or existing.outcome != outcome
            or json.loads(existing.satisfied_obligations_json) != satisfied
            or existing.metadata_sha256 != metadata_digest
        ):
            raise EnforcementConflict(
                "Enforcement event id was already used for different evidence"
            )
        return existing, True
    event = EnforcementEvent(
        tenant_id=tenant_id,
        event_id=event_id,
        receipt_id=receipt.receipt_id,
        pep_id=values["pep_id"],
        outcome=outcome,
        required_obligations_json=json.dumps(required),
        satisfied_obligations_json=json.dumps(satisfied),
        failure_reason=values.get("failure_reason"),
        metadata_sha256=metadata_digest,
        occurred_at=values["occurred_at"].replace(tzinfo=None),
        recorded_by=recorded_by,
    )
    db.add(event)
    queue_outbox_event(
        db,
        tenant_id,
        "runtime-receipt",
        receipt.receipt_id,
        "runtime.enforcement",
        {
            "event_id": event_id,
            "receipt_id": receipt.receipt_id,
            "pep_id": values["pep_id"],
            "outcome": outcome,
            "required_obligations": required,
            "satisfied_obligations": satisfied,
            "occurred_at": values["occurred_at"].isoformat(),
        },
        idempotency_key=f"enforcement:{event_id}",
    )
    db.commit()
    db.refresh(event)
    ENFORCEMENT_EVENTS.labels(outcome).inc()
    return event, False


def enforcement_response(event: EnforcementEvent) -> dict:
    return {
        "event_id": event.event_id,
        "receipt_id": event.receipt_id,
        "pep_id": event.pep_id,
        "outcome": event.outcome,
        "required_obligations": json.loads(event.required_obligations_json),
        "satisfied_obligations": json.loads(event.satisfied_obligations_json),
        "failure_reason": event.failure_reason,
        "metadata_sha256": event.metadata_sha256,
        "occurred_at": event.occurred_at,
        "recorded_by": event.recorded_by,
        "created_at": event.created_at,
    }


def _metadata_digest(metadata: dict) -> str:
    forbidden = {
        "authorization",
        "credential",
        "credentials",
        "password",
        "prompt",
        "response",
        "secret",
        "token",
    }

    def inspect(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower().replace("-", "_") in forbidden:
                    raise ValueError("Enforcement metadata contains a forbidden field")
                inspect(item)
        elif isinstance(value, list):
            if len(value) > 1000:
                raise ValueError("Enforcement metadata list exceeds 1000 items")
            for item in value:
                inspect(item)
        elif isinstance(value, str) and len(value) > 4000:
            raise ValueError("Enforcement metadata string exceeds 4000 characters")
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("Enforcement metadata contains an unsupported value")

    if not isinstance(metadata, dict):
        raise ValueError("Enforcement metadata must be an object")
    inspect(metadata)
    canonical = canonical_json(metadata)
    if len(canonical) > 64 * 1024:
        raise ValueError("Enforcement metadata exceeds 64 KiB")
    return hashlib.sha256(canonical).hexdigest()
