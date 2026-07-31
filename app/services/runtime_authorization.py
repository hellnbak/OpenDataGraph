import hashlib
import json
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AIAgent,
    AIResource,
    DataAsset,
    RuntimeDecisionReceipt,
    utc_now,
)
from app.observability import AUTHORIZATION_DECISIONS, AUTHORIZATION_EVALUATION
from app.schemas import AuthZENEvaluationRequest
from app.services.evidence_signing import (
    canonical_json,
    sign_manifest,
    validate_signing_profile,
    verify_manifest_signature,
)
from app.services.policy import effective_policy_matches, evaluate as evaluate_asset_policy


AI_RESOURCE_TYPES = {"model", "prompt", "vector-index", "tool", "endpoint", "ai-system"}
ENFORCEMENT_MODES = {"observe", "warn", "enforce"}


class IdempotencyConflict(ValueError):
    pass


def evaluate_access(
    db: Session,
    tenant_id: str,
    request: AuthZENEvaluationRequest,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    lookup_cache: dict | None = None,
) -> tuple[dict, RuntimeDecisionReceipt, bool]:
    payload = request.model_dump(mode="json")
    request_digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    if idempotency_key:
        existing = db.scalar(
            select(RuntimeDecisionReceipt).where(
                RuntimeDecisionReceipt.tenant_id == tenant_id,
                RuntimeDecisionReceipt.idempotency_key == idempotency_key,
            )
        )
        if existing:
            if existing.request_sha256 != request_digest:
                raise IdempotencyConflict(
                    "Idempotency key was already used for a different evaluation"
                )
            return decision_response(existing), existing, True

    mode = settings.runtime_authorization_mode
    if mode not in ENFORCEMENT_MODES:
        raise ValueError("ODG_RUNTIME_AUTHORIZATION_MODE must be observe, warn, or enforce")

    started = time.perf_counter()
    result = _evaluate_policy(db, tenant_id, request, lookup_cache)
    AUTHORIZATION_EVALUATION.observe(time.perf_counter() - started)
    policy_decision = result["decision"]
    permitted = policy_decision != "deny" if mode == "enforce" else True
    obligations = [
        {
            "id": control,
            "required": True,
            "enforced_by": "policy-enforcement-point",
        }
        for control in result["controls"]
    ]
    now = utc_now()
    retention_until = now + timedelta(
        days=max(1, settings.runtime_receipt_retention_days)
    )
    receipt_id = str(uuid4())
    signing_profile = settings.runtime_receipt_signing_profile or None
    if signing_profile:
        validate_signing_profile(signing_profile)
    signing_status = "pending" if signing_profile else "unsigned"
    manifest = {
        "format": "opendatagraph-runtime-decision-receipt",
        "version": 1,
        "receipt_id": receipt_id,
        "request_id": request_id,
        "tenant_id": tenant_id,
        "subject": _entity_claim(payload["subject"]),
        "resource": _entity_claim(payload["resource"]),
        "action": _entity_claim(payload["action"]),
        "context_sha256": hashlib.sha256(
            canonical_json(payload.get("context", {}))
        ).hexdigest(),
        "request_sha256": request_digest,
        "authorization": {
            "decision": permitted,
            "policy_decision": policy_decision,
            "enforcement_mode": mode,
            "risk_score": result["risk_score"],
            "policy_version": result["policy_version"],
            "matched_policies": result["matched_policies"],
            "reasons": result["reasons"],
            "obligations": obligations,
        },
        "issued_at": now,
        "retention_until": retention_until,
    }
    manifest_digest = hashlib.sha256(canonical_json(manifest)).hexdigest()
    receipt = RuntimeDecisionReceipt(
        tenant_id=tenant_id,
        receipt_id=receipt_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        subject_type=request.subject.type,
        subject_id=request.subject.id,
        action_name=request.action.name,
        resource_type=request.resource.type,
        resource_id=request.resource.id,
        request_sha256=request_digest,
        decision=permitted,
        policy_decision=policy_decision,
        enforcement_mode=mode,
        risk_score=result["risk_score"],
        policy_version=result["policy_version"],
        matched_policies_json=json.dumps(result["matched_policies"]),
        reasons_json=json.dumps(result["reasons"]),
        obligations_json=json.dumps(obligations),
        manifest_json=canonical_json(manifest).decode(),
        manifest_sha256=manifest_digest,
        signing_status=signing_status,
        signing_profile=signing_profile,
        assurance_json=json.dumps(
            {
                "status": signing_status,
                "profile": signing_profile,
                "type": "none",
                "key_id": None,
                "signed_at": None,
            },
            default=str,
        ),
        retention_until=retention_until,
        created_at=now,
    )
    db.add(receipt)
    AUTHORIZATION_DECISIONS.labels(
        mode,
        policy_decision,
        str(permitted).lower(),
    ).inc()
    return decision_response(receipt), receipt, False


def decision_response(receipt: RuntimeDecisionReceipt) -> dict:
    reasons = json.loads(receipt.reasons_json or "[]")
    return {
        "decision": receipt.decision,
        "context": {
            "reason": reasons[0] if reasons else "No policy reason was recorded",
            "policy_decision": receipt.policy_decision,
            "enforcement_mode": receipt.enforcement_mode,
            "risk_score": receipt.risk_score,
            "policy_version": receipt.policy_version,
            "matched_policies": json.loads(receipt.matched_policies_json or "[]"),
            "reasons": reasons,
            "obligations": json.loads(receipt.obligations_json or "[]"),
            "receipt": {
                "id": receipt.receipt_id,
                "sha256": receipt.manifest_sha256,
                "signing_status": receipt.signing_status,
                "signing_profile": receipt.signing_profile,
                "retention_until": receipt.retention_until,
            },
        },
    }


def receipt_response(
    receipt: RuntimeDecisionReceipt,
    include_manifest: bool = False,
) -> dict:
    response = {
        "receipt_id": receipt.receipt_id,
        "request_id": receipt.request_id,
        "subject": {"type": receipt.subject_type, "id": receipt.subject_id},
        "action": {"name": receipt.action_name},
        "resource": {"type": receipt.resource_type, "id": receipt.resource_id},
        "request_sha256": receipt.request_sha256,
        "decision": receipt.decision,
        "policy_decision": receipt.policy_decision,
        "enforcement_mode": receipt.enforcement_mode,
        "risk_score": receipt.risk_score,
        "policy_version": receipt.policy_version,
        "matched_policies": json.loads(receipt.matched_policies_json or "[]"),
        "reasons": json.loads(receipt.reasons_json or "[]"),
        "obligations": json.loads(receipt.obligations_json or "[]"),
        "manifest_sha256": receipt.manifest_sha256,
        "signing_status": receipt.signing_status,
        "signing_profile": receipt.signing_profile,
        "assurance": json.loads(receipt.assurance_json or "{}"),
        "signing_attempts": receipt.signing_attempts,
        "signing_error": receipt.signing_error,
        "retention_until": receipt.retention_until,
        "created_at": receipt.created_at,
    }
    if include_manifest:
        response["manifest"] = json.loads(receipt.manifest_json)
    return response


def verify_receipt(
    receipt: RuntimeDecisionReceipt,
    verification_profile: str | None = None,
) -> dict:
    manifest = json.loads(receipt.manifest_json)
    assurance = json.loads(receipt.assurance_json or "{}")
    verification = verify_manifest_signature(
        manifest,
        assurance,
        verification_profile,
    )
    stored_digest_valid = (
        hashlib.sha256(canonical_json(manifest)).hexdigest()
        == receipt.manifest_sha256
    )
    verification["stored_digest_valid"] = stored_digest_valid
    verification["valid"] = verification["valid"] and stored_digest_valid
    verification["receipt_id"] = receipt.receipt_id
    verification["signing_status"] = receipt.signing_status
    if not stored_digest_valid:
        verification["errors"] = [
            *verification["errors"],
            "stored-manifest-digest-mismatch",
        ]
    return verification


def process_pending_receipts(db: Session, limit: int | None = None) -> dict:
    bounded_limit = min(
        max(1, limit or settings.runtime_receipt_signing_batch_size),
        1000,
    )
    now = utc_now()
    stale_cutoff = now - timedelta(seconds=settings.worker_claim_timeout_seconds)
    db.execute(
        update(RuntimeDecisionReceipt)
        .where(
            RuntimeDecisionReceipt.signing_status == "signing",
            RuntimeDecisionReceipt.signing_claimed_at < stale_cutoff,
            RuntimeDecisionReceipt.signing_attempts
            < settings.runtime_receipt_signing_max_attempts,
        )
        .values(
            signing_status="pending",
            signing_claimed_at=None,
            signing_available_at=now,
            signing_error="Recovered after signing claim timeout",
        )
    )
    db.commit()
    candidate_ids = list(
        db.scalars(
            select(RuntimeDecisionReceipt.id)
            .where(
                RuntimeDecisionReceipt.signing_status == "pending",
                RuntimeDecisionReceipt.signing_available_at <= now,
            )
            .order_by(RuntimeDecisionReceipt.created_at)
            .limit(bounded_limit)
        ).all()
    )
    signed = 0
    retried = 0
    failed = 0
    for receipt_id in candidate_ids:
        claimed_at = utc_now()
        claimed = db.execute(
            update(RuntimeDecisionReceipt)
            .where(
                RuntimeDecisionReceipt.id == receipt_id,
                RuntimeDecisionReceipt.signing_status == "pending",
            )
            .values(
                signing_status="signing",
                signing_claimed_at=claimed_at,
                signing_attempts=RuntimeDecisionReceipt.signing_attempts + 1,
            )
        )
        db.commit()
        if claimed.rowcount != 1:
            continue
        receipt = db.get(RuntimeDecisionReceipt, receipt_id)
        try:
            assurance = sign_manifest(
                json.loads(receipt.manifest_json),
                receipt.signing_profile,
            )
            receipt.assurance_json = json.dumps(assurance, default=str)
            receipt.signing_status = assurance["status"]
            receipt.signing_error = None
            receipt.signing_claimed_at = None
            signed += 1
        except Exception as exc:
            receipt.signing_error = str(exc)[:2000]
            receipt.signing_claimed_at = None
            if receipt.signing_attempts >= settings.runtime_receipt_signing_max_attempts:
                receipt.signing_status = "failed"
                failed += 1
            else:
                receipt.signing_status = "pending"
                receipt.signing_available_at = utc_now() + timedelta(
                    seconds=min(300, 2**receipt.signing_attempts)
                )
                retried += 1
        db.commit()
    return {
        "claimed": signed + retried + failed,
        "signed": signed,
        "retried": retried,
        "failed": failed,
    }


def purge_expired_receipts(db: Session, limit: int = 10_000) -> int:
    receipt_ids = list(
        db.scalars(
            select(RuntimeDecisionReceipt.id)
            .where(
                RuntimeDecisionReceipt.retention_until < utc_now(),
                RuntimeDecisionReceipt.signing_status.not_in({"pending", "signing"}),
            )
            .order_by(RuntimeDecisionReceipt.retention_until)
            .limit(min(max(1, limit), 100_000))
        ).all()
    )
    if not receipt_ids:
        return 0
    deleted = db.execute(
        delete(RuntimeDecisionReceipt).where(
            RuntimeDecisionReceipt.id.in_(receipt_ids)
        )
    )
    db.commit()
    return deleted.rowcount


def _evaluate_policy(
    db: Session,
    tenant_id: str,
    request: AuthZENEvaluationRequest,
    lookup_cache: dict | None,
) -> dict:
    agent = _agent(
        db,
        tenant_id,
        request.subject.type,
        request.subject.id,
        lookup_cache,
    )
    asset = _asset(
        db,
        tenant_id,
        request.resource.type,
        request.resource.id,
        lookup_cache,
    )
    if request.subject.type in {"agent", "ai_agent"} and not agent:
        return _denial("AI agent is not registered in this tenant", 100)
    if request.resource.type in {"asset", "data_asset"} and not asset:
        return _denial("Data asset is not registered in this tenant", 100)
    if agent and asset:
        destination = str(request.context.get("destination", "internal-rag"))
        purpose = str(request.context.get("purpose", "runtime-access"))
        return evaluate_asset_policy(
            agent,
            asset,
            destination,
            request.action.name,
            purpose,
            db,
            tenant_id,
        )

    context = _policy_context(request, agent, asset)
    matches, policy_version = effective_policy_matches(context, db, tenant_id)
    reasons = [match.reason for match in matches]
    controls = ["audit-log", "identity-context", "tenant-context"]
    for match in matches:
        controls.extend(match.controls)
    risk_score = max([20, *(match.risk_score for match in matches)])
    policy_decision = matches[0].decision if matches else "allow"
    if agent and agent.approval_status != "Approved":
        policy_decision = "deny"
        risk_score = max(risk_score, 90)
        reasons.append("AI agent is not approved for production access")
        controls.append("complete-agent-security-review")

    ai_resource = _ai_resource(
        db,
        tenant_id,
        request.resource.type,
        request.resource.id,
        lookup_cache,
    )
    if request.resource.type in AI_RESOURCE_TYPES and not ai_resource:
        policy_decision = "deny"
        risk_score = 100
        reasons.append("AI resource is not registered in this tenant")
        controls.append("register-ai-resource")
    elif ai_resource and ai_resource.status != "approved":
        policy_decision = "deny"
        risk_score = max(risk_score, 90)
        reasons.append("AI resource is not approved for runtime use")
        controls.append("complete-ai-resource-review")
    if not reasons:
        reasons = ["Subject, action, resource, and runtime context are within policy"]
    return {
        "decision": policy_decision,
        "risk_score": min(100, risk_score),
        "reasons": list(dict.fromkeys(reasons)),
        "controls": sorted(set(controls)),
        "confidence": 1.0,
        "policy_version": policy_version,
        "expires_in_seconds": 300,
        "matched_policies": [match.policy_id for match in matches],
    }


def _policy_context(
    request: AuthZENEvaluationRequest,
    agent: AIAgent | None,
    asset: DataAsset | None,
) -> dict:
    context = {
        "subject_type": request.subject.type,
        "subject_id": request.subject.id,
        "resource_type": request.resource.type,
        "resource_id": request.resource.id,
        "action": request.action.name,
    }
    sources = (
        request.subject.properties,
        request.resource.properties,
        request.action.properties,
        request.context,
    )
    for source in sources:
        for key, value in source.items():
            if isinstance(key, str) and len(key) <= 160:
                context[key] = value
    if agent:
        context["agent_status"] = agent.approval_status.lower()
    if asset:
        context["sensitivity"] = asset.sensitivity
    destination = str(context.get("destination", ""))
    if destination and "destination_type" not in context:
        context["destination_type"] = (
            "approved_private_ai"
            if destination in {"internal-rag", "private-model", "bedrock-private"}
            else "public_ai"
        )
    return context


def _agent(
    db: Session,
    tenant_id: str,
    subject_type: str,
    subject_id: str,
    lookup_cache: dict | None,
) -> AIAgent | None:
    if subject_type not in {"agent", "ai_agent"}:
        return None
    cache_key = ("agent", tenant_id, subject_id)
    if lookup_cache is not None and cache_key in lookup_cache:
        return lookup_cache[cache_key]
    result = db.scalar(
        select(AIAgent).where(
            AIAgent.tenant_id == tenant_id,
            AIAgent.key == subject_id,
        )
    )
    if lookup_cache is not None:
        lookup_cache[cache_key] = result
    return result


def _asset(
    db: Session,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    lookup_cache: dict | None,
) -> DataAsset | None:
    if resource_type not in {"asset", "data_asset"}:
        return None
    cache_key = ("asset", tenant_id, resource_id)
    if lookup_cache is not None and cache_key in lookup_cache:
        return lookup_cache[cache_key]
    conditions = [DataAsset.external_id == resource_id]
    try:
        conditions.append(DataAsset.id == int(resource_id))
    except ValueError:
        pass
    from sqlalchemy import or_

    result = db.scalar(
        select(DataAsset).where(
            DataAsset.tenant_id == tenant_id,
            or_(*conditions),
        )
    )
    if lookup_cache is not None:
        lookup_cache[cache_key] = result
    return result


def _ai_resource(
    db: Session,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    lookup_cache: dict | None,
) -> AIResource | None:
    if resource_type not in AI_RESOURCE_TYPES:
        return None
    cache_key = ("ai-resource", tenant_id, resource_type, resource_id)
    if lookup_cache is not None and cache_key in lookup_cache:
        return lookup_cache[cache_key]
    result = db.scalar(
        select(AIResource).where(
            AIResource.tenant_id == tenant_id,
            AIResource.resource_key == resource_id,
            AIResource.resource_type == resource_type,
        )
    )
    if lookup_cache is not None:
        lookup_cache[cache_key] = result
    return result


def _entity_claim(entity: dict) -> dict:
    identity = {
        key: entity[key]
        for key in ("type", "id", "name")
        if key in entity
    }
    identity["properties_sha256"] = hashlib.sha256(
        canonical_json(entity.get("properties", {}))
    ).hexdigest()
    return identity


def _denial(reason: str, risk_score: int) -> dict:
    return {
        "decision": "deny",
        "risk_score": risk_score,
        "reasons": [reason],
        "controls": ["audit-log", "deny-by-default", "tenant-context"],
        "confidence": 1.0,
        "policy_version": "1.8.0",
        "expires_in_seconds": 60,
        "matched_policies": [],
    }
