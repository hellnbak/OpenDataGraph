import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import (
    PolicyApproverDelegation,
    PolicyBundle,
    PolicyException,
    utc_now,
)


def compare_policy_bundles(
    current: PolicyBundle,
    previous: PolicyBundle | None,
) -> dict:
    current_policies = _policies_by_id(current)
    previous_policies = _policies_by_id(previous) if previous else {}
    added = [
        current_policies[policy_id]
        for policy_id in sorted(current_policies.keys() - previous_policies.keys())
    ]
    removed = [
        previous_policies[policy_id]
        for policy_id in sorted(previous_policies.keys() - current_policies.keys())
    ]
    changed = []
    for policy_id in sorted(current_policies.keys() & previous_policies.keys()):
        before = previous_policies[policy_id]
        after = current_policies[policy_id]
        if before == after:
            continue
        fields = {}
        for field in sorted(before.keys() | after.keys()):
            if before.get(field) != after.get(field):
                fields[field] = {"before": before.get(field), "after": after.get(field)}
        changed.append({"policy_id": policy_id, "fields": fields})
    return {
        "from": (
            {
                "bundle_id": previous.bundle_id,
                "name": previous.name,
                "version": previous.version,
            }
            if previous
            else None
        ),
        "to": {
            "bundle_id": current.bundle_id,
            "name": current.name,
            "version": current.version,
        },
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def previous_policy_bundle(
    db: Session,
    tenant_id: str,
    bundle: PolicyBundle,
) -> PolicyBundle | None:
    return db.scalar(
        select(PolicyBundle)
        .where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.name == bundle.name,
            PolicyBundle.version < bundle.version,
        )
        .order_by(PolicyBundle.version.desc())
        .limit(1)
    )


def create_delegation(
    db: Session,
    tenant_id: str,
    subject: str,
    bundle_name: str | None,
    can_approve_bundles: bool,
    can_approve_exceptions: bool,
    expires_at,
    created_by: str,
) -> PolicyApproverDelegation:
    if not can_approve_bundles and not can_approve_exceptions:
        raise ValueError("Delegation must grant at least one approval capability")
    expires_at = expires_at.replace(tzinfo=None)
    if expires_at <= utc_now():
        raise ValueError("Delegation expiry must be in the future")
    delegation = PolicyApproverDelegation(
        tenant_id=tenant_id,
        delegation_id=str(uuid4()),
        subject=subject,
        bundle_name=bundle_name,
        can_approve_bundles=can_approve_bundles,
        can_approve_exceptions=can_approve_exceptions,
        expires_at=expires_at,
        created_by=created_by,
    )
    db.add(delegation)
    db.commit()
    db.refresh(delegation)
    return delegation


def can_approve_bundle(
    db: Session,
    principal: Principal,
    bundle: PolicyBundle,
) -> bool:
    if principal.role == "administrator":
        return True
    return bool(
        db.scalar(
            select(PolicyApproverDelegation).where(
                PolicyApproverDelegation.tenant_id == principal.tenant_id,
                PolicyApproverDelegation.subject == principal.subject,
                PolicyApproverDelegation.active.is_(True),
                PolicyApproverDelegation.expires_at > utc_now(),
                PolicyApproverDelegation.can_approve_bundles.is_(True),
                (
                    (PolicyApproverDelegation.bundle_name.is_(None))
                    | (PolicyApproverDelegation.bundle_name == bundle.name)
                ),
            )
        )
    )


def can_approve_exception(db: Session, principal: Principal) -> bool:
    if principal.role == "administrator":
        return True
    return bool(
        db.scalar(
            select(PolicyApproverDelegation).where(
                PolicyApproverDelegation.tenant_id == principal.tenant_id,
                PolicyApproverDelegation.subject == principal.subject,
                PolicyApproverDelegation.active.is_(True),
                PolicyApproverDelegation.expires_at > utc_now(),
                PolicyApproverDelegation.can_approve_exceptions.is_(True),
            )
        )
    )


def request_exception_renewal(
    db: Session,
    exception: PolicyException,
    expires_at,
    reason: str,
    requested_by: str,
) -> PolicyException:
    expires_at = expires_at.replace(tzinfo=None)
    if not exception.active or exception.expires_at <= utc_now():
        raise ValueError("Only active policy exceptions can be renewed")
    if expires_at <= exception.expires_at or expires_at <= utc_now():
        raise ValueError("Renewal expiry must extend the current exception")
    if exception.renewal_status == "pending":
        raise ValueError("A renewal request is already pending")
    exception.renewal_status = "pending"
    exception.renewal_requested_until = expires_at
    exception.renewal_requested_by = requested_by
    exception.renewal_requested_at = utc_now()
    exception.renewal_reason = reason
    db.commit()
    db.refresh(exception)
    return exception


def approve_exception_renewal(
    db: Session,
    exception: PolicyException,
    approved_by: str,
) -> PolicyException:
    if exception.renewal_status != "pending" or not exception.renewal_requested_until:
        raise ValueError("Policy exception has no pending renewal")
    exception.expires_at = exception.renewal_requested_until
    exception.renewal_status = "approved"
    exception.renewed_by = approved_by
    exception.renewed_at = utc_now()
    db.commit()
    db.refresh(exception)
    return exception


def delegation_response(delegation: PolicyApproverDelegation) -> dict:
    return {
        "delegation_id": delegation.delegation_id,
        "subject": delegation.subject,
        "bundle_name": delegation.bundle_name,
        "can_approve_bundles": delegation.can_approve_bundles,
        "can_approve_exceptions": delegation.can_approve_exceptions,
        "expires_at": delegation.expires_at,
        "active": delegation.active,
        "created_by": delegation.created_by,
        "created_at": delegation.created_at,
        "revoked_at": delegation.revoked_at,
    }


def _policies_by_id(bundle: PolicyBundle | None) -> dict[str, dict]:
    if not bundle:
        return {}
    policies = json.loads(bundle.definition_json)
    return {policy["id"]: policy for policy in policies}
