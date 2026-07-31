import json

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal, require_role
from app.config import settings
from app.database import get_db
from app.models import (
    AILineageObservation,
    AIResource,
    AIResourceRelationship,
    RuntimeDecisionReceipt,
)
from app.schemas import (
    AILineageObservationCreate,
    AIRelationshipCreate,
    AIResourceCreate,
    AIResourceUpdate,
    AuthZENEvaluationRequest,
    AuthZENEvaluationsRequest,
    GovernanceEvidencePackageVerify,
)
from app.services.ai_resources import (
    ai_resource_response,
    create_ai_resource,
    declare_relationship,
    observation_response,
    observe_relationship,
    relationship_response,
    update_ai_resource,
)
from app.services.runtime_authorization import (
    IdempotencyConflict,
    evaluate_access,
    receipt_response,
    verify_receipt,
)


router = APIRouter()


@router.get("/.well-known/authzen-configuration")
def authzen_configuration(request: Request):
    base_url = settings.public_base_url or str(request.base_url).rstrip("/")
    return {
        "policy_decision_point": base_url,
        "access_evaluation_endpoint": f"{base_url}/access/v1/evaluation",
        "access_evaluations_endpoint": f"{base_url}/access/v1/evaluations",
        "subject_search_endpoint": f"{base_url}/access/v1/search/subject",
        "resource_search_endpoint": f"{base_url}/access/v1/search/resource",
        "action_search_endpoint": f"{base_url}/access/v1/search/action",
        "odg_enforcement_mode": settings.runtime_authorization_mode,
        "odg_receipts_endpoint": f"{base_url}/api/v1/runtime/decision-receipts",
        "odg_enforcement_events_endpoint": f"{base_url}/api/v1/runtime/enforcement-events",
    }


@router.post("/access/v1/evaluation")
def access_evaluation(
    payload: dict = Body(...),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    request = _evaluation_request(payload)
    request_id = _bounded_header(x_request_id, "X-Request-ID")
    normalized_idempotency = _bounded_header(idempotency_key, "Idempotency-Key")
    try:
        response, _receipt, _idempotent = evaluate_access(
            db,
            principal.tenant_id,
            request,
            request_id,
            normalized_idempotency,
        )
        db.commit()
        return response
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Runtime decision receipt already exists") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from exc


@router.post("/access/v1/evaluations")
def access_evaluations(
    payload: dict = Body(...),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    if len(json.dumps(payload, separators=(",", ":")).encode()) > 2 * 1024 * 1024:
        raise HTTPException(400, "Access Evaluations request exceeds 2 MiB")
    request_id = _bounded_header(x_request_id, "X-Request-ID")
    normalized_idempotency = _bounded_header(idempotency_key, "Idempotency-Key")
    try:
        request = AuthZENEvaluationsRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(400, "Invalid Access Evaluations request") from exc
    max_batch = min(max(1, settings.runtime_authorization_batch_max), 1000)
    if len(request.evaluations) > max_batch:
        raise HTTPException(
            400,
            f"Access Evaluations request exceeds the configured limit of {max_batch}",
        )
    if not request.evaluations:
        single = _resolved_evaluation(request, None)
        try:
            response, _receipt, _idempotent = evaluate_access(
                db,
                principal.tenant_id,
                single,
                request_id,
                normalized_idempotency,
            )
            db.commit()
            return response
        except IdempotencyConflict as exc:
            db.rollback()
            raise HTTPException(409, str(exc)) from exc
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Runtime decision receipt already exists") from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(503, str(exc)) from exc

    responses = []
    semantic = request.options.evaluations_semantic
    lookup_cache = {}
    try:
        for index, item in enumerate(request.evaluations):
            try:
                evaluation = _resolved_evaluation(request, item)
            except HTTPException as exc:
                response = {
                    "decision": False,
                    "context": {
                        "error": {"status": 400, "message": str(exc.detail)}
                    },
                }
            else:
                response, _receipt, _idempotent = evaluate_access(
                    db,
                    principal.tenant_id,
                    evaluation,
                    _indexed_header(request_id, index),
                    _indexed_header(normalized_idempotency, index),
                    lookup_cache,
                )
            responses.append(response)
            if semantic == "deny_on_first_deny" and not response["decision"]:
                break
            if semantic == "permit_on_first_permit" and response["decision"]:
                break
        db.commit()
        return {"evaluations": responses}
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Runtime decision receipt already exists") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from exc


@router.get("/api/v1/runtime/decision-receipts")
def list_runtime_decision_receipts(
    decision: bool | None = None,
    subject_type: str | None = Query(default=None, max_length=80),
    subject_id: str | None = Query(default=None, max_length=320),
    resource_type: str | None = Query(default=None, max_length=80),
    resource_id: str | None = Query(default=None, max_length=1024),
    signing_status: str | None = Query(
        default=None,
        pattern="^(unsigned|pending|signing|signed|failed)$",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(RuntimeDecisionReceipt).where(
        RuntimeDecisionReceipt.tenant_id == principal.tenant_id
    )
    for field, value in (
        (RuntimeDecisionReceipt.decision, decision),
        (RuntimeDecisionReceipt.subject_type, subject_type),
        (RuntimeDecisionReceipt.subject_id, subject_id),
        (RuntimeDecisionReceipt.resource_type, resource_type),
        (RuntimeDecisionReceipt.resource_id, resource_id),
        (RuntimeDecisionReceipt.signing_status, signing_status),
    ):
        if value is not None:
            statement = statement.where(field == value)
    rows = db.scalars(
        statement.order_by(RuntimeDecisionReceipt.created_at.desc()).limit(limit)
    )
    return [receipt_response(row) for row in rows]


@router.get("/api/v1/runtime/decision-receipts/{receipt_id}")
def get_runtime_decision_receipt(
    receipt_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    receipt = _receipt(db, principal.tenant_id, receipt_id)
    if not receipt:
        raise HTTPException(404, "Runtime decision receipt not found")
    return receipt_response(receipt, include_manifest=True)


@router.post("/api/v1/runtime/decision-receipts/{receipt_id}/verify")
def verify_runtime_decision_receipt(
    receipt_id: str,
    req: GovernanceEvidencePackageVerify,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    receipt = _receipt(db, principal.tenant_id, receipt_id)
    if not receipt:
        raise HTTPException(404, "Runtime decision receipt not found")
    try:
        return verify_receipt(receipt, req.verification_profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/v1/ai/resources", status_code=201)
def create_registered_ai_resource(
    req: AIResourceCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    try:
        resource = create_ai_resource(
            db,
            principal.tenant_id,
            req.model_dump(),
            principal.subject,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "AI resource key already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ai_resource_response(resource)


@router.get("/api/v1/ai/resources")
def list_registered_ai_resources(
    resource_type: str | None = Query(default=None, max_length=40),
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    statement = select(AIResource).where(
        AIResource.tenant_id == principal.tenant_id
    )
    if resource_type:
        statement = statement.where(AIResource.resource_type == resource_type)
    if status:
        statement = statement.where(AIResource.status == status)
    resources = db.scalars(statement.order_by(AIResource.name).limit(limit))
    return [ai_resource_response(resource) for resource in resources]


@router.get("/api/v1/ai/resources/{resource_key}")
def get_registered_ai_resource(
    resource_key: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    resource = _ai_resource(db, principal.tenant_id, resource_key)
    if not resource:
        raise HTTPException(404, "AI resource not found")
    return ai_resource_response(resource)


@router.patch("/api/v1/ai/resources/{resource_key}")
def update_registered_ai_resource(
    resource_key: str,
    req: AIResourceUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    resource = _ai_resource(db, principal.tenant_id, resource_key)
    if not resource:
        raise HTTPException(404, "AI resource not found")
    try:
        return ai_resource_response(
            update_ai_resource(
                db,
                resource,
                req.model_dump(exclude_none=True),
            )
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/v1/ai/lineage/relationships")
def create_ai_lineage_relationship(
    req: AIRelationshipCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    try:
        relationship, created = declare_relationship(
            db,
            principal.tenant_id,
            req.source.model_dump(),
            req.relationship,
            req.target.model_dump(),
            req.expected,
            req.metadata,
            principal.subject,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "AI lineage relationship already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"created": created, **relationship_response(relationship)}


@router.get("/api/v1/ai/lineage/relationships")
def list_ai_lineage_relationships(
    expected: bool | None = None,
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    statement = select(AIResourceRelationship).where(
        AIResourceRelationship.tenant_id == principal.tenant_id
    )
    if expected is not None:
        statement = statement.where(AIResourceRelationship.expected == expected)
    if status:
        statement = statement.where(AIResourceRelationship.status == status)
    rows = db.scalars(
        statement.order_by(AIResourceRelationship.updated_at.desc()).limit(limit)
    )
    return [relationship_response(row) for row in rows]


@router.post("/api/v1/ai/lineage/observations")
def create_ai_lineage_observation(
    req: AILineageObservationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    try:
        observation, relationship, idempotent = observe_relationship(
            db,
            principal.tenant_id,
            req.event_id,
            req.source.model_dump(),
            req.relationship,
            req.target.model_dump(),
            req.observed_at,
            req.metadata,
            principal.subject,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "AI lineage observation already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "idempotent": idempotent,
        "observation": observation_response(observation),
        "relationship": relationship_response(relationship),
    }


@router.get("/api/v1/ai/lineage/drift")
def list_ai_lineage_drift(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    rows = db.scalars(
        select(AILineageObservation)
        .where(
            AILineageObservation.tenant_id == principal.tenant_id,
            AILineageObservation.drift_detected.is_(True),
        )
        .order_by(AILineageObservation.observed_at.desc())
        .limit(limit)
    )
    return [observation_response(row) for row in rows]


def _evaluation_request(payload: dict) -> AuthZENEvaluationRequest:
    try:
        return AuthZENEvaluationRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(400, "Invalid Access Evaluation request") from exc


def _resolved_evaluation(request: AuthZENEvaluationsRequest, item):
    subject = item.subject if item and item.subject is not None else request.subject
    resource = item.resource if item and item.resource is not None else request.resource
    action = item.action if item and item.action is not None else request.action
    context = item.context if item and item.context is not None else request.context
    if not subject or not resource or not action:
        raise HTTPException(
            400,
            "Each access evaluation requires subject, resource, and action",
        )
    try:
        return AuthZENEvaluationRequest.model_validate(
            {
                "subject": subject.model_dump(),
                "resource": resource.model_dump(),
                "action": action.model_dump(),
                "context": context or {},
            }
        )
    except ValidationError as exc:
        raise HTTPException(400, "Invalid nested Access Evaluation request") from exc


def _bounded_header(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not value or len(value) > 160 or any(ord(character) < 32 for character in value):
        raise HTTPException(400, f"{name} is invalid")
    return value


def _indexed_header(value: str | None, index: int) -> str | None:
    if value is None:
        return None
    suffix = f":{index}"
    return f"{value[: 160 - len(suffix)]}{suffix}"


def _receipt(
    db: Session,
    tenant_id: str,
    receipt_id: str,
) -> RuntimeDecisionReceipt | None:
    return db.scalar(
        select(RuntimeDecisionReceipt).where(
            RuntimeDecisionReceipt.tenant_id == tenant_id,
            RuntimeDecisionReceipt.receipt_id == receipt_id,
        )
    )


def _ai_resource(
    db: Session,
    tenant_id: str,
    resource_key: str,
) -> AIResource | None:
    return db.scalar(
        select(AIResource).where(
            AIResource.tenant_id == tenant_id,
            AIResource.resource_key == resource_key,
        )
    )
