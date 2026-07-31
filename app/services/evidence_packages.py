import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    DecisionAudit,
    EvidenceDisposition,
    EvidenceRecord,
    GovernanceEvidencePackage,
    GovernanceReviewTask,
    GraphExport,
    OwnershipAssignment,
    OwnershipCampaign,
    PolicyBundle,
    ServiceAccount,
    ServiceAccountCredential,
    utc_now,
)
from app.services.governance import OPEN_STATUSES


PACKAGE_CATEGORIES = {
    "reviews",
    "ownership",
    "evidence",
    "policies",
    "service-accounts",
    "graph-exports",
}


def governance_analytics(db: Session, tenant_id: str, days: int = 30) -> dict:
    if not 1 <= days <= 366:
        raise ValueError("Governance analytics window must be 1 to 366 days")
    now = utc_now()
    window_start = now - timedelta(days=days)
    review_filters = (
        GovernanceReviewTask.tenant_id == tenant_id,
        GovernanceReviewTask.created_at >= window_start,
    )
    completed = _count(
        db,
        GovernanceReviewTask,
        *review_filters,
        GovernanceReviewTask.status == "completed",
    )
    completed_within_sla = _count(
        db,
        GovernanceReviewTask,
        *review_filters,
        GovernanceReviewTask.status == "completed",
        GovernanceReviewTask.completed_at <= GovernanceReviewTask.due_at,
    )
    by_type = {
        task_type: count
        for task_type, count in db.execute(
            select(
                GovernanceReviewTask.task_type,
                func.count(GovernanceReviewTask.id),
            )
            .where(*review_filters)
            .group_by(GovernanceReviewTask.task_type)
        ).all()
    }
    decision_counts = {
        decision: count
        for decision, count in db.execute(
            select(DecisionAudit.decision, func.count(DecisionAudit.id))
            .where(
                DecisionAudit.tenant_id == tenant_id,
                DecisionAudit.created_at >= window_start,
            )
            .group_by(DecisionAudit.decision)
        ).all()
    }
    return {
        "window": {
            "days": days,
            "start": window_start,
            "end": now,
        },
        "reviews": {
            "created": _count(db, GovernanceReviewTask, *review_filters),
            "open": _count(
                db,
                GovernanceReviewTask,
                GovernanceReviewTask.tenant_id == tenant_id,
                GovernanceReviewTask.status.in_(OPEN_STATUSES),
            ),
            "overdue": _count(
                db,
                GovernanceReviewTask,
                GovernanceReviewTask.tenant_id == tenant_id,
                GovernanceReviewTask.status.in_(OPEN_STATUSES),
                GovernanceReviewTask.due_at < now,
            ),
            "completed": completed,
            "completed_within_sla": completed_within_sla,
            "sla_compliance_rate": (
                round(completed_within_sla / completed, 4) if completed else None
            ),
            "aging": {
                "due_within_24_hours": _count(
                    db,
                    GovernanceReviewTask,
                    GovernanceReviewTask.tenant_id == tenant_id,
                    GovernanceReviewTask.status.in_(OPEN_STATUSES),
                    GovernanceReviewTask.due_at >= now,
                    GovernanceReviewTask.due_at <= now + timedelta(hours=24),
                ),
                "overdue_under_7_days": _count(
                    db,
                    GovernanceReviewTask,
                    GovernanceReviewTask.tenant_id == tenant_id,
                    GovernanceReviewTask.status.in_(OPEN_STATUSES),
                    GovernanceReviewTask.due_at < now,
                    GovernanceReviewTask.due_at >= now - timedelta(days=7),
                ),
                "overdue_7_days_or_more": _count(
                    db,
                    GovernanceReviewTask,
                    GovernanceReviewTask.tenant_id == tenant_id,
                    GovernanceReviewTask.status.in_(OPEN_STATUSES),
                    GovernanceReviewTask.due_at < now - timedelta(days=7),
                ),
            },
            "by_type": by_type,
        },
        "ownership": {
            "campaigns_created": _count(
                db,
                OwnershipCampaign,
                OwnershipCampaign.tenant_id == tenant_id,
                OwnershipCampaign.created_at >= window_start,
            ),
            "active_campaigns": _count(
                db,
                OwnershipCampaign,
                OwnershipCampaign.tenant_id == tenant_id,
                OwnershipCampaign.status == "active",
            ),
            "pending_assignments": _count(
                db,
                OwnershipAssignment,
                OwnershipAssignment.tenant_id == tenant_id,
                OwnershipAssignment.status == "pending",
            ),
            "remediation_required": _count(
                db,
                OwnershipAssignment,
                OwnershipAssignment.tenant_id == tenant_id,
                OwnershipAssignment.status == "remediation-required",
            ),
            "remediation_overdue": _count(
                db,
                OwnershipAssignment,
                OwnershipAssignment.tenant_id == tenant_id,
                OwnershipAssignment.status == "remediation-required",
                OwnershipAssignment.remediation_due_at < now,
            ),
        },
        "evidence": {
            "records_created": _count(
                db,
                EvidenceRecord,
                EvidenceRecord.tenant_id == tenant_id,
                EvidenceRecord.created_at >= window_start,
            ),
            "legal_holds": _count(
                db,
                EvidenceRecord,
                EvidenceRecord.tenant_id == tenant_id,
                EvidenceRecord.legal_hold.is_(True),
                EvidenceRecord.deleted_at.is_(None),
            ),
            "dispositions_requested": _count(
                db,
                EvidenceDisposition,
                EvidenceDisposition.tenant_id == tenant_id,
                EvidenceDisposition.requested_at >= window_start,
            ),
            "dispositions_executed": _count(
                db,
                EvidenceDisposition,
                EvidenceDisposition.tenant_id == tenant_id,
                EvidenceDisposition.executed_at >= window_start,
            ),
        },
        "identity": {
            "active_service_accounts": _count(
                db,
                ServiceAccount,
                ServiceAccount.tenant_id == tenant_id,
                ServiceAccount.status == "active",
            ),
            "credentials_expiring_within_30_days": _count(
                db,
                ServiceAccountCredential,
                ServiceAccountCredential.tenant_id == tenant_id,
                ServiceAccountCredential.status == "active",
                ServiceAccountCredential.expires_at > now,
                ServiceAccountCredential.expires_at <= now + timedelta(days=30),
            ),
        },
        "policy_decisions": decision_counts,
    }


def create_evidence_package(
    db: Session,
    tenant_id: str,
    days: int,
    categories: list[str],
    max_records: int,
    created_by: str,
) -> tuple[GovernanceEvidencePackage, object]:
    from app.services.jobs import enqueue_job

    if not 1 <= days <= 366:
        raise ValueError("Governance evidence package window must be 1 to 366 days")
    if not 1 <= max_records <= 100_000:
        raise ValueError("Governance evidence package record limit must be 1 to 100000")
    normalized_categories = sorted(set(categories or PACKAGE_CATEGORIES))
    unknown = set(normalized_categories) - PACKAGE_CATEGORIES
    if unknown:
        raise ValueError(
            f"Unsupported governance evidence categories: {', '.join(sorted(unknown))}"
        )
    now = utc_now()
    record = GovernanceEvidencePackage(
        tenant_id=tenant_id,
        package_id=str(uuid4()),
        window_start=now - timedelta(days=days),
        window_end=now,
        categories_json=json.dumps(normalized_categories),
        max_records=max_records,
        created_by=created_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    job = enqueue_job(
        db,
        tenant_id,
        "governance.evidence-package",
        {"package_id": record.package_id},
        created_by,
        max_attempts=3,
    )
    return record, job


def execute_evidence_package(
    db: Session,
    tenant_id: str,
    package_id: str,
) -> dict:
    record = evidence_package_for_tenant(db, tenant_id, package_id)
    if not record:
        raise ValueError("Governance evidence package not found")
    if record.status == "completed":
        return evidence_package_response(record)
    record.status = "running"
    record.error = None
    db.commit()
    categories = json.loads(record.categories_json or "[]")
    sections, record_count, truncated = _package_sections(
        db,
        record,
        categories,
    )
    document = {
        "manifest": {
            "format": "opendatagraph-governance-evidence",
            "version": 1,
            "package_id": record.package_id,
            "tenant_id": tenant_id,
            "window_start": record.window_start,
            "window_end": record.window_end,
            "categories": categories,
            "record_count": record_count,
            "truncated": truncated,
            "content_policy": "metadata-only",
            "generated_at": utc_now(),
        },
        "analytics": governance_analytics(
            db,
            tenant_id,
            max(1, (record.window_end - record.window_start).days),
        ),
        "records": sections,
    }
    content = json.dumps(
        document,
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    if len(content) > settings.governance_package_max_bytes:
        raise ValueError("Governance evidence package exceeds the configured byte limit")
    digest = hashlib.sha256(content).hexdigest()
    storage_uri = _store_package(record, content, digest)
    record.status = "completed"
    record.record_count = record_count
    record.truncated = truncated
    record.storage_uri = storage_uri
    record.sha256 = digest
    record.size_bytes = len(content)
    record.error = None
    record.completed_at = utc_now()
    db.commit()
    db.refresh(record)
    _queue_completion_event(db, record)
    return evidence_package_response(record)


def mark_evidence_package_error(
    db: Session,
    tenant_id: str,
    package_id: str,
    error: str,
) -> None:
    record = evidence_package_for_tenant(db, tenant_id, package_id)
    if record:
        record.status = "failed"
        record.error = error
        db.commit()


def load_evidence_package(record: GovernanceEvidencePackage) -> bytes:
    if record.status != "completed" or not record.storage_uri:
        raise ValueError("Governance evidence package is not available")
    if record.storage_uri.startswith("local://"):
        object_key = record.storage_uri.removeprefix("local://")
        root = settings.governance_package_local_directory.resolve()
        path = (root / object_key).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local governance package path")
        content = path.read_bytes()
    elif record.storage_uri.startswith("s3://"):
        bucket, key = _s3_location(record.storage_uri)
        content = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read(
            settings.governance_package_max_bytes + 1
        )
    else:
        raise ValueError("Unsupported governance evidence package URI")
    if len(content) > settings.governance_package_max_bytes:
        raise ValueError("Stored governance evidence package exceeds the byte limit")
    if record.sha256 and hashlib.sha256(content).hexdigest() != record.sha256:
        raise ValueError("Governance evidence package integrity check failed")
    return content


def evidence_package_for_tenant(
    db: Session,
    tenant_id: str,
    package_id: str,
) -> GovernanceEvidencePackage | None:
    return db.scalar(
        select(GovernanceEvidencePackage).where(
            GovernanceEvidencePackage.tenant_id == tenant_id,
            GovernanceEvidencePackage.package_id == package_id,
        )
    )


def evidence_package_response(record: GovernanceEvidencePackage) -> dict:
    return {
        "package_id": record.package_id,
        "status": record.status,
        "window_start": record.window_start,
        "window_end": record.window_end,
        "categories": json.loads(record.categories_json or "[]"),
        "max_records": record.max_records,
        "record_count": record.record_count,
        "truncated": record.truncated,
        "storage_uri": record.storage_uri,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "error": record.error,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "completed_at": record.completed_at,
    }


def _package_sections(
    db: Session,
    package: GovernanceEvidencePackage,
    categories: list[str],
) -> tuple[dict, int, bool]:
    sections: dict[str, list[dict]] = {}
    remaining = package.max_records
    truncated = False
    definitions = {
        "reviews": (
            GovernanceReviewTask,
            GovernanceReviewTask.created_at,
            _review_record,
        ),
        "ownership": (
            OwnershipCampaign,
            OwnershipCampaign.created_at,
            _campaign_record,
        ),
        "evidence": (EvidenceRecord, EvidenceRecord.created_at, _evidence_record),
        "policies": (PolicyBundle, PolicyBundle.created_at, _policy_record),
        "service-accounts": (
            ServiceAccount,
            ServiceAccount.created_at,
            _service_account_record,
        ),
        "graph-exports": (GraphExport, GraphExport.created_at, _graph_export_record),
    }
    for category in categories:
        model, timestamp, serializer = definitions[category]
        if remaining == 0:
            sections[category] = []
            truncated = True
            continue
        rows = list(
            db.scalars(
                select(model)
                .where(
                    model.tenant_id == package.tenant_id,
                    timestamp >= package.window_start,
                    timestamp <= package.window_end,
                )
                .order_by(timestamp, model.id)
                .limit(remaining + 1)
            ).all()
        )
        if len(rows) > remaining:
            rows = rows[:remaining]
            truncated = True
        sections[category] = [serializer(row) for row in rows]
        remaining -= len(rows)
    record_count = package.max_records - remaining
    return sections, record_count, truncated


def _review_record(record: GovernanceReviewTask) -> dict:
    return {
        "task_id": record.task_id,
        "task_type": record.task_type,
        "subject_id": record.subject_id,
        "priority": record.priority,
        "status": record.status,
        "due_at": record.due_at,
        "created_at": record.created_at,
        "completed_at": record.completed_at,
    }


def _campaign_record(record: OwnershipCampaign) -> dict:
    return {
        "campaign_id": record.campaign_id,
        "source_schedule_id": record.source_schedule_id,
        "status": record.status,
        "due_at": record.due_at,
        "created_at": record.created_at,
        "launched_at": record.launched_at,
        "completed_at": record.completed_at,
    }


def _evidence_record(record: EvidenceRecord) -> dict:
    return {
        "evidence_id": record.evidence_id,
        "category": record.category,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "retention_until": record.retention_until,
        "legal_hold": record.legal_hold,
        "deleted_at": record.deleted_at,
        "object_lock_status": record.object_lock_status,
        "created_at": record.created_at,
    }


def _policy_record(record: PolicyBundle) -> dict:
    return {
        "bundle_id": record.bundle_id,
        "name": record.name,
        "version": record.version,
        "status": record.status,
        "created_at": record.created_at,
        "approved_at": record.approved_at,
        "activated_at": record.activated_at,
        "retired_at": record.retired_at,
    }


def _service_account_record(record: ServiceAccount) -> dict:
    return {
        "account_id": record.account_id,
        "name": record.name,
        "role": record.role,
        "status": record.status,
        "last_authenticated_at": record.last_authenticated_at,
        "created_at": record.created_at,
        "disabled_at": record.disabled_at,
    }


def _graph_export_record(record: GraphExport) -> dict:
    return {
        "export_id": record.export_id,
        "format": record.export_format,
        "status": record.status,
        "edge_count": record.edge_count,
        "truncated": record.truncated,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "created_at": record.created_at,
        "completed_at": record.completed_at,
    }


def _store_package(
    record: GovernanceEvidencePackage,
    content: bytes,
    digest: str,
) -> str:
    prefix = settings.governance_package_prefix.strip("/")
    safe_tenant = re.sub(r"[^A-Za-z0-9_.-]", "_", record.tenant_id)
    object_key = "/".join(
        part
        for part in (prefix, safe_tenant, f"{record.package_id}.json")
        if part
    )
    if settings.governance_package_backend == "local":
        root = settings.governance_package_local_directory.resolve()
        path = (root / object_key).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local governance package path")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return f"local://{object_key}"
    if settings.governance_package_backend == "s3":
        if not settings.governance_package_bucket:
            raise RuntimeError(
                "ODG_GOVERNANCE_PACKAGE_BUCKET is required for S3 package storage"
            )
        _s3_client().put_object(
            Bucket=settings.governance_package_bucket,
            Key=object_key,
            Body=content,
            ContentType="application/json",
            Metadata={"sha256": digest},
        )
        return f"s3://{settings.governance_package_bucket}/{object_key}"
    raise RuntimeError(
        f"Unsupported governance package backend: {settings.governance_package_backend}"
    )


def _s3_location(uri: str) -> tuple[str, str]:
    bucket_and_key = uri.removeprefix("s3://")
    return tuple(bucket_and_key.split("/", 1))


def _s3_client():
    import boto3

    kwargs = {}
    if settings.governance_package_endpoint_url:
        kwargs["endpoint_url"] = settings.governance_package_endpoint_url
    if settings.governance_package_region:
        kwargs["region_name"] = settings.governance_package_region
    return boto3.client("s3", **kwargs)


def _count(db: Session, model, *conditions) -> int:
    return int(db.scalar(select(func.count(model.id)).where(*conditions)) or 0)


def _json_default(value):
    if isinstance(value, datetime):
        return (
            value.replace(tzinfo=UTC).isoformat()
            if value.tzinfo is None
            else value.isoformat()
        )
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _queue_completion_event(
    db: Session,
    record: GovernanceEvidencePackage,
) -> None:
    try:
        from app.services.integrations import queue_integration_event

        queue_integration_event(
            db,
            record.tenant_id,
            "governance.evidence-package.completed",
            evidence_package_response(record),
            created_by=f"governance-package:{record.package_id}",
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "failed to queue governance evidence package event"
        )
