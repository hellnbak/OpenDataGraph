from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal, require_role
from app.database import get_db
from app.models import (
    ConnectorCapabilityPolicy,
    OwnershipEscalationEvent,
    OwnershipEscalationPolicy,
)
from app.schemas import (
    ConnectorCapabilityPolicyUpdate,
    GovernanceEvidencePackageVerify,
    OwnershipEscalationPolicyCreate,
    OwnershipEscalationPolicyUpdate,
)
from app.services.evidence_packages import (
    evidence_package_for_tenant,
    verify_stored_evidence_package,
)
from app.services.evidence_signing import signing_configuration
from app.services.workload_exchange import (
    test_workload_exchange,
    workload_exchange_configuration,
)
from app.services.ownership import (
    create_escalation_policy,
    escalation_policy_response,
    ownership_trends,
    update_escalation_policy,
)
from connectors.registry import (
    connector_manifests,
    connector_policy,
    connector_policy_response,
    evaluate_connector_policy,
    set_connector_policy,
)


router = APIRouter()


@router.post("/api/v1/ownership/escalation-policies", status_code=201)
def create_ownership_escalation_policy(
    req: OwnershipEscalationPolicyCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    try:
        policy = create_escalation_policy(
            db,
            principal.tenant_id,
            req.name,
            req.description,
            [stage.model_dump() for stage in req.stages],
            req.enabled,
            principal.subject,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ownership escalation policy name already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return escalation_policy_response(policy)


@router.get("/api/v1/ownership/escalation-policies")
def list_ownership_escalation_policies(
    enabled: bool | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(OwnershipEscalationPolicy).where(
        OwnershipEscalationPolicy.tenant_id == principal.tenant_id
    )
    if enabled is not None:
        statement = statement.where(OwnershipEscalationPolicy.enabled == enabled)
    policies = db.scalars(
        statement.order_by(OwnershipEscalationPolicy.created_at.desc())
    )
    return [escalation_policy_response(policy) for policy in policies]


@router.patch("/api/v1/ownership/escalation-policies/{policy_id}")
def update_ownership_escalation_policy(
    policy_id: str,
    req: OwnershipEscalationPolicyUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    policy = _ownership_escalation_policy(db, principal.tenant_id, policy_id)
    if not policy:
        raise HTTPException(404, "Ownership escalation policy not found")
    changes = req.model_dump(exclude_none=True)
    if "stages" in changes:
        changes["stages"] = [
            stage.model_dump() if hasattr(stage, "model_dump") else stage
            for stage in changes["stages"]
        ]
    try:
        return escalation_policy_response(update_escalation_policy(db, policy, changes))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/v1/ownership/escalation-events")
def list_ownership_escalation_events(
    status: str | None = Query(default=None, pattern="^(pending|running|queued|failed)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(OwnershipEscalationEvent).where(
        OwnershipEscalationEvent.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(OwnershipEscalationEvent.status == status)
    events = db.scalars(
        statement.order_by(OwnershipEscalationEvent.triggered_at.desc()).limit(limit)
    )
    return [_ownership_escalation_event_response(event) for event in events]


@router.get("/api/v1/ownership/analytics/trends")
def get_ownership_analytics_trends(
    days: int = Query(default=90, ge=1, le=366),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    return ownership_trends(db, principal.tenant_id, days)


@router.get("/api/v1/workload-identity/exchange-profiles")
def list_workload_exchange_profiles(
    principal: Principal = Depends(require_role("auditor")),
):
    del principal
    return workload_exchange_configuration()


@router.post("/api/v1/workload-identity/exchange-profiles/{profile_name}/test")
def test_workload_exchange_profile(
    profile_name: str,
    principal: Principal = Depends(require_role("administrator")),
):
    del principal
    try:
        return test_workload_exchange(profile_name)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/v1/governance/evidence-signing")
def governance_evidence_signing_configuration(
    principal: Principal = Depends(require_role("auditor")),
):
    del principal
    return signing_configuration()


@router.post("/api/v1/governance/evidence-packages/{package_id}/verify")
def verify_governance_evidence_package(
    package_id: str,
    req: GovernanceEvidencePackageVerify,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    record = evidence_package_for_tenant(db, principal.tenant_id, package_id)
    if not record:
        raise HTTPException(404, "Governance evidence package not found")
    try:
        return verify_stored_evidence_package(record, req.verification_profile)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/v1/connectors/capabilities")
def list_connector_capabilities(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    policy, version = connector_policy(db, principal.tenant_id)
    return {
        "policy_version": version,
        "connectors": [
            {
                "manifest": manifest.as_dict(),
                "manifest_digest": manifest.digest(),
                "policy": evaluate_connector_policy(manifest, policy),
            }
            for manifest in connector_manifests()
        ],
    }


@router.get("/api/v1/connectors/capability-policy")
def get_connector_capability_policy(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    record = db.scalar(
        select(ConnectorCapabilityPolicy).where(
            ConnectorCapabilityPolicy.tenant_id == principal.tenant_id
        )
    )
    policy, _version = connector_policy(db, principal.tenant_id)
    return connector_policy_response(record, policy)


@router.put("/api/v1/connectors/capability-policy")
def update_connector_capability_policy(
    req: ConnectorCapabilityPolicyUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    try:
        record = set_connector_policy(
            db,
            principal.tenant_id,
            req.model_dump(),
            principal.subject,
        )
        policy, _version = connector_policy(db, principal.tenant_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return connector_policy_response(record, policy)


def _ownership_escalation_policy(
    db: Session,
    tenant_id: str,
    policy_id: str,
) -> OwnershipEscalationPolicy | None:
    return db.scalar(
        select(OwnershipEscalationPolicy).where(
            OwnershipEscalationPolicy.tenant_id == tenant_id,
            OwnershipEscalationPolicy.policy_id == policy_id,
        )
    )


def _ownership_escalation_event_response(event: OwnershipEscalationEvent) -> dict:
    return {
        "event_id": event.event_id,
        "campaign_id": event.campaign_id,
        "policy_id": event.policy_id,
        "stage_key": event.stage_key,
        "offset_hours": event.offset_hours,
        "recipient": event.recipient,
        "status": event.status,
        "attempts": event.attempts,
        "assignment_count": event.assignment_count,
        "delivery_count": event.delivery_count,
        "error": event.error,
        "triggered_at": event.triggered_at,
        "queued_at": event.queued_at,
    }
