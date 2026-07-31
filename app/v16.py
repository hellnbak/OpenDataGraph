import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal, require_role
from app.database import get_db
from app.models import (
    GovernanceEvidencePackage,
    OwnershipCampaignSchedule,
    utc_now,
)
from app.schemas import (
    GovernanceEvidencePackageCreate,
    OwnershipCampaignScheduleCreate,
    OwnershipCampaignScheduleUpdate,
)
from app.services.evidence_packages import (
    create_evidence_package,
    evidence_package_for_tenant,
    evidence_package_response,
    governance_analytics,
    load_evidence_package,
)
from app.services.export_sinks import export_sink_schemes
from app.services.ownership import (
    campaign_schedule_response,
    create_campaign_schedule,
    validate_escalation_policy,
    validate_campaign_schedule_endpoints,
    validate_ownership_scope,
)
from app.services.schedules import (
    next_cron_run,
    skip_maintenance,
    validate_schedule_definition,
)


router = APIRouter()


@router.post("/api/v1/ownership/schedules", status_code=201)
def create_ownership_schedule(
    req: OwnershipCampaignScheduleCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    try:
        schedule = create_campaign_schedule(
            db,
            principal.tenant_id,
            req.name,
            req.description,
            req.scope,
            req.due_days,
            req.max_assets,
            req.schedule_type,
            req.interval_seconds,
            req.cron_expression,
            req.timezone,
            req.maintenance_windows,
            req.notification_endpoint_ids,
            req.enabled,
            principal.subject,
            req.escalation_policy_id,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Ownership campaign schedule name already exists") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return campaign_schedule_response(schedule)


@router.get("/api/v1/ownership/schedules")
def list_ownership_schedules(
    enabled: bool | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(OwnershipCampaignSchedule).where(
        OwnershipCampaignSchedule.tenant_id == principal.tenant_id
    )
    if enabled is not None:
        statement = statement.where(OwnershipCampaignSchedule.enabled == enabled)
    schedules = db.scalars(
        statement.order_by(OwnershipCampaignSchedule.created_at.desc())
    )
    return [campaign_schedule_response(schedule) for schedule in schedules]


@router.patch("/api/v1/ownership/schedules/{schedule_id}")
def update_ownership_schedule(
    schedule_id: str,
    req: OwnershipCampaignScheduleUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    schedule = _ownership_schedule(db, principal.tenant_id, schedule_id)
    if not schedule:
        raise HTTPException(404, "Ownership campaign schedule not found")
    changes = req.model_dump(exclude_none=True)
    maintenance_windows = changes.pop(
        "maintenance_windows",
        json.loads(schedule.maintenance_windows_json or "[]"),
    )
    endpoint_ids = changes.pop(
        "notification_endpoint_ids",
        json.loads(schedule.notification_endpoint_ids_json or "[]"),
    )
    try:
        if "scope" in changes:
            schedule.scope_json = json.dumps(
                validate_ownership_scope(changes.pop("scope")),
                sort_keys=True,
            )
        endpoint_ids = validate_campaign_schedule_endpoints(
            db,
            principal.tenant_id,
            endpoint_ids,
        )
        if "escalation_policy_id" in changes:
            changes["escalation_policy_id"] = validate_escalation_policy(
                db,
                principal.tenant_id,
                changes["escalation_policy_id"],
            )
        if changes.get("schedule_type") == "interval":
            changes["cron_expression"] = None
        for field, value in changes.items():
            setattr(
                schedule,
                field,
                value.replace(tzinfo=None) if field == "next_run_at" else value,
            )
        validate_schedule_definition(
            schedule.schedule_type,
            schedule.interval_seconds,
            schedule.cron_expression,
            schedule.timezone,
            maintenance_windows,
        )
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
                else skip_maintenance(
                    utc_now(),
                    schedule.timezone,
                    maintenance_windows,
                )
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    schedule.maintenance_windows_json = json.dumps(maintenance_windows)
    schedule.notification_endpoint_ids_json = json.dumps(endpoint_ids)
    schedule.updated_at = utc_now()
    db.commit()
    db.refresh(schedule)
    return campaign_schedule_response(schedule)


@router.delete("/api/v1/ownership/schedules/{schedule_id}", status_code=204)
def delete_ownership_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    schedule = _ownership_schedule(db, principal.tenant_id, schedule_id)
    if not schedule:
        raise HTTPException(404, "Ownership campaign schedule not found")
    db.delete(schedule)
    db.commit()
    return Response(status_code=204)


@router.get("/api/v1/governance/analytics")
def get_governance_analytics(
    days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    return governance_analytics(db, principal.tenant_id, days)


@router.post("/api/v1/governance/evidence-packages", status_code=202)
def create_governance_evidence_package(
    req: GovernanceEvidencePackageCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    try:
        record, job = create_evidence_package(
            db,
            principal.tenant_id,
            req.days,
            req.categories,
            req.max_records,
            principal.subject,
            req.signing_profile,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"package": evidence_package_response(record), "job_id": job.job_id}


@router.get("/api/v1/governance/evidence-packages")
def list_governance_evidence_packages(
    status: str | None = Query(
        default=None,
        pattern="^(pending|running|completed|failed)$",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(GovernanceEvidencePackage).where(
        GovernanceEvidencePackage.tenant_id == principal.tenant_id
    )
    if status:
        statement = statement.where(GovernanceEvidencePackage.status == status)
    records = db.scalars(
        statement.order_by(GovernanceEvidencePackage.created_at.desc()).limit(limit)
    )
    return [evidence_package_response(record) for record in records]


@router.get("/api/v1/governance/evidence-packages/{package_id}")
def get_governance_evidence_package(
    package_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    record = evidence_package_for_tenant(db, principal.tenant_id, package_id)
    if not record:
        raise HTTPException(404, "Governance evidence package not found")
    return evidence_package_response(record)


@router.get("/api/v1/governance/evidence-packages/{package_id}/download")
def download_governance_evidence_package(
    package_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    record = evidence_package_for_tenant(db, principal.tenant_id, package_id)
    if not record:
        raise HTTPException(404, "Governance evidence package not found")
    try:
        content = load_evidence_package(record)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="opendatagraph-governance-{record.package_id}.json"'
            ),
            "X-Content-SHA256": record.sha256 or "",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/v1/graph/export-sinks")
def graph_export_sink_configuration(
    principal: Principal = Depends(require_role("auditor")),
):
    del principal
    from app.config import settings

    return {
        "schemes": export_sink_schemes(),
        "s3_allowlisted_buckets": len(settings.graph_export_allowed_sink_buckets),
        "https_allowlisted_hosts": len(settings.graph_export_https_allowed_hosts),
        "https_workload_identity_configured": bool(
            settings.graph_export_https_identity_token_file
        ),
        "s3_exchange_profile_configured": bool(
            settings.graph_export_s3_exchange_profile
        ),
        "gcs_allowlisted_buckets": len(
            settings.graph_export_gcs_allowed_sink_buckets
        ),
        "gcs_exchange_profile_configured": bool(
            settings.graph_export_gcs_exchange_profile
        ),
        "azure_allowlisted_sinks": len(settings.graph_export_azure_allowed_sinks),
        "azure_exchange_profile_configured": bool(
            settings.graph_export_azure_exchange_profile
        ),
    }


def _ownership_schedule(
    db: Session,
    tenant_id: str,
    schedule_id: str,
) -> OwnershipCampaignSchedule | None:
    return db.scalar(
        select(OwnershipCampaignSchedule).where(
            OwnershipCampaignSchedule.tenant_id == tenant_id,
            OwnershipCampaignSchedule.schedule_id == schedule_id,
        )
    )
