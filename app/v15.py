from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal, require_role
from app.database import get_db
from app.models import (
    CredentialRotation,
    GovernanceReviewTask,
    GraphExport,
    OwnershipAssignment,
    OwnershipCampaign,
    ServiceAccount,
    ServiceAccountCredential,
)
from app.schemas import (
    GovernanceTaskAssign,
    GraphExportCreate,
    OwnershipAttestation,
    OwnershipCampaignCreate,
    OwnershipRemediationUpdate,
    ServiceAccountCreate,
    ServiceAccountRotate,
)
from app.services.governance import (
    OPEN_STATUSES,
    assign_review_task,
    governance_sla_metrics,
    review_task_response,
)
from app.services.graph_exports import (
    CONTENT_TYPES,
    create_graph_export,
    graph_export_for_tenant,
    graph_export_response,
    load_graph_export,
)
from app.services.jobs import enqueue_job
from app.services.ownership import (
    assignment_response,
    attest_assignment,
    campaign_counts,
    campaign_response,
    create_campaign,
    launch_campaign,
    resolve_remediation,
    update_remediation,
)
from app.services.service_accounts import (
    complete_rotation,
    create_service_account,
    credential_response,
    disable_service_account,
    lifecycle_report,
    rotate_service_account,
    rotation_response,
    service_account_response,
)


router = APIRouter()


@router.post("/api/v1/service-accounts", status_code=201)
def create_automation_identity(
    req: ServiceAccountCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    try:
        account, credential, key = create_service_account(
            db,
            principal.tenant_id,
            req.name,
            req.description,
            req.owner,
            req.role,
            principal.subject,
            req.credential_days,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Service account name already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "service_account": service_account_response(account, [credential]),
        "key": key,
        "key_notice": "Store this key securely; it cannot be retrieved again.",
    }


@router.get("/api/v1/service-accounts")
def list_automation_identities(
    status: str | None = Query(default=None, pattern="^(active|disabled)$"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(ServiceAccount).where(
        ServiceAccount.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(ServiceAccount.status == status)
    accounts = db.scalars(statement.order_by(ServiceAccount.name))
    return [
        service_account_response(
            account,
            _credentials_for_account(db, principal.tenant_id, account.account_id),
        )
        for account in accounts
    ]


@router.get("/api/v1/service-accounts/lifecycle")
def service_account_lifecycle(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    return lifecycle_report(db, principal.tenant_id)


@router.get("/api/v1/service-accounts/{account_id}")
def get_automation_identity(
    account_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    account = _service_account(db, principal.tenant_id, account_id)
    if not account:
        raise HTTPException(404, "Service account not found")
    return service_account_response(
        account,
        _credentials_for_account(db, principal.tenant_id, account.account_id),
    )


@router.post("/api/v1/service-accounts/{account_id}/rotate", status_code=201)
def rotate_automation_identity(
    account_id: str,
    req: ServiceAccountRotate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    account = _service_account(db, principal.tenant_id, account_id)
    if not account:
        raise HTTPException(404, "Service account not found")
    try:
        rotation, credential, key = rotate_service_account(
            db,
            account,
            principal.subject,
            req.grace_hours,
            req.credential_days,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "rotation": rotation_response(rotation),
        "credential": credential_response(credential),
        "key": key,
        "key_notice": "Store this key securely; it cannot be retrieved again.",
    }


@router.post("/api/v1/service-accounts/rotations/{rotation_id}/complete")
def complete_credential_rotation(
    rotation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    rotation = db.scalar(
        select(CredentialRotation).where(
            CredentialRotation.tenant_id == principal.tenant_id,
            CredentialRotation.rotation_id == rotation_id,
        )
    )
    if not rotation:
        raise HTTPException(404, "Credential rotation not found")
    try:
        return rotation_response(complete_rotation(db, rotation))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/api/v1/service-accounts/{account_id}", status_code=204)
def disable_automation_identity(
    account_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    account = _service_account(db, principal.tenant_id, account_id)
    if not account:
        raise HTTPException(404, "Service account not found")
    disable_service_account(db, account)
    return Response(status_code=204)


@router.get("/api/v1/governance/reviews")
def list_governance_reviews(
    status: str | None = Query(
        default=None,
        pattern="^(open|in-progress|completed)$",
    ),
    task_type: str | None = Query(default=None, max_length=80),
    assigned_to: str | None = Query(default=None, max_length=320),
    overdue: bool | None = None,
    limit: int = Query(default=250, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(GovernanceReviewTask).where(
        GovernanceReviewTask.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(GovernanceReviewTask.status == status)
    if task_type:
        statement = statement.where(GovernanceReviewTask.task_type == task_type)
    if assigned_to:
        statement = statement.where(GovernanceReviewTask.assigned_to == assigned_to)
    if overdue is True:
        from app.models import utc_now

        statement = statement.where(
            GovernanceReviewTask.status.in_(OPEN_STATUSES),
            GovernanceReviewTask.due_at < utc_now(),
        )
    tasks = db.scalars(statement.order_by(GovernanceReviewTask.due_at).limit(limit))
    return [review_task_response(task) for task in tasks]


@router.patch("/api/v1/governance/reviews/{task_id}/assign")
def assign_governance_review(
    task_id: str,
    req: GovernanceTaskAssign,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    task = _governance_task(db, principal.tenant_id, task_id)
    if not task:
        raise HTTPException(404, "Governance review task not found")
    try:
        return review_task_response(assign_review_task(db, task, req.assigned_to))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/v1/governance/sla")
def governance_service_levels(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    return governance_sla_metrics(db, principal.tenant_id)


@router.post("/api/v1/governance/notifications/jobs", status_code=202)
def enqueue_governance_notifications(
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    return enqueue_job(
        db,
        principal.tenant_id,
        "governance.sla-notify",
        {"limit": limit},
        principal.subject,
    )


@router.post("/api/v1/ownership/campaigns", status_code=201)
def create_ownership_campaign(
    req: OwnershipCampaignCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    try:
        campaign = create_campaign(
            db,
            principal.tenant_id,
            req.name,
            req.description,
            req.scope,
            req.due_at,
            principal.subject,
            escalation_policy_id=req.escalation_policy_id,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ownership campaign name already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return campaign_response(campaign)


@router.get("/api/v1/ownership/campaigns")
def list_ownership_campaigns(
    status: str | None = Query(default=None, pattern="^(draft|active|completed)$"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(OwnershipCampaign).where(
        OwnershipCampaign.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(OwnershipCampaign.status == status)
    campaigns = db.scalars(statement.order_by(OwnershipCampaign.created_at.desc()))
    return [
        campaign_response(
            campaign,
            campaign_counts(db, principal.tenant_id, campaign.campaign_id),
        )
        for campaign in campaigns
    ]


@router.get("/api/v1/ownership/campaigns/{campaign_id}")
def get_ownership_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    campaign = _campaign(db, principal.tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(404, "Ownership campaign not found")
    return campaign_response(
        campaign,
        campaign_counts(db, principal.tenant_id, campaign.campaign_id),
    )


@router.post("/api/v1/ownership/campaigns/{campaign_id}/launch")
def launch_ownership_attestations(
    campaign_id: str,
    max_assets: int = Query(default=10_000, ge=1, le=100_000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    campaign = _campaign(db, principal.tenant_id, campaign_id)
    if not campaign:
        raise HTTPException(404, "Ownership campaign not found")
    try:
        campaign, assignment_count = launch_campaign(db, campaign, max_assets)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    response = campaign_response(
        campaign,
        campaign_counts(db, principal.tenant_id, campaign.campaign_id),
    )
    response["assignment_count"] = assignment_count
    return response


@router.get("/api/v1/ownership/campaigns/{campaign_id}/assignments")
def list_ownership_assignments(
    campaign_id: str,
    status: str | None = Query(
        default=None,
        pattern="^(pending|attested|remediation-required|resolved)$",
    ),
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    if not _campaign(db, principal.tenant_id, campaign_id):
        raise HTTPException(404, "Ownership campaign not found")
    statement = select(OwnershipAssignment).where(
        OwnershipAssignment.tenant_id == principal.tenant_id,
        OwnershipAssignment.campaign_id == campaign_id,
    )
    if status:
        statement = statement.where(OwnershipAssignment.status == status)
    assignments = db.scalars(
        statement.order_by(OwnershipAssignment.created_at).limit(limit)
    )
    return [assignment_response(assignment) for assignment in assignments]


@router.post("/api/v1/ownership/assignments/{assignment_id}/attest")
def attest_catalog_ownership(
    assignment_id: str,
    req: OwnershipAttestation,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    assignment = _assignment(db, principal.tenant_id, assignment_id)
    if not assignment:
        raise HTTPException(404, "Ownership assignment not found")
    try:
        assignment = attest_assignment(
            db,
            assignment,
            req.confirmed,
            principal.subject,
            req.owner,
            req.note,
            req.remediation_action,
            req.remediation_due_at,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return assignment_response(assignment)


@router.patch("/api/v1/ownership/assignments/{assignment_id}/remediation")
def update_catalog_ownership_remediation(
    assignment_id: str,
    req: OwnershipRemediationUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    assignment = _assignment(db, principal.tenant_id, assignment_id)
    if not assignment:
        raise HTTPException(404, "Ownership assignment not found")
    try:
        return assignment_response(
            update_remediation(db, assignment, req.action, req.due_at)
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/api/v1/ownership/assignments/{assignment_id}/resolve")
def resolve_catalog_ownership_remediation(
    assignment_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    assignment = _assignment(db, principal.tenant_id, assignment_id)
    if not assignment:
        raise HTTPException(404, "Ownership assignment not found")
    try:
        return assignment_response(
            resolve_remediation(db, assignment, principal.subject)
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/api/v1/graph/exports", status_code=202)
def create_async_graph_export(
    req: GraphExportCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    try:
        record, job = create_graph_export(
            db,
            principal.tenant_id,
            req.format,
            req.relationships,
            req.sink_uri,
            req.max_edges,
            principal.subject,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"export": graph_export_response(record), "job_id": job.job_id}


@router.get("/api/v1/graph/exports")
def list_async_graph_exports(
    status: str | None = Query(
        default=None,
        pattern="^(pending|running|completed|failed)$",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(GraphExport).where(
        GraphExport.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(GraphExport.status == status)
    records = db.scalars(statement.order_by(GraphExport.created_at.desc()).limit(limit))
    return [graph_export_response(record) for record in records]


@router.get("/api/v1/graph/exports/{export_id}")
def get_async_graph_export(
    export_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    record = graph_export_for_tenant(db, principal.tenant_id, export_id)
    if not record:
        raise HTTPException(404, "Graph export not found")
    return graph_export_response(record)


@router.get("/api/v1/graph/exports/{export_id}/download")
def download_async_graph_export(
    export_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    record = graph_export_for_tenant(db, principal.tenant_id, export_id)
    if not record:
        raise HTTPException(404, "Graph export not found")
    try:
        content = load_graph_export(record)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    extension = {"json": "json", "csv": "csv", "graphml": "graphml"}[
        record.export_format
    ]
    return Response(
        content=content,
        media_type=CONTENT_TYPES[record.export_format],
        headers={
            "Content-Disposition": (
                f'attachment; filename="opendatagraph-{record.export_id}.{extension}"'
            ),
            "X-Content-SHA256": record.sha256 or "",
        },
    )


def _service_account(
    db: Session,
    tenant_id: str,
    account_id: str,
) -> ServiceAccount | None:
    return db.scalar(
        select(ServiceAccount).where(
            ServiceAccount.tenant_id == tenant_id,
            ServiceAccount.account_id == account_id,
        )
    )


def _credentials_for_account(
    db: Session,
    tenant_id: str,
    account_id: str,
) -> list[ServiceAccountCredential]:
    return list(
        db.scalars(
            select(ServiceAccountCredential)
            .where(
                ServiceAccountCredential.tenant_id == tenant_id,
                ServiceAccountCredential.account_id == account_id,
            )
            .order_by(ServiceAccountCredential.issued_at.desc())
        ).all()
    )


def _governance_task(
    db: Session,
    tenant_id: str,
    task_id: str,
) -> GovernanceReviewTask | None:
    return db.scalar(
        select(GovernanceReviewTask).where(
            GovernanceReviewTask.tenant_id == tenant_id,
            GovernanceReviewTask.task_id == task_id,
        )
    )


def _campaign(
    db: Session,
    tenant_id: str,
    campaign_id: str,
) -> OwnershipCampaign | None:
    return db.scalar(
        select(OwnershipCampaign).where(
            OwnershipCampaign.tenant_id == tenant_id,
            OwnershipCampaign.campaign_id == campaign_id,
        )
    )


def _assignment(
    db: Session,
    tenant_id: str,
    assignment_id: str,
) -> OwnershipAssignment | None:
    return db.scalar(
        select(OwnershipAssignment).where(
            OwnershipAssignment.tenant_id == tenant_id,
            OwnershipAssignment.assignment_id == assignment_id,
        )
    )
