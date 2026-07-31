import json
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    DataAsset,
    IntegrationEndpoint,
    OwnershipAssignment,
    OwnershipCampaign,
    OwnershipCampaignSchedule,
    utc_now,
)
from app.services.schedules import (
    next_cron_run,
    next_schedule_run,
    skip_maintenance,
    validate_schedule_definition,
)


SCOPE_FIELDS = {
    "source": DataAsset.source,
    "business_domain": DataAsset.business_domain,
    "sensitivity": DataAsset.sensitivity,
    "owner": DataAsset.owner,
}


def create_campaign(
    db: Session,
    tenant_id: str,
    name: str,
    description: str,
    scope: dict,
    due_at,
    created_by: str,
    source_schedule_id: str | None = None,
    notification_endpoint_ids: list[str] | None = None,
) -> OwnershipCampaign:
    normalized_scope = _validate_scope(scope)
    due_at = due_at.replace(tzinfo=None)
    if due_at <= utc_now():
        raise ValueError("Ownership campaign due date must be in the future")
    campaign = OwnershipCampaign(
        tenant_id=tenant_id,
        campaign_id=str(uuid4()),
        name=name,
        description=description,
        scope_json=json.dumps(normalized_scope, sort_keys=True),
        source_schedule_id=source_schedule_id,
        notification_endpoint_ids_json=json.dumps(
            sorted(set(notification_endpoint_ids or []))
        ),
        due_at=due_at,
        created_by=created_by,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def launch_campaign(
    db: Session,
    campaign: OwnershipCampaign,
    max_assets: int,
) -> tuple[OwnershipCampaign, int]:
    if campaign.status != "draft":
        raise ValueError("Only draft ownership campaigns can be launched")
    if campaign.due_at <= utc_now():
        raise ValueError("Expired ownership campaigns cannot be launched")
    if not 1 <= max_assets <= 100_000:
        raise ValueError("Ownership campaign asset limit must be 1 to 100000")
    statement = select(DataAsset).where(DataAsset.tenant_id == campaign.tenant_id)
    for field, values in json.loads(campaign.scope_json or "{}").items():
        statement = statement.where(SCOPE_FIELDS[field].in_(values))
    assets = list(db.scalars(statement.order_by(DataAsset.id).limit(max_assets)).all())
    if not assets:
        raise ValueError("Ownership campaign scope matched no assets")
    for asset in assets:
        db.add(
            OwnershipAssignment(
                tenant_id=campaign.tenant_id,
                assignment_id=str(uuid4()),
                campaign_id=campaign.campaign_id,
                asset_id=asset.id,
                owner=asset.owner,
            )
        )
    campaign.status = "active"
    campaign.launched_at = utc_now()
    db.commit()
    db.refresh(campaign)
    _queue_ownership_event(db, campaign, "ownership.campaign.launched")
    return campaign, len(assets)


def attest_assignment(
    db: Session,
    assignment: OwnershipAssignment,
    confirmed: bool,
    attested_by: str,
    owner: str | None = None,
    note: str = "",
    remediation_action: str | None = None,
    remediation_due_at=None,
) -> OwnershipAssignment:
    if assignment.status not in {"pending", "remediation-required"}:
        raise ValueError("Ownership assignment is already complete")
    now = utc_now()
    if confirmed:
        resolved_owner = (owner or assignment.owner).strip()
        if not resolved_owner:
            raise ValueError("Confirmed ownership requires a non-empty owner")
        asset = db.scalar(
            select(DataAsset).where(
                DataAsset.tenant_id == assignment.tenant_id,
                DataAsset.id == assignment.asset_id,
            )
        )
        if not asset:
            raise ValueError("Campaign asset no longer exists")
        asset.owner = resolved_owner
        assignment.owner = resolved_owner
        assignment.attested_owner = resolved_owner
        assignment.status = "attested"
        assignment.remediation_action = None
        assignment.remediation_due_at = None
    else:
        if owner is not None and not owner.strip():
            raise ValueError("Attested ownership must be non-empty when provided")
        if not remediation_action or remediation_due_at is None:
            raise ValueError(
                "Unconfirmed ownership requires a remediation action and due date"
            )
        remediation_due_at = remediation_due_at.replace(tzinfo=None)
        if remediation_due_at <= now:
            raise ValueError("Ownership remediation due date must be in the future")
        assignment.status = "remediation-required"
        assignment.remediation_action = remediation_action
        assignment.remediation_due_at = remediation_due_at
        assignment.attested_owner = owner.strip() if owner else None
    assignment.attestation_note = note
    assignment.attested_by = attested_by
    assignment.attested_at = now
    db.commit()
    db.refresh(assignment)
    if assignment.status == "remediation-required":
        _queue_ownership_event(
            db,
            assignment,
            "ownership.assignment.remediation-required",
        )
    _complete_campaign_if_ready(db, assignment.tenant_id, assignment.campaign_id)
    return assignment


def update_remediation(
    db: Session,
    assignment: OwnershipAssignment,
    action: str,
    due_at,
) -> OwnershipAssignment:
    if assignment.status != "remediation-required":
        raise ValueError("Only remediation-required assignments can be updated")
    due_at = due_at.replace(tzinfo=None)
    if due_at <= utc_now():
        raise ValueError("Ownership remediation due date must be in the future")
    assignment.remediation_action = action
    assignment.remediation_due_at = due_at
    db.commit()
    db.refresh(assignment)
    return assignment


def resolve_remediation(
    db: Session,
    assignment: OwnershipAssignment,
    resolved_by: str,
) -> OwnershipAssignment:
    if assignment.status != "remediation-required":
        raise ValueError("Only remediation-required assignments can be resolved")
    assignment.status = "resolved"
    assignment.resolved_by = resolved_by
    assignment.resolved_at = utc_now()
    db.commit()
    db.refresh(assignment)
    _complete_campaign_if_ready(db, assignment.tenant_id, assignment.campaign_id)
    return assignment


def campaign_response(
    campaign: OwnershipCampaign,
    counts: dict[str, int] | None = None,
) -> dict:
    return {
        "campaign_id": campaign.campaign_id,
        "name": campaign.name,
        "description": campaign.description,
        "status": campaign.status,
        "scope": json.loads(campaign.scope_json or "{}"),
        "source_schedule_id": campaign.source_schedule_id,
        "notification_endpoint_ids": json.loads(
            campaign.notification_endpoint_ids_json or "[]"
        ),
        "due_at": campaign.due_at,
        "counts": counts or {},
        "created_by": campaign.created_by,
        "created_at": campaign.created_at,
        "launched_at": campaign.launched_at,
        "completed_at": campaign.completed_at,
    }


def assignment_response(assignment: OwnershipAssignment) -> dict:
    return {
        "assignment_id": assignment.assignment_id,
        "campaign_id": assignment.campaign_id,
        "asset_id": assignment.asset_id,
        "owner": assignment.owner,
        "status": assignment.status,
        "attested_owner": assignment.attested_owner,
        "attestation_note": assignment.attestation_note,
        "remediation_action": assignment.remediation_action,
        "remediation_due_at": assignment.remediation_due_at,
        "attested_by": assignment.attested_by,
        "attested_at": assignment.attested_at,
        "resolved_by": assignment.resolved_by,
        "resolved_at": assignment.resolved_at,
        "created_at": assignment.created_at,
    }


def campaign_counts(db: Session, tenant_id: str, campaign_id: str) -> dict[str, int]:
    assignments = db.scalars(
        select(OwnershipAssignment).where(
            OwnershipAssignment.tenant_id == tenant_id,
            OwnershipAssignment.campaign_id == campaign_id,
        )
    )
    counts: dict[str, int] = {}
    for assignment in assignments:
        counts[assignment.status] = counts.get(assignment.status, 0) + 1
    return counts


def _complete_campaign_if_ready(
    db: Session,
    tenant_id: str,
    campaign_id: str,
) -> None:
    remaining = db.scalar(
        select(OwnershipAssignment).where(
            OwnershipAssignment.tenant_id == tenant_id,
            OwnershipAssignment.campaign_id == campaign_id,
            OwnershipAssignment.status.in_(("pending", "remediation-required")),
        )
    )
    if remaining:
        return
    campaign = db.scalar(
        select(OwnershipCampaign).where(
            OwnershipCampaign.tenant_id == tenant_id,
            OwnershipCampaign.campaign_id == campaign_id,
            OwnershipCampaign.status == "active",
        )
    )
    if campaign:
        campaign.status = "completed"
        campaign.completed_at = utc_now()
        db.commit()
        db.refresh(campaign)
        _queue_ownership_event(db, campaign, "ownership.campaign.completed")


def _validate_scope(scope: dict) -> dict[str, list[str]]:
    if not isinstance(scope, dict):
        raise ValueError("Ownership campaign scope must be an object")
    unknown = set(scope) - set(SCOPE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported ownership scope fields: {', '.join(sorted(unknown))}")
    normalized = {}
    for field, value in scope.items():
        values = value if isinstance(value, list) else [value]
        if (
            not values
            or len(values) > 100
            or any(not isinstance(item, str) or not item.strip() for item in values)
        ):
            raise ValueError(f"Ownership scope {field} must contain non-empty strings")
        normalized[field] = sorted(set(item.strip() for item in values))
    return normalized


def create_campaign_schedule(
    db: Session,
    tenant_id: str,
    name: str,
    description: str,
    scope: dict,
    due_days: int,
    max_assets: int,
    schedule_type: str,
    interval_seconds: int,
    cron_expression: str | None,
    timezone_name: str,
    maintenance_windows: list[dict],
    notification_endpoint_ids: list[str],
    enabled: bool,
    created_by: str,
) -> OwnershipCampaignSchedule:
    normalized_scope = _validate_scope(scope)
    validate_schedule_definition(
        schedule_type,
        interval_seconds,
        cron_expression,
        timezone_name,
        maintenance_windows,
    )
    if not 1 <= due_days <= 365:
        raise ValueError("Ownership campaign due days must be 1 to 365")
    if not 1 <= max_assets <= 100_000:
        raise ValueError("Ownership campaign asset limit must be 1 to 100000")
    endpoint_ids = _validate_notification_endpoints(
        db,
        tenant_id,
        notification_endpoint_ids,
    )
    now = utc_now()
    schedule = OwnershipCampaignSchedule(
        tenant_id=tenant_id,
        schedule_id=str(uuid4()),
        name=name,
        description=description,
        scope_json=json.dumps(normalized_scope, sort_keys=True),
        due_days=due_days,
        max_assets=max_assets,
        schedule_type=schedule_type,
        interval_seconds=interval_seconds,
        cron_expression=cron_expression,
        timezone=timezone_name,
        maintenance_windows_json=json.dumps(maintenance_windows),
        notification_endpoint_ids_json=json.dumps(endpoint_ids),
        enabled=enabled,
        next_run_at=(
            next_cron_run(
                cron_expression or "",
                timezone_name,
                now,
                maintenance_windows,
            )
            if schedule_type == "cron"
            else skip_maintenance(now, timezone_name, maintenance_windows)
        ),
        created_by=created_by,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def enqueue_due_ownership_campaigns(db: Session, limit: int = 50) -> int:
    from app.services.jobs import enqueue_job

    now = utc_now()
    due = list(
        db.scalars(
            select(OwnershipCampaignSchedule)
            .where(
                OwnershipCampaignSchedule.enabled.is_(True),
                OwnershipCampaignSchedule.next_run_at <= now,
            )
            .order_by(OwnershipCampaignSchedule.next_run_at)
            .limit(limit)
        ).all()
    )
    enqueued = 0
    for schedule in due:
        scheduled_for = schedule.next_run_at.isoformat()
        next_run = next_schedule_run(schedule, now)
        claimed = db.execute(
            update(OwnershipCampaignSchedule)
            .where(
                OwnershipCampaignSchedule.id == schedule.id,
                OwnershipCampaignSchedule.enabled.is_(True),
                OwnershipCampaignSchedule.next_run_at == schedule.next_run_at,
            )
            .values(next_run_at=next_run, last_enqueued_at=now, updated_at=now)
        )
        db.commit()
        if claimed.rowcount != 1:
            continue
        enqueue_job(
            db,
            tenant_id=schedule.tenant_id,
            job_type="ownership.campaign.launch",
            payload={
                "schedule_id": schedule.schedule_id,
                "scheduled_for": scheduled_for,
            },
            created_by=f"ownership-schedule:{schedule.schedule_id}",
        )
        enqueued += 1
    return enqueued


def execute_scheduled_campaign(
    db: Session,
    tenant_id: str,
    schedule_id: str,
    scheduled_for: str,
) -> dict:
    schedule = db.scalar(
        select(OwnershipCampaignSchedule).where(
            OwnershipCampaignSchedule.tenant_id == tenant_id,
            OwnershipCampaignSchedule.schedule_id == schedule_id,
        )
    )
    if not schedule:
        raise ValueError("Ownership campaign schedule not found")
    try:
        scheduled_at = scheduled_for.replace("+00:00", "")
        run_stamp = scheduled_at.replace("-", "").replace(":", "")[:15]
    except (AttributeError, ValueError) as exc:
        raise ValueError("Ownership campaign scheduled_for is invalid") from exc
    campaign_name = f"{schedule.name[:140]} · {run_stamp}"
    existing = db.scalar(
        select(OwnershipCampaign).where(
            OwnershipCampaign.tenant_id == tenant_id,
            OwnershipCampaign.source_schedule_id == schedule.schedule_id,
            OwnershipCampaign.name == campaign_name,
        )
    )
    if existing:
        if existing.status == "draft":
            existing, assignment_count = launch_campaign(
                db,
                existing,
                schedule.max_assets,
            )
        else:
            assignment_count = sum(
                campaign_counts(db, tenant_id, existing.campaign_id).values()
            )
        return {
            "campaign": campaign_response(
                existing,
                campaign_counts(db, tenant_id, existing.campaign_id),
            ),
            "assignment_count": assignment_count,
            "idempotent": True,
        }
    campaign = create_campaign(
        db,
        tenant_id,
        campaign_name,
        schedule.description,
        json.loads(schedule.scope_json or "{}"),
        utc_now() + timedelta(days=schedule.due_days),
        f"ownership-schedule:{schedule.schedule_id}",
        source_schedule_id=schedule.schedule_id,
        notification_endpoint_ids=json.loads(
            schedule.notification_endpoint_ids_json or "[]"
        ),
    )
    campaign, assignment_count = launch_campaign(db, campaign, schedule.max_assets)
    return {
        "campaign": campaign_response(
            campaign,
            campaign_counts(db, tenant_id, campaign.campaign_id),
        ),
        "assignment_count": assignment_count,
        "idempotent": False,
    }


def campaign_schedule_response(schedule: OwnershipCampaignSchedule) -> dict:
    return {
        "schedule_id": schedule.schedule_id,
        "name": schedule.name,
        "description": schedule.description,
        "scope": json.loads(schedule.scope_json or "{}"),
        "due_days": schedule.due_days,
        "max_assets": schedule.max_assets,
        "schedule_type": schedule.schedule_type,
        "interval_seconds": schedule.interval_seconds,
        "cron_expression": schedule.cron_expression,
        "timezone": schedule.timezone,
        "maintenance_windows": json.loads(
            schedule.maintenance_windows_json or "[]"
        ),
        "notification_endpoint_ids": json.loads(
            schedule.notification_endpoint_ids_json or "[]"
        ),
        "enabled": schedule.enabled,
        "next_run_at": schedule.next_run_at,
        "last_enqueued_at": schedule.last_enqueued_at,
        "created_by": schedule.created_by,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


def validate_campaign_schedule_endpoints(
    db: Session,
    tenant_id: str,
    endpoint_ids: list[str],
) -> list[str]:
    return _validate_notification_endpoints(db, tenant_id, endpoint_ids)


def validate_ownership_scope(scope: dict) -> dict[str, list[str]]:
    return _validate_scope(scope)


def _validate_notification_endpoints(
    db: Session,
    tenant_id: str,
    endpoint_ids: list[str],
) -> list[str]:
    normalized = sorted(set(endpoint_ids))
    if any(not value or len(value) > 36 for value in normalized):
        raise ValueError("Ownership notification endpoint identifiers are invalid")
    if not normalized:
        return []
    found = set(
        db.scalars(
            select(IntegrationEndpoint.endpoint_id).where(
                IntegrationEndpoint.tenant_id == tenant_id,
                IntegrationEndpoint.endpoint_id.in_(normalized),
                IntegrationEndpoint.enabled.is_(True),
            )
        ).all()
    )
    if found != set(normalized):
        raise ValueError(
            "Ownership notification endpoints must exist and be enabled in the tenant"
        )
    return normalized


def _queue_ownership_event(
    db: Session,
    subject: OwnershipCampaign | OwnershipAssignment,
    event_type: str,
) -> bool:
    try:
        from app.services.integrations import queue_integration_event

        if isinstance(subject, OwnershipAssignment):
            campaign = db.scalar(
                select(OwnershipCampaign).where(
                    OwnershipCampaign.tenant_id == subject.tenant_id,
                    OwnershipCampaign.campaign_id == subject.campaign_id,
                )
            )
            payload = assignment_response(subject)
            source_id = subject.assignment_id
        else:
            campaign = subject
            payload = campaign_response(subject)
            source_id = subject.campaign_id
        endpoint_ids = (
            set(json.loads(campaign.notification_endpoint_ids_json or "[]"))
            if campaign
            else set()
        )
        deliveries = queue_integration_event(
            db,
            subject.tenant_id,
            event_type,
            payload,
            created_by=f"ownership:{source_id}",
            endpoint_ids=endpoint_ids or None,
        )
        return bool(deliveries)
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "failed to queue ownership notification"
        )
        return False
