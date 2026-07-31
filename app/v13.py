import json
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal, require_role
from app.config import settings
from app.database import get_db
from app.models import (
    ConnectorSchedule,
    EvidenceRecord,
    IntegrationDelivery,
    IntegrationEndpoint,
    PolicyBundle,
    PolicyException,
    ProviderRateLimit,
    SCIMResource,
    utc_now,
)
from app.schemas import (
    ConnectorScheduleCreate,
    ConnectorScheduleUpdate,
    EvidenceGovernanceUpdate,
    IntegrationEndpointCreate,
    PolicyBundleCreate,
    PolicyExceptionCreate,
    ProviderRateLimitUpdate,
)
from app.services.evidence import delete_evidence
from app.services.graph import ingest_openlineage_event, query_graph
from app.services.governance import complete_review_task, create_review_task
from app.services.identity import (
    create_resource,
    filter_resources,
    list_response,
    patch_resource,
    replace_resource,
    request_deprovision,
    resource_response,
    scim_principal,
)
from app.services.schedules import (
    configure_provider_budget,
    create_schedule,
    next_cron_run,
    skip_maintenance,
    validate_schedule_definition,
)
from app.services.jobs import enqueue_job
from app.services.integrations import create_endpoint, queue_integration_event
from app.services.policy_governance import can_approve_bundle
from app.services.policy_engine import validate_policy_definitions


router = APIRouter()


@router.post("/api/v1/connectors/schedules", status_code=201)
def create_connector_schedule(
    req: ConnectorScheduleCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    payload = req.model_dump(
        exclude={"connector_type", "account", "interval_seconds", "enabled"},
        exclude_none=True,
    )
    try:
        schedule = create_schedule(
            db,
            principal.tenant_id,
            req.connector_type,
            req.account,
            req.interval_seconds,
            payload,
            principal.subject,
            req.enabled,
            req.schedule_type,
            req.cron_expression,
            req.timezone,
            req.maintenance_windows,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _schedule_response(schedule)


@router.get("/api/v1/connectors/schedules")
def list_connector_schedules(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    schedules = db.scalars(
        select(ConnectorSchedule)
        .where(ConnectorSchedule.tenant_id == principal.tenant_id)
        .order_by(ConnectorSchedule.created_at.desc())
    )
    return [_schedule_response(schedule) for schedule in schedules]


@router.patch("/api/v1/connectors/schedules/{schedule_id}")
def update_connector_schedule(
    schedule_id: str,
    req: ConnectorScheduleUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    schedule = _schedule_for_tenant(db, schedule_id, principal.tenant_id)
    if not schedule:
        raise HTTPException(404, "Connector schedule not found")
    changes = req.model_dump(exclude_none=True)
    maintenance_windows = changes.pop(
        "maintenance_windows",
        json.loads(schedule.maintenance_windows_json or "[]"),
    )
    if changes.get("schedule_type") == "interval":
        changes["cron_expression"] = None
    for field, value in changes.items():
        setattr(schedule, field, value.replace(tzinfo=None) if field == "next_run_at" else value)
    try:
        validate_schedule_definition(
            schedule.schedule_type,
            schedule.interval_seconds,
            schedule.cron_expression,
            schedule.timezone,
            maintenance_windows,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    schedule.maintenance_windows_json = json.dumps(maintenance_windows)
    cadence_fields = {
        "schedule_type",
        "interval_seconds",
        "cron_expression",
        "timezone",
        "maintenance_windows",
    }
    if req.next_run_at is None and cadence_fields & req.model_fields_set:
        schedule.next_run_at = (
            next_cron_run(
                schedule.cron_expression or "",
                schedule.timezone,
                utc_now(),
                maintenance_windows,
            )
            if schedule.schedule_type == "cron"
            else skip_maintenance(utc_now(), schedule.timezone, maintenance_windows)
        )
    elif req.enabled is True and req.next_run_at is None and schedule.next_run_at < utc_now():
        schedule.next_run_at = utc_now()
    schedule.updated_at = utc_now()
    db.commit()
    db.refresh(schedule)
    return _schedule_response(schedule)


@router.delete("/api/v1/connectors/schedules/{schedule_id}", status_code=204)
def delete_connector_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    schedule = _schedule_for_tenant(db, schedule_id, principal.tenant_id)
    if not schedule:
        raise HTTPException(404, "Connector schedule not found")
    db.delete(schedule)
    db.commit()
    return Response(status_code=204)


@router.get("/api/v1/connectors/rate-limits")
def list_provider_rate_limits(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    budgets = db.scalars(
        select(ProviderRateLimit)
        .where(ProviderRateLimit.tenant_id == principal.tenant_id)
        .order_by(ProviderRateLimit.provider)
    )
    return [_rate_limit_response(budget) for budget in budgets]


@router.put("/api/v1/connectors/rate-limits/{provider}")
def update_provider_rate_limit(
    provider: str,
    req: ProviderRateLimitUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    if provider not in {"aws-s3", "google-drive", "github", "gitlab", "sharepoint"}:
        raise HTTPException(404, "Unsupported connector provider")
    return _rate_limit_response(
        configure_provider_budget(
            db,
            principal.tenant_id,
            provider,
            req.max_requests,
            req.window_seconds,
        )
    )


@router.patch("/api/v1/evidence/{evidence_id}/governance")
def update_evidence_governance(
    evidence_id: str,
    req: EvidenceGovernanceUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    record = _evidence_for_tenant(db, evidence_id, principal.tenant_id)
    if not record:
        raise HTTPException(404, "Evidence record not found")
    if record.deleted_at:
        raise HTTPException(409, "Deleted evidence governance cannot be changed")
    if req.retention_until is not None:
        record.retention_until = req.retention_until.replace(tzinfo=None)
    if req.legal_hold is not None:
        record.legal_hold = req.legal_hold
    metadata = json.loads(record.metadata_json or "{}")
    metadata["governance_reason"] = req.reason
    metadata["governance_updated_by"] = principal.subject
    metadata["governance_updated_at"] = utc_now().isoformat()
    record.metadata_json = json.dumps(metadata)
    db.commit()
    db.refresh(record)
    return _evidence_governance_response(record)


@router.delete("/api/v1/evidence/{evidence_id}", status_code=204)
def delete_evidence_record(
    evidence_id: str,
    reason: str = Query(min_length=3, max_length=2000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    record = _evidence_for_tenant(db, evidence_id, principal.tenant_id)
    if not record:
        raise HTTPException(404, "Evidence record not found")
    if record.deleted_at:
        return Response(status_code=204)
    if settings.evidence_disposition_approval_required:
        raise HTTPException(409, "Evidence deletion requires an approved disposition")
    if record.legal_hold:
        raise HTTPException(409, "Evidence under legal hold cannot be deleted")
    try:
        delete_evidence(record.storage_uri)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(503, f"Evidence deletion failed: {exc}") from exc
    record.deleted_at = utc_now()
    record.deleted_by = principal.subject
    record.deletion_reason = reason
    db.commit()
    return Response(status_code=204)


@router.post("/api/v1/evidence/retention/jobs", status_code=202)
def enqueue_evidence_retention(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    return enqueue_job(
        db,
        tenant_id=principal.tenant_id,
        job_type="evidence.retention",
        payload={"limit": limit},
        created_by=principal.subject,
    )


@router.post("/api/v1/policy/bundles", status_code=201)
def create_policy_bundle(
    req: PolicyBundleCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    try:
        validate_policy_definitions(req.policies)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    definition_json = json.dumps(req.policies)
    if len(definition_json.encode()) > 262_144:
        raise HTTPException(413, "Policy bundle exceeds 256 KiB")
    bundle = PolicyBundle(
        tenant_id=principal.tenant_id,
        bundle_id=str(uuid4()),
        name=req.name,
        version=req.version,
        definition_json=definition_json,
        created_by=principal.subject,
    )
    db.add(bundle)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Policy bundle name and version already exist") from exc
    db.refresh(bundle)
    return _policy_bundle_response(bundle)


@router.get("/api/v1/policy/bundles")
def list_policy_bundles(
    status: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(PolicyBundle).where(PolicyBundle.tenant_id == principal.tenant_id)
    if status:
        statement = statement.where(PolicyBundle.status == status)
    bundles = db.scalars(statement.order_by(PolicyBundle.name, PolicyBundle.version.desc()))
    return [_policy_bundle_response(bundle) for bundle in bundles]


@router.post("/api/v1/policy/bundles/{bundle_id}/submit")
def submit_policy_bundle(
    bundle_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    bundle = _policy_bundle_for_tenant(db, bundle_id, principal.tenant_id)
    if not bundle:
        raise HTTPException(404, "Policy bundle not found")
    if bundle.status != "draft":
        raise HTTPException(409, "Only draft bundles can be submitted")
    bundle.status = "pending"
    bundle.submitted_at = utc_now()
    db.commit()
    db.refresh(bundle)
    create_review_task(
        db,
        principal.tenant_id,
        "policy-approval",
        bundle.bundle_id,
        f"Approve policy bundle {bundle.name} v{bundle.version}",
        principal.subject,
        {"bundle_name": bundle.name, "bundle_version": bundle.version},
        priority="high",
    )
    return _policy_bundle_response(bundle)


@router.post("/api/v1/policy/bundles/{bundle_id}/approve")
def approve_policy_bundle(
    bundle_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    bundle = _policy_bundle_for_tenant(db, bundle_id, principal.tenant_id)
    if not bundle:
        raise HTTPException(404, "Policy bundle not found")
    if bundle.status != "pending":
        raise HTTPException(409, "Only pending bundles can be approved")
    if not can_approve_bundle(db, principal, bundle):
        raise HTTPException(403, "Policy bundle approval is not delegated to this identity")
    if bundle.created_by == principal.subject and principal.subject != "development":
        raise HTTPException(409, "Policy approval requires a different identity")
    bundle.status = "approved"
    bundle.approved_by = principal.subject
    bundle.approved_at = utc_now()
    db.commit()
    db.refresh(bundle)
    complete_review_task(
        db,
        principal.tenant_id,
        "policy-approval",
        bundle.bundle_id,
        principal.subject,
        "approved",
    )
    return _policy_bundle_response(bundle)


@router.post("/api/v1/policy/bundles/{bundle_id}/activate")
def activate_policy_bundle(
    bundle_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    bundle = _policy_bundle_for_tenant(db, bundle_id, principal.tenant_id)
    if not bundle:
        raise HTTPException(404, "Policy bundle not found")
    if bundle.status != "approved":
        raise HTTPException(409, "Only approved bundles can be activated")
    _activate_policy_bundle(db, bundle, principal.tenant_id)
    return _policy_bundle_response(bundle)


@router.post("/api/v1/policy/bundles/{bundle_id}/rollback")
def rollback_policy_bundle(
    bundle_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    bundle = _policy_bundle_for_tenant(db, bundle_id, principal.tenant_id)
    if not bundle:
        raise HTTPException(404, "Policy bundle not found")
    if bundle.status not in {"retired", "approved"}:
        raise HTTPException(409, "Rollback target must be retired or approved")
    _activate_policy_bundle(db, bundle, principal.tenant_id)
    return _policy_bundle_response(bundle)


@router.post("/api/v1/policy/exceptions", status_code=201)
def create_policy_exception(
    req: PolicyExceptionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    if not any((req.policy_id, req.agent_key, req.asset_id, req.destination, req.action, req.purpose)):
        raise HTTPException(400, "Policy exceptions require at least one scope")
    expires_at = req.expires_at.replace(tzinfo=None)
    if expires_at <= utc_now():
        raise HTTPException(400, "Policy exception expiry must be in the future")
    exception = PolicyException(
        tenant_id=principal.tenant_id,
        exception_id=str(uuid4()),
        policy_id=req.policy_id,
        agent_key=req.agent_key,
        asset_id=req.asset_id,
        destination=req.destination,
        action=req.action,
        purpose=req.purpose,
        override_decision=req.override_decision,
        reason=req.reason,
        controls_json=json.dumps(req.controls),
        expires_at=expires_at,
        created_by=principal.subject,
        approved_by=principal.subject,
    )
    db.add(exception)
    db.commit()
    db.refresh(exception)
    return _policy_exception_response(exception)


@router.get("/api/v1/policy/exceptions")
def list_policy_exceptions(
    active: bool | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(PolicyException).where(PolicyException.tenant_id == principal.tenant_id)
    if active is not None:
        statement = statement.where(PolicyException.active == active)
    exceptions = db.scalars(statement.order_by(PolicyException.created_at.desc()))
    return [_policy_exception_response(exception) for exception in exceptions]


@router.delete("/api/v1/policy/exceptions/{exception_id}", status_code=204)
def revoke_policy_exception(
    exception_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    exception = db.scalar(
        select(PolicyException).where(
            PolicyException.tenant_id == principal.tenant_id,
            PolicyException.exception_id == exception_id,
        )
    )
    if not exception:
        raise HTTPException(404, "Policy exception not found")
    exception.active = False
    exception.revoked_at = utc_now()
    db.commit()
    return Response(status_code=204)


@router.post("/api/v1/integrations", status_code=201)
def create_integration_endpoint(
    req: IntegrationEndpointCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    try:
        endpoint = create_endpoint(
            db,
            principal.tenant_id,
            req.name,
            req.mode,
            req.url,
            req.secret_ref,
            req.events,
            req.enabled,
            principal.subject,
            req.event_format,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Integration endpoint name already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _integration_endpoint_response(endpoint)


@router.get("/api/v1/integrations")
def list_integration_endpoints(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    endpoints = db.scalars(
        select(IntegrationEndpoint)
        .where(IntegrationEndpoint.tenant_id == principal.tenant_id)
        .order_by(IntegrationEndpoint.name)
    )
    return [_integration_endpoint_response(endpoint) for endpoint in endpoints]


@router.delete("/api/v1/integrations/{endpoint_id}", status_code=204)
def disable_integration_endpoint(
    endpoint_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    endpoint = _integration_endpoint_for_tenant(db, endpoint_id, principal.tenant_id)
    if not endpoint:
        raise HTTPException(404, "Integration endpoint not found")
    endpoint.enabled = False
    endpoint.updated_at = utc_now()
    db.commit()
    return Response(status_code=204)


@router.post("/api/v1/integrations/{endpoint_id}/test", status_code=202)
def test_integration_endpoint(
    endpoint_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    endpoint = _integration_endpoint_for_tenant(db, endpoint_id, principal.tenant_id)
    if not endpoint or not endpoint.enabled:
        raise HTTPException(404, "Enabled integration endpoint not found")
    deliveries = queue_integration_event(
        db,
        principal.tenant_id,
        "integration.test",
        {
            "test": True,
            "endpoint_id": endpoint.endpoint_id,
            "message": "OpenDataGraph integration test",
        },
        principal.subject,
        endpoint_ids={endpoint.endpoint_id},
    )
    if not deliveries:
        raise HTTPException(409, "Endpoint is not subscribed to integration.test")
    return {"delivery_id": deliveries[0].delivery_id, "status": deliveries[0].status}


@router.get("/api/v1/integrations/deliveries")
def list_integration_deliveries(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    deliveries = db.scalars(
        select(IntegrationDelivery)
        .where(IntegrationDelivery.tenant_id == principal.tenant_id)
        .order_by(IntegrationDelivery.created_at.desc())
        .limit(limit)
    )
    return [_integration_delivery_response(delivery) for delivery in deliveries]


@router.post("/api/v1/lineage/events", status_code=202)
def ingest_lineage_event(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    try:
        return ingest_openlineage_event(db, principal.tenant_id, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/v1/graph/query")
def advanced_graph_query(
    start_type: str = Query(min_length=1, max_length=80),
    start_id: str = Query(min_length=1, max_length=320),
    max_depth: int = Query(default=3, ge=1, le=10),
    direction: str = Query(default="both", pattern="^(inbound|outbound|both)$"),
    relationships: str | None = Query(default=None, max_length=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    relationship_set = {
        relationship.strip()
        for relationship in (relationships or "").split(",")
        if relationship.strip()
    }
    return query_graph(
        db,
        principal.tenant_id,
        start_type,
        start_id,
        max_depth,
        direction,
        relationship_set,
    )


@router.get("/scim/v2/{resource_collection}")
def list_scim_resources(
    resource_collection: str,
    filter: str | None = Query(default=None),
    start_index: int = Query(default=1, alias="startIndex", ge=1),
    count: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(scim_principal),
):
    resource_type = _resource_type(resource_collection)
    try:
        resources, total_results = filter_resources(
            db,
            principal.tenant_id,
            resource_type,
            filter,
            start_index,
            count,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return list_response(resources, start_index, total_results)


@router.post("/scim/v2/{resource_collection}", status_code=201)
def create_scim_resource(
    resource_collection: str,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(scim_principal),
):
    resource_type = _resource_type(resource_collection)
    try:
        resource = create_resource(db, principal.tenant_id, resource_type, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    response.headers["Location"] = f"/scim/v2/{resource_collection}/{resource.resource_id}"
    return resource_response(resource)


@router.get("/scim/v2/{resource_collection}/{resource_id}")
def get_scim_resource(
    resource_collection: str,
    resource_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(scim_principal),
):
    resource = _scim_resource_for_tenant(
        db,
        principal.tenant_id,
        _resource_type(resource_collection),
        resource_id,
    )
    if not resource:
        raise HTTPException(404, "SCIM resource not found")
    return resource_response(resource)


@router.put("/scim/v2/{resource_collection}/{resource_id}")
def replace_scim_resource(
    resource_collection: str,
    resource_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(scim_principal),
):
    resource = _scim_resource_for_tenant(
        db,
        principal.tenant_id,
        _resource_type(resource_collection),
        resource_id,
    )
    if not resource:
        raise HTTPException(404, "SCIM resource not found")
    was_active = resource.active
    try:
        resource = replace_resource(db, resource, payload)
        if resource.resource_type == "User" and was_active and not resource.active:
            request_deprovision(db, resource, principal.subject)
        return resource_response(resource)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/scim/v2/{resource_collection}/{resource_id}")
def patch_scim_resource(
    resource_collection: str,
    resource_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(scim_principal),
):
    resource = _scim_resource_for_tenant(
        db,
        principal.tenant_id,
        _resource_type(resource_collection),
        resource_id,
    )
    if not resource:
        raise HTTPException(404, "SCIM resource not found")
    operations = payload.get("Operations")
    if not isinstance(operations, list):
        raise HTTPException(400, "SCIM patch requires an Operations array")
    was_active = resource.active
    try:
        resource = patch_resource(db, resource, operations)
        if resource.resource_type == "User" and was_active and not resource.active:
            request_deprovision(db, resource, principal.subject)
        return resource_response(resource)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/scim/v2/{resource_collection}/{resource_id}", status_code=204)
def delete_scim_resource(
    resource_collection: str,
    resource_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(scim_principal),
):
    resource = _scim_resource_for_tenant(
        db,
        principal.tenant_id,
        _resource_type(resource_collection),
        resource_id,
    )
    if not resource:
        raise HTTPException(404, "SCIM resource not found")
    if resource.resource_type == "User":
        request_deprovision(db, resource, principal.subject)
        return Response(status_code=204)
    db.delete(resource)
    db.commit()
    return Response(status_code=204)


def _schedule_for_tenant(db: Session, schedule_id: str, tenant_id: str) -> ConnectorSchedule | None:
    return db.scalar(
        select(ConnectorSchedule).where(
            ConnectorSchedule.tenant_id == tenant_id,
            ConnectorSchedule.schedule_id == schedule_id,
        )
    )


def _schedule_response(schedule: ConnectorSchedule) -> dict:
    payload = json.loads(schedule.payload_json or "{}")
    payload.pop("secret_ref", None)
    return {
        "schedule_id": schedule.schedule_id,
        "tenant_id": schedule.tenant_id,
        "connector_type": schedule.connector_type,
        "account": schedule.account,
        "schedule_type": schedule.schedule_type,
        "interval_seconds": schedule.interval_seconds,
        "cron_expression": schedule.cron_expression,
        "timezone": schedule.timezone,
        "maintenance_windows": json.loads(schedule.maintenance_windows_json or "[]"),
        "enabled": schedule.enabled,
        "next_run_at": schedule.next_run_at,
        "last_enqueued_at": schedule.last_enqueued_at,
        "configuration": payload,
        "has_secret_ref": "secret_ref" in json.loads(schedule.payload_json or "{}"),
        "created_by": schedule.created_by,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


def _rate_limit_response(budget: ProviderRateLimit) -> dict:
    return {
        "provider": budget.provider,
        "max_requests": budget.max_requests,
        "window_seconds": budget.window_seconds,
        "used_requests": budget.used_requests,
        "window_started_at": budget.window_started_at,
        "window_ends_at": budget.window_started_at + timedelta(seconds=budget.window_seconds),
        "updated_at": budget.updated_at,
    }


def _evidence_for_tenant(db: Session, evidence_id: str, tenant_id: str) -> EvidenceRecord | None:
    return db.scalar(
        select(EvidenceRecord).where(
            EvidenceRecord.tenant_id == tenant_id,
            EvidenceRecord.evidence_id == evidence_id,
        )
    )


def _evidence_governance_response(record: EvidenceRecord) -> dict:
    return {
        "evidence_id": record.evidence_id,
        "retention_until": record.retention_until,
        "legal_hold": record.legal_hold,
        "deleted_at": record.deleted_at,
        "deleted_by": record.deleted_by,
        "deletion_reason": record.deletion_reason,
    }


def _policy_bundle_for_tenant(db: Session, bundle_id: str, tenant_id: str) -> PolicyBundle | None:
    return db.scalar(
        select(PolicyBundle).where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.bundle_id == bundle_id,
        )
    )


def _activate_policy_bundle(db: Session, bundle: PolicyBundle, tenant_id: str) -> None:
    now = utc_now()
    active = db.scalar(
        select(PolicyBundle).where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.status == "active",
        )
    )
    if active and active.id != bundle.id:
        active.status = "retired"
        active.retired_at = now
    bundle.status = "active"
    bundle.activated_at = now
    bundle.retired_at = None
    db.commit()
    db.refresh(bundle)


def _policy_bundle_response(bundle: PolicyBundle) -> dict:
    return {
        "bundle_id": bundle.bundle_id,
        "tenant_id": bundle.tenant_id,
        "name": bundle.name,
        "version": bundle.version,
        "status": bundle.status,
        "policies": json.loads(bundle.definition_json),
        "created_by": bundle.created_by,
        "approved_by": bundle.approved_by,
        "created_at": bundle.created_at,
        "submitted_at": bundle.submitted_at,
        "approved_at": bundle.approved_at,
        "activated_at": bundle.activated_at,
        "retired_at": bundle.retired_at,
    }


def _policy_exception_response(exception: PolicyException) -> dict:
    return {
        "exception_id": exception.exception_id,
        "policy_id": exception.policy_id,
        "agent_key": exception.agent_key,
        "asset_id": exception.asset_id,
        "destination": exception.destination,
        "action": exception.action,
        "purpose": exception.purpose,
        "override_decision": exception.override_decision,
        "reason": exception.reason,
        "controls": json.loads(exception.controls_json or "[]"),
        "expires_at": exception.expires_at,
        "active": exception.active,
        "created_by": exception.created_by,
        "approved_by": exception.approved_by,
        "created_at": exception.created_at,
        "revoked_at": exception.revoked_at,
        "renewal_status": exception.renewal_status,
        "renewal_requested_until": exception.renewal_requested_until,
        "renewal_requested_by": exception.renewal_requested_by,
        "renewal_requested_at": exception.renewal_requested_at,
        "renewal_reason": exception.renewal_reason,
        "renewed_by": exception.renewed_by,
        "renewed_at": exception.renewed_at,
    }


def _integration_endpoint_for_tenant(
    db: Session,
    endpoint_id: str,
    tenant_id: str,
) -> IntegrationEndpoint | None:
    return db.scalar(
        select(IntegrationEndpoint).where(
            IntegrationEndpoint.tenant_id == tenant_id,
            IntegrationEndpoint.endpoint_id == endpoint_id,
        )
    )


def _integration_endpoint_response(endpoint: IntegrationEndpoint) -> dict:
    return {
        "endpoint_id": endpoint.endpoint_id,
        "tenant_id": endpoint.tenant_id,
        "name": endpoint.name,
        "endpoint_type": endpoint.endpoint_type,
        "mode": endpoint.mode,
        "event_format": endpoint.event_format,
        "url": endpoint.url,
        "events": json.loads(endpoint.events_json or "[]"),
        "enabled": endpoint.enabled,
        "has_secret_ref": bool(endpoint.secret_ref),
        "created_by": endpoint.created_by,
        "created_at": endpoint.created_at,
        "updated_at": endpoint.updated_at,
    }


def _integration_delivery_response(delivery: IntegrationDelivery) -> dict:
    return {
        "delivery_id": delivery.delivery_id,
        "endpoint_id": delivery.endpoint_id,
        "event_type": delivery.event_type,
        "status": delivery.status,
        "attempts": delivery.attempts,
        "response_code": delivery.response_code,
        "error": delivery.error,
        "replayed_from": delivery.replayed_from,
        "last_attempted_at": delivery.last_attempted_at,
        "dead_lettered_at": delivery.dead_lettered_at,
        "created_at": delivery.created_at,
        "delivered_at": delivery.delivered_at,
    }


def _resource_type(collection: str) -> str:
    resource_type = {"Users": "User", "Groups": "Group"}.get(collection)
    if not resource_type:
        raise HTTPException(404, "Supported SCIM resources: Users, Groups")
    return resource_type


def _scim_resource_for_tenant(
    db: Session,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
) -> SCIMResource | None:
    return db.scalar(
        select(SCIMResource).where(
            SCIMResource.tenant_id == tenant_id,
            SCIMResource.resource_type == resource_type,
            SCIMResource.resource_id == resource_id,
        )
    )
