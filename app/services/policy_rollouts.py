import hashlib
import json
import time
from threading import RLock
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PolicyBundle, PolicyReplay, PolicyRollout, RuntimeDecisionReceipt, utc_now
from app.observability import POLICY_ROLLOUT_EVENTS
from app.schemas import AuthZENEvaluationRequest
from app.services.outbox import queue_outbox_event
from app.services.policy import invalidate_policy_cache


_ROLLOUT_CACHE: dict[tuple[int, str], tuple[float, dict | None]] = {}
_ROLLOUT_LOCK = RLock()


def create_rollout(
    db: Session,
    tenant_id: str,
    values: dict,
    created_by: str,
) -> PolicyRollout:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"opendatagraph-policy-rollout:{tenant_id}"},
        )
    active = db.scalar(
        select(PolicyRollout).where(
            PolicyRollout.tenant_id == tenant_id,
            PolicyRollout.status == "active",
        )
    )
    if active:
        raise ValueError("Only one active policy rollout is allowed per tenant")
    bundle = _bundle(db, tenant_id, values["bundle_id"])
    if not bundle or bundle.status != "approved":
        raise ValueError("Policy rollout requires an approved candidate bundle")
    baseline = db.scalar(
        select(PolicyBundle).where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.status == "active",
        )
    )
    stage = values.get("stage", "shadow")
    traffic = values.get("traffic_percentage", 0)
    if stage == "shadow" and traffic != 0:
        raise ValueError("Shadow rollouts must use zero traffic percentage")
    if stage == "canary" and not 1 <= traffic <= 99:
        raise ValueError("Canary rollouts require traffic percentage from 1 to 99")
    rollout = PolicyRollout(
        tenant_id=tenant_id,
        rollout_id=str(uuid4()),
        bundle_id=bundle.bundle_id,
        baseline_bundle_id=baseline.bundle_id if baseline else None,
        stage=stage,
        traffic_percentage=traffic,
        replay_limit=values.get("replay_limit", 500),
        created_by=created_by,
    )
    db.add(rollout)
    queue_outbox_event(
        db,
        tenant_id,
        "policy-rollout",
        rollout.rollout_id,
        "policy.rollout.created",
        {
            "rollout_id": rollout.rollout_id,
            "bundle_id": bundle.bundle_id,
            "stage": stage,
            "traffic_percentage": traffic,
        },
        idempotency_key=f"policy-rollout-created:{rollout.rollout_id}",
    )
    db.commit()
    db.refresh(rollout)
    POLICY_ROLLOUT_EVENTS.labels("created", rollout.stage).inc()
    invalidate_rollout_cache(tenant_id)
    return rollout


def advance_rollout(
    db: Session,
    rollout: PolicyRollout,
    stage: str,
    traffic_percentage: int | None,
    promoted_by: str,
) -> PolicyRollout:
    transitions = {
        "shadow": {"canary", "paused", "completed"},
        "canary": {"shadow", "enforce", "paused", "completed"},
        "paused": {"shadow", "canary", "completed"},
    }
    if rollout.status != "active" or stage not in transitions.get(
        rollout.stage,
        set(),
    ):
        raise ValueError("Policy rollout stage transition is not allowed")
    if stage == "canary":
        if traffic_percentage is None or not 1 <= traffic_percentage <= 99:
            raise ValueError("Canary stage requires traffic percentage from 1 to 99")
        rollout.traffic_percentage = traffic_percentage
    elif stage == "shadow":
        rollout.traffic_percentage = 0
    elif stage == "paused":
        rollout.traffic_percentage = 0
    elif stage in {"enforce", "completed"}:
        rollout.traffic_percentage = 100 if stage == "enforce" else 0
        rollout.status = "completed"
        rollout.completed_at = utc_now()
    if stage == "enforce":
        candidate = _bundle(db, rollout.tenant_id, rollout.bundle_id)
        if not candidate or candidate.status != "approved":
            raise ValueError("Candidate bundle is no longer approved")
        _activate_bundle(db, candidate)
    rollout.stage = stage
    rollout.promoted_by = promoted_by
    rollout.updated_at = utc_now()
    queue_outbox_event(
        db,
        rollout.tenant_id,
        "policy-rollout",
        rollout.rollout_id,
        "policy.rollout.advanced",
        {
            "rollout_id": rollout.rollout_id,
            "bundle_id": rollout.bundle_id,
            "stage": stage,
            "traffic_percentage": rollout.traffic_percentage,
            "status": rollout.status,
        },
        idempotency_key=(
            f"policy-rollout-stage:{rollout.rollout_id}:{stage}:"
            f"{rollout.traffic_percentage}"
        ),
    )
    db.commit()
    db.refresh(rollout)
    POLICY_ROLLOUT_EVENTS.labels("advanced", rollout.stage).inc()
    invalidate_rollout_cache(rollout.tenant_id)
    invalidate_policy_cache(rollout.tenant_id)
    return rollout


def replay_rollout(
    db: Session,
    rollout: PolicyRollout,
    limit: int | None,
    created_by: str,
) -> PolicyReplay:
    from app.services.runtime_authorization import evaluate_policy_only

    bundle = _bundle(db, rollout.tenant_id, rollout.bundle_id)
    if not bundle:
        raise ValueError("Candidate policy bundle not found")
    definitions = json.loads(bundle.definition_json)
    bounded_limit = min(max(1, limit or rollout.replay_limit), 5000)
    receipts = list(
        db.scalars(
            select(RuntimeDecisionReceipt)
            .where(RuntimeDecisionReceipt.tenant_id == rollout.tenant_id)
            .order_by(RuntimeDecisionReceipt.created_at.desc())
            .limit(bounded_limit)
        ).all()
    )
    evaluated = changed = newly_denied = newly_permitted = incomplete = 0
    examples = []
    baseline_version = receipts[0].policy_version if receipts else "none"
    lookup_cache = {}
    for receipt in receipts:
        if not receipt.replayable:
            incomplete += 1
            continue
        context = json.loads(receipt.replay_context_json or "{}")
        request = AuthZENEvaluationRequest.model_validate(
            {
                "subject": {
                    "type": receipt.subject_type,
                    "id": receipt.subject_id,
                },
                "resource": {
                    "type": receipt.resource_type,
                    "id": receipt.resource_id,
                },
                "action": {"name": receipt.action_name},
                "context": context,
            }
        )
        candidate = evaluate_policy_only(
            db,
            rollout.tenant_id,
            request,
            lookup_cache,
            definitions,
            f"{bundle.name}:v{bundle.version}",
        )
        evaluated += 1
        candidate_decision = candidate["decision"]
        if candidate_decision != receipt.policy_decision:
            changed += 1
            newly_denied += int(
                receipt.policy_decision != "deny" and candidate_decision == "deny"
            )
            newly_permitted += int(
                receipt.policy_decision == "deny" and candidate_decision != "deny"
            )
            if len(examples) < 100:
                examples.append(
                    {
                        "receipt_id": receipt.receipt_id,
                        "baseline": receipt.policy_decision,
                        "candidate": candidate_decision,
                        "subject": {
                            "type": receipt.subject_type,
                            "id": receipt.subject_id,
                        },
                        "resource": {
                            "type": receipt.resource_type,
                            "id": receipt.resource_id,
                        },
                        "action": receipt.action_name,
                    }
                )
    replay = PolicyReplay(
        tenant_id=rollout.tenant_id,
        replay_id=str(uuid4()),
        rollout_id=rollout.rollout_id,
        bundle_id=rollout.bundle_id,
        baseline_policy_version=baseline_version,
        evaluated=evaluated,
        changed=changed,
        newly_denied=newly_denied,
        newly_permitted=newly_permitted,
        incomplete=incomplete,
        examples_json=json.dumps(examples),
        created_by=created_by,
    )
    db.add(replay)
    rollout.replay_evaluated = evaluated
    rollout.replay_changed = changed
    rollout.replay_newly_denied = newly_denied
    rollout.replay_newly_permitted = newly_permitted
    rollout.replay_incomplete = incomplete
    rollout.last_replay_id = replay.replay_id
    rollout.updated_at = utc_now()
    queue_outbox_event(
        db,
        rollout.tenant_id,
        "policy-rollout",
        rollout.rollout_id,
        "policy.rollout.replayed",
        {
            "rollout_id": rollout.rollout_id,
            "replay_id": replay.replay_id,
            "evaluated": evaluated,
            "changed": changed,
            "newly_denied": newly_denied,
            "newly_permitted": newly_permitted,
            "incomplete": incomplete,
        },
        idempotency_key=f"policy-replay:{replay.replay_id}",
    )
    db.commit()
    db.refresh(replay)
    db.refresh(rollout)
    POLICY_ROLLOUT_EVENTS.labels("replayed", rollout.stage).inc()
    return replay


def runtime_rollout(
    db: Session,
    tenant_id: str,
    selector: str,
) -> dict | None:
    cache_key = (id(db.get_bind()), tenant_id)
    now = time.monotonic()
    with _ROLLOUT_LOCK:
        cached = _ROLLOUT_CACHE.get(cache_key)
        if cached and cached[0] > now:
            config = cached[1]
        else:
            config = _load_runtime_rollout(db, tenant_id)
            _ROLLOUT_CACHE[cache_key] = (
                now + max(0, settings.policy_rollout_cache_seconds),
                config,
            )
    if not config:
        return None
    bucket = int(hashlib.sha256(selector.encode()).hexdigest()[:8], 16) % 100
    return {
        **config,
        "bucket": bucket,
        "selected": config["stage"] == "canary"
        and bucket < config["traffic_percentage"],
    }


def invalidate_rollout_cache(tenant_id: str | None = None) -> None:
    with _ROLLOUT_LOCK:
        if tenant_id is None:
            _ROLLOUT_CACHE.clear()
        else:
            for key in [key for key in _ROLLOUT_CACHE if key[1] == tenant_id]:
                _ROLLOUT_CACHE.pop(key, None)


def rollout_response(rollout: PolicyRollout) -> dict:
    return {
        "rollout_id": rollout.rollout_id,
        "bundle_id": rollout.bundle_id,
        "baseline_bundle_id": rollout.baseline_bundle_id,
        "stage": rollout.stage,
        "status": rollout.status,
        "traffic_percentage": rollout.traffic_percentage,
        "replay_limit": rollout.replay_limit,
        "replay": {
            "replay_id": rollout.last_replay_id,
            "evaluated": rollout.replay_evaluated,
            "changed": rollout.replay_changed,
            "newly_denied": rollout.replay_newly_denied,
            "newly_permitted": rollout.replay_newly_permitted,
            "incomplete": rollout.replay_incomplete,
        },
        "created_by": rollout.created_by,
        "promoted_by": rollout.promoted_by,
        "created_at": rollout.created_at,
        "updated_at": rollout.updated_at,
        "completed_at": rollout.completed_at,
    }


def replay_response(replay: PolicyReplay) -> dict:
    return {
        "replay_id": replay.replay_id,
        "rollout_id": replay.rollout_id,
        "bundle_id": replay.bundle_id,
        "baseline_policy_version": replay.baseline_policy_version,
        "evaluated": replay.evaluated,
        "changed": replay.changed,
        "newly_denied": replay.newly_denied,
        "newly_permitted": replay.newly_permitted,
        "incomplete": replay.incomplete,
        "examples": json.loads(replay.examples_json or "[]"),
        "created_by": replay.created_by,
        "created_at": replay.created_at,
    }


def _load_runtime_rollout(db: Session, tenant_id: str) -> dict | None:
    rollout = db.scalar(
        select(PolicyRollout)
        .where(
            PolicyRollout.tenant_id == tenant_id,
            PolicyRollout.status == "active",
            PolicyRollout.stage.in_(("shadow", "canary")),
        )
        .order_by(PolicyRollout.updated_at.desc())
        .limit(1)
    )
    if not rollout:
        return None
    bundle = _bundle(db, tenant_id, rollout.bundle_id)
    if not bundle or bundle.status != "approved":
        return None
    return {
        "rollout_id": rollout.rollout_id,
        "stage": rollout.stage,
        "traffic_percentage": rollout.traffic_percentage,
        "bundle_id": bundle.bundle_id,
        "policy_version": f"{bundle.name}:v{bundle.version}",
        "definitions": json.loads(bundle.definition_json),
    }


def _activate_bundle(db: Session, bundle: PolicyBundle) -> None:
    now = utc_now()
    active = db.scalar(
        select(PolicyBundle).where(
            PolicyBundle.tenant_id == bundle.tenant_id,
            PolicyBundle.status == "active",
        )
    )
    if active and active.id != bundle.id:
        active.status = "retired"
        active.retired_at = now
    bundle.status = "active"
    bundle.activated_at = now
    bundle.retired_at = None


def _bundle(db: Session, tenant_id: str, bundle_id: str) -> PolicyBundle | None:
    return db.scalar(
        select(PolicyBundle).where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.bundle_id == bundle_id,
        )
    )
