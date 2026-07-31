import csv
import io
import json
import re
from xml.sax.saxutils import escape

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, require_role
from app.config import settings
from app.database import get_db
from app.models import (
    EvidenceDisposition,
    EvidenceRecord,
    IdentityDeprovisionWorkflow,
    IntegrationDelivery,
    PolicyApproverDelegation,
    PolicyBundle,
    PolicyException,
    SCIMResource,
    utc_now,
)
from app.schemas import (
    EvidenceDispositionCreate,
    IntegrationReplayRequest,
    PolicyApproverDelegationCreate,
    PolicyExceptionRenewalRequest,
)
from app.services.evidence import (
    approve_disposition,
    create_disposition,
    disposition_response,
    reject_disposition,
    verify_object_lock,
)
from app.services.graph import explain_paths, export_graph_edges
from app.services.identity import (
    create_resource,
    deprovision_response,
    patch_resource,
    replace_resource,
    request_deprovision,
    resource_response,
    scim_principal,
)
from app.services.integrations import delivery_dashboard, replay_delivery
from app.services.jobs import enqueue_job
from app.services.policy_governance import (
    approve_exception_renewal,
    can_approve_exception,
    compare_policy_bundles,
    create_delegation,
    delegation_response,
    previous_policy_bundle,
    request_exception_renewal,
)


router = APIRouter()
SCIM_BULK_REQUEST = "urn:ietf:params:scim:api:messages:2.0:BulkRequest"
SCIM_BULK_RESPONSE = "urn:ietf:params:scim:api:messages:2.0:BulkResponse"


@router.post("/scim/v2/Bulk")
def scim_bulk(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(scim_principal),
):
    if len(json.dumps(payload).encode()) > 1024 * 1024:
        raise HTTPException(413, "SCIM Bulk payload exceeds 1 MiB")
    schemas = payload.get("schemas", [SCIM_BULK_REQUEST])
    if not isinstance(schemas, list) or SCIM_BULK_REQUEST not in schemas:
        raise HTTPException(400, "SCIM Bulk request schema is required")
    operations = payload.get("Operations")
    if not isinstance(operations, list) or not operations:
        raise HTTPException(400, "SCIM Bulk requires an Operations array")
    if len(operations) > settings.scim_bulk_max_operations:
        raise HTTPException(413, "SCIM Bulk operation limit exceeded")
    fail_on_errors = payload.get("failOnErrors", 0)
    if not isinstance(fail_on_errors, int) or fail_on_errors < 0:
        raise HTTPException(400, "SCIM Bulk failOnErrors must be a non-negative integer")
    bulk_ids: dict[str, str] = {}
    responses = []
    errors = 0
    for operation in operations:
        try:
            result = _execute_scim_bulk_operation(db, principal, operation, bulk_ids)
        except ValueError as exc:
            result = {
                "method": str(operation.get("method", "")).upper(),
                "bulkId": operation.get("bulkId"),
                "status": "400",
                "response": {"detail": str(exc)},
            }
        responses.append({key: value for key, value in result.items() if value is not None})
        if int(result["status"]) >= 400:
            errors += 1
        if fail_on_errors and errors >= fail_on_errors:
            break
    return {"schemas": [SCIM_BULK_RESPONSE], "Operations": responses}


@router.get("/api/v1/identity/deprovisioning")
def list_identity_deprovisioning(
    status: str | None = Query(default=None, pattern="^(pending|running|completed|failed)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(IdentityDeprovisionWorkflow).where(
        IdentityDeprovisionWorkflow.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(IdentityDeprovisionWorkflow.status == status)
    workflows = db.scalars(
        statement.order_by(IdentityDeprovisionWorkflow.requested_at.desc()).limit(limit)
    )
    return [deprovision_response(workflow) for workflow in workflows]


@router.get("/api/v1/integrations/dashboard")
def integration_delivery_dashboard(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    return delivery_dashboard(db, principal.tenant_id)


@router.post("/api/v1/integrations/deliveries/{delivery_id}/replay", status_code=202)
def replay_integration_delivery(
    delivery_id: str,
    req: IntegrationReplayRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    try:
        delivery = replay_delivery(
            db,
            principal.tenant_id,
            delivery_id,
            principal.subject,
            req.reason,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _delivery_response(delivery)


@router.get("/api/v1/policy/bundles/{bundle_id}/diff")
def policy_bundle_diff(
    bundle_id: str,
    against_bundle_id: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    bundle = _policy_bundle(db, principal.tenant_id, bundle_id)
    if not bundle:
        raise HTTPException(404, "Policy bundle not found")
    if against_bundle_id:
        previous = _policy_bundle(db, principal.tenant_id, against_bundle_id)
        if not previous:
            raise HTTPException(404, "Comparison policy bundle not found")
    else:
        previous = previous_policy_bundle(db, principal.tenant_id, bundle)
    return compare_policy_bundles(bundle, previous)


@router.post("/api/v1/policy/approver-delegations", status_code=201)
def create_policy_approver_delegation(
    req: PolicyApproverDelegationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    try:
        delegation = create_delegation(
            db,
            principal.tenant_id,
            req.subject,
            req.bundle_name,
            req.can_approve_bundles,
            req.can_approve_exceptions,
            req.expires_at,
            principal.subject,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return delegation_response(delegation)


@router.get("/api/v1/policy/approver-delegations")
def list_policy_approver_delegations(
    active: bool | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(PolicyApproverDelegation).where(
        PolicyApproverDelegation.tenant_id == principal.tenant_id
    )
    if active is not None:
        statement = statement.where(PolicyApproverDelegation.active == active)
    delegations = db.scalars(statement.order_by(PolicyApproverDelegation.created_at.desc()))
    return [delegation_response(delegation) for delegation in delegations]


@router.delete("/api/v1/policy/approver-delegations/{delegation_id}", status_code=204)
def revoke_policy_approver_delegation(
    delegation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    delegation = db.scalar(
        select(PolicyApproverDelegation).where(
            PolicyApproverDelegation.tenant_id == principal.tenant_id,
            PolicyApproverDelegation.delegation_id == delegation_id,
        )
    )
    if not delegation:
        raise HTTPException(404, "Policy approver delegation not found")
    delegation.active = False
    delegation.revoked_at = utc_now()
    db.commit()
    return Response(status_code=204)


@router.post("/api/v1/policy/exceptions/{exception_id}/renewal")
def request_policy_exception_renewal(
    exception_id: str,
    req: PolicyExceptionRenewalRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    exception = _policy_exception(db, principal.tenant_id, exception_id)
    if not exception:
        raise HTTPException(404, "Policy exception not found")
    try:
        exception = request_exception_renewal(
            db,
            exception,
            req.expires_at,
            req.reason,
            principal.subject,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _exception_renewal_response(exception)


@router.post("/api/v1/policy/exceptions/{exception_id}/renewal/approve")
def approve_policy_exception_renewal(
    exception_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    exception = _policy_exception(db, principal.tenant_id, exception_id)
    if not exception:
        raise HTTPException(404, "Policy exception not found")
    if not can_approve_exception(db, principal):
        raise HTTPException(403, "Exception renewal approval is not delegated to this identity")
    if (
        exception.renewal_requested_by == principal.subject
        and principal.subject != "development"
    ):
        raise HTTPException(409, "Exception renewal approval requires a different identity")
    try:
        exception = approve_exception_renewal(db, exception, principal.subject)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _exception_renewal_response(exception)


@router.post("/api/v1/evidence/{evidence_id}/verify-object-lock")
def verify_evidence_object_lock(
    evidence_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    record = _evidence_record(db, principal.tenant_id, evidence_id)
    if not record:
        raise HTTPException(404, "Evidence record not found")
    return verify_object_lock(db, record)


@router.post("/api/v1/evidence/{evidence_id}/dispositions", status_code=201)
def request_evidence_disposition(
    evidence_id: str,
    req: EvidenceDispositionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    record = _evidence_record(db, principal.tenant_id, evidence_id)
    if not record:
        raise HTTPException(404, "Evidence record not found")
    try:
        disposition = create_disposition(
            db,
            record,
            req.action,
            req.reason,
            principal.subject,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return disposition_response(disposition)


@router.get("/api/v1/evidence/dispositions")
def list_evidence_dispositions(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected|executed)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(EvidenceDisposition).where(
        EvidenceDisposition.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(EvidenceDisposition.status == status)
    dispositions = db.scalars(
        statement.order_by(EvidenceDisposition.requested_at.desc()).limit(limit)
    )
    return [disposition_response(disposition) for disposition in dispositions]


@router.post("/api/v1/evidence/dispositions/{disposition_id}/approve", status_code=202)
def approve_evidence_disposition(
    disposition_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    disposition = _evidence_disposition(db, principal.tenant_id, disposition_id)
    if not disposition:
        raise HTTPException(404, "Evidence disposition not found")
    try:
        disposition = approve_disposition(db, disposition, principal.subject)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    job = enqueue_job(
        db,
        tenant_id=principal.tenant_id,
        job_type="evidence.disposition",
        payload={"disposition_id": disposition.disposition_id},
        created_by=principal.subject,
        max_attempts=5,
    )
    return {"disposition": disposition_response(disposition), "job_id": job.job_id}


@router.post("/api/v1/evidence/dispositions/{disposition_id}/reject")
def reject_evidence_disposition(
    disposition_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    disposition = _evidence_disposition(db, principal.tenant_id, disposition_id)
    if not disposition:
        raise HTTPException(404, "Evidence disposition not found")
    try:
        disposition = reject_disposition(db, disposition, principal.subject)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return disposition_response(disposition)


@router.get("/api/v1/graph/paths")
def graph_path_explanations(
    source_type: str = Query(min_length=1, max_length=80),
    source_id: str = Query(min_length=1, max_length=320),
    target_type: str = Query(min_length=1, max_length=80),
    target_id: str = Query(min_length=1, max_length=320),
    max_depth: int = Query(default=5, ge=1, le=10),
    direction: str = Query(default="outbound", pattern="^(inbound|outbound|both)$"),
    max_paths: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    return explain_paths(
        db,
        principal.tenant_id,
        source_type,
        source_id,
        target_type,
        target_id,
        max_depth,
        direction,
        max_paths,
    )


@router.get("/api/v1/graph/export")
def export_graph(
    format: str = Query(default="json", pattern="^(json|csv|graphml)$"),
    relationships: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=10_000, ge=1, le=100_000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    relationship_set = {
        relationship.strip()
        for relationship in (relationships or "").split(",")
        if relationship.strip()
    }
    export_data = export_graph_edges(
        db,
        principal.tenant_id,
        relationship_set,
        limit,
    )
    if format == "json":
        return export_data
    if format == "csv":
        return _csv_graph_response(export_data)
    return _graphml_response(export_data)


def _execute_scim_bulk_operation(
    db: Session,
    principal: Principal,
    operation: dict,
    bulk_ids: dict[str, str],
) -> dict:
    if not isinstance(operation, dict):
        raise ValueError("SCIM Bulk operations must be objects")
    method = str(operation.get("method", "")).upper()
    match = re.fullmatch(r"/(Users|Groups)(?:/([^/]+))?", str(operation.get("path", "")))
    if method not in {"POST", "PUT", "PATCH", "DELETE"} or not match:
        raise ValueError("SCIM Bulk operation method or path is invalid")
    collection, resource_id = match.groups()
    resource_type = "User" if collection == "Users" else "Group"
    data = _resolve_bulk_ids(operation.get("data", {}), bulk_ids)
    bulk_id = operation.get("bulkId")
    if method == "POST":
        if resource_id:
            raise ValueError("SCIM Bulk POST paths cannot include a resource id")
        resource = create_resource(db, principal.tenant_id, resource_type, data)
        if bulk_id:
            if not isinstance(bulk_id, str) or bulk_id in bulk_ids:
                raise ValueError("SCIM Bulk bulkId must be unique")
            bulk_ids[bulk_id] = resource.resource_id
        return {
            "method": method,
            "bulkId": bulk_id,
            "status": "201",
            "location": f"/scim/v2/{collection}/{resource.resource_id}",
            "response": resource_response(resource),
        }
    if not resource_id:
        raise ValueError("SCIM Bulk operation requires a resource id")
    resource_id = _bulk_reference(resource_id, bulk_ids)
    resource = _scim_resource(db, principal.tenant_id, resource_type, resource_id)
    if not resource:
        return {"method": method, "bulkId": bulk_id, "status": "404"}
    if method == "PUT":
        was_active = resource.active
        resource = replace_resource(db, resource, data)
        if resource_type == "User" and was_active and not resource.active:
            request_deprovision(db, resource, principal.subject)
        status = "200"
    elif method == "PATCH":
        operations = data.get("Operations")
        if not isinstance(operations, list):
            raise ValueError("SCIM Bulk PATCH data requires Operations")
        was_active = resource.active
        resource = patch_resource(db, resource, operations)
        if resource_type == "User" and was_active and not resource.active:
            request_deprovision(db, resource, principal.subject)
        status = "200"
    else:
        if resource_type == "User":
            request_deprovision(db, resource, principal.subject)
        else:
            db.delete(resource)
            db.commit()
        return {"method": method, "bulkId": bulk_id, "status": "204"}
    return {
        "method": method,
        "bulkId": bulk_id,
        "status": status,
        "location": f"/scim/v2/{collection}/{resource.resource_id}",
        "response": resource_response(resource),
    }


def _resolve_bulk_ids(value, bulk_ids: dict[str, str]):
    if isinstance(value, str):
        return _bulk_reference(value, bulk_ids)
    if isinstance(value, list):
        return [_resolve_bulk_ids(item, bulk_ids) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_bulk_ids(item, bulk_ids) for key, item in value.items()}
    return value


def _bulk_reference(value: str, bulk_ids: dict[str, str]) -> str:
    if value.startswith("bulkId:"):
        bulk_id = value.removeprefix("bulkId:")
        if bulk_id not in bulk_ids:
            raise ValueError(f"SCIM Bulk reference is unresolved: {bulk_id}")
        return bulk_ids[bulk_id]
    return value


def _scim_resource(
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


def _policy_bundle(db: Session, tenant_id: str, bundle_id: str) -> PolicyBundle | None:
    return db.scalar(
        select(PolicyBundle).where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.bundle_id == bundle_id,
        )
    )


def _policy_exception(
    db: Session,
    tenant_id: str,
    exception_id: str,
) -> PolicyException | None:
    return db.scalar(
        select(PolicyException).where(
            PolicyException.tenant_id == tenant_id,
            PolicyException.exception_id == exception_id,
        )
    )


def _evidence_record(db: Session, tenant_id: str, evidence_id: str) -> EvidenceRecord | None:
    return db.scalar(
        select(EvidenceRecord).where(
            EvidenceRecord.tenant_id == tenant_id,
            EvidenceRecord.evidence_id == evidence_id,
        )
    )


def _evidence_disposition(
    db: Session,
    tenant_id: str,
    disposition_id: str,
) -> EvidenceDisposition | None:
    return db.scalar(
        select(EvidenceDisposition).where(
            EvidenceDisposition.tenant_id == tenant_id,
            EvidenceDisposition.disposition_id == disposition_id,
        )
    )


def _delivery_response(delivery: IntegrationDelivery) -> dict:
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


def _exception_renewal_response(exception: PolicyException) -> dict:
    return {
        "exception_id": exception.exception_id,
        "expires_at": exception.expires_at,
        "renewal_status": exception.renewal_status,
        "renewal_requested_until": exception.renewal_requested_until,
        "renewal_requested_by": exception.renewal_requested_by,
        "renewal_requested_at": exception.renewal_requested_at,
        "renewal_reason": exception.renewal_reason,
        "renewed_by": exception.renewed_by,
        "renewed_at": exception.renewed_at,
    }


def _csv_graph_response(export_data: dict) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "source_type",
            "source_id",
            "relationship",
            "target_type",
            "target_id",
            "created_at",
            "metadata_json",
        ]
    )
    for edge in export_data["edges"]:
        writer.writerow(
            [
                edge["source"]["type"],
                edge["source"]["id"],
                edge["relationship"],
                edge["target"]["type"],
                edge["target"]["id"],
                edge["created_at"].isoformat(),
                json.dumps(edge["metadata"], sort_keys=True),
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=opendatagraph-graph.csv"},
    )


def _graphml_response(export_data: dict) -> Response:
    nodes = {}
    edges = []
    for edge in export_data["edges"]:
        source_key = f"{edge['source']['type']}:{edge['source']['id']}"
        target_key = f"{edge['target']['type']}:{edge['target']['id']}"
        nodes[source_key] = edge["source"]
        nodes[target_key] = edge["target"]
        edges.append((source_key, target_key, edge))
    node_ids = {key: f"n{index}" for index, key in enumerate(sorted(nodes), start=1)}
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '<key id="type" for="node" attr.name="type" attr.type="string"/>',
        '<key id="label" for="node" attr.name="label" attr.type="string"/>',
        '<key id="relationship" for="edge" attr.name="relationship" attr.type="string"/>',
        '<graph edgedefault="directed">',
    ]
    for key in sorted(nodes):
        node = nodes[key]
        parts.append(
            f'<node id="{node_ids[key]}"><data key="type">{escape(node["type"])}</data>'
            f'<data key="label">{escape(node["id"])}</data></node>'
        )
    for index, (source_key, target_key, edge) in enumerate(edges, start=1):
        parts.append(
            f'<edge id="e{index}" source="{node_ids[source_key]}" target="{node_ids[target_key]}">'
            f'<data key="relationship">{escape(edge["relationship"])}</data></edge>'
        )
    parts.extend(["</graph>", "</graphml>"])
    return Response(
        "\n".join(parts),
        media_type="application/graphml+xml",
        headers={"Content-Disposition": "attachment; filename=opendatagraph-graph.graphml"},
    )
