import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DataAsset,
    OwnershipAssignment,
    OwnershipCampaign,
    utc_now,
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
