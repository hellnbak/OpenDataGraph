import hashlib
import re
from datetime import UTC
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EvidenceDisposition, EvidenceRecord, utc_now


def store_evidence(
    tenant_id: str,
    evidence_id: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> tuple[str, str]:
    if len(content) > settings.evidence_max_bytes:
        raise ValueError(f"Evidence exceeds the {settings.evidence_max_bytes}-byte limit")
    digest = hashlib.sha256(content).hexdigest()
    object_key = _object_key(tenant_id, evidence_id)
    if settings.evidence_backend == "local":
        root = settings.evidence_local_directory.resolve()
        path = (root / object_key).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local evidence path")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return f"local://{object_key}", digest
    if settings.evidence_backend == "s3":
        if not settings.evidence_bucket:
            raise RuntimeError("ODG_EVIDENCE_BUCKET is required for S3 evidence storage")
        _s3_client().put_object(
            Bucket=settings.evidence_bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return f"s3://{settings.evidence_bucket}/{object_key}", digest
    raise RuntimeError(f"Unsupported evidence backend: {settings.evidence_backend}")


def load_evidence(storage_uri: str) -> bytes:
    if storage_uri.startswith("local://"):
        object_key = storage_uri.removeprefix("local://")
        path = (settings.evidence_local_directory / object_key).resolve()
        root = settings.evidence_local_directory.resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local evidence path")
        content = path.read_bytes()
        if len(content) > settings.evidence_max_bytes:
            raise ValueError("Stored evidence exceeds the configured size limit")
        return content
    if storage_uri.startswith("s3://"):
        bucket_and_key = storage_uri.removeprefix("s3://")
        bucket, object_key = bucket_and_key.split("/", 1)
        content = _s3_client().get_object(Bucket=bucket, Key=object_key)["Body"].read(
            settings.evidence_max_bytes + 1
        )
        if len(content) > settings.evidence_max_bytes:
            raise ValueError("Stored evidence exceeds the configured size limit")
        return content
    raise ValueError("Unsupported evidence URI")


def delete_evidence(storage_uri: str) -> None:
    if storage_uri.startswith("local://"):
        object_key = storage_uri.removeprefix("local://")
        root = settings.evidence_local_directory.resolve()
        path = (root / object_key).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local evidence path")
        path.unlink(missing_ok=True)
        return
    if storage_uri.startswith("s3://"):
        bucket_and_key = storage_uri.removeprefix("s3://")
        bucket, object_key = bucket_and_key.split("/", 1)
        _s3_client().delete_object(Bucket=bucket, Key=object_key)
        return
    raise ValueError("Unsupported evidence URI")


def purge_expired_evidence(
    db: Session,
    tenant_id: str,
    deleted_by: str = "retention-worker",
    limit: int = 500,
) -> dict:
    records = list(
        db.scalars(
            select(EvidenceRecord)
            .where(
                EvidenceRecord.tenant_id == tenant_id,
                EvidenceRecord.deleted_at.is_(None),
                EvidenceRecord.legal_hold.is_(False),
                EvidenceRecord.retention_until.is_not(None),
                EvidenceRecord.retention_until <= utc_now(),
            )
            .order_by(EvidenceRecord.retention_until)
            .limit(limit)
        ).all()
    )
    if settings.evidence_disposition_approval_required:
        requested = 0
        for record in records:
            existing = db.scalar(
                select(EvidenceDisposition).where(
                    EvidenceDisposition.tenant_id == tenant_id,
                    EvidenceDisposition.evidence_id == record.evidence_id,
                    EvidenceDisposition.status.in_(("pending", "approved")),
                )
            )
            if existing:
                continue
            db.add(
                EvidenceDisposition(
                    tenant_id=tenant_id,
                    disposition_id=str(uuid4()),
                    evidence_id=record.evidence_id,
                    reason="Retention period expired",
                    requested_by=deleted_by,
                )
            )
            requested += 1
        db.commit()
        return {"requested": requested, "examined": len(records)}
    deleted = failed = 0
    for record in records:
        try:
            delete_evidence(record.storage_uri)
        except (OSError, RuntimeError, ValueError):
            failed += 1
            continue
        record.deleted_at = utc_now()
        record.deleted_by = deleted_by
        record.deletion_reason = "Retention period expired"
        deleted += 1
    db.commit()
    return {"deleted": deleted, "failed": failed, "examined": len(records)}


def verify_object_lock(db: Session, record: EvidenceRecord) -> dict:
    now = utc_now()
    if record.storage_uri.startswith("local://"):
        record.object_lock_status = "not-applicable"
        record.object_lock_mode = None
        record.object_lock_retain_until = None
        record.object_lock_legal_hold = None
        record.object_lock_verified_at = now
        db.commit()
        db.refresh(record)
        return object_lock_response(record)
    if not record.storage_uri.startswith("s3://"):
        raise ValueError("Unsupported evidence URI")
    bucket, object_key = _s3_location(record.storage_uri)
    client = _s3_client()
    try:
        head = client.head_object(Bucket=bucket, Key=object_key)
        kwargs = {"Bucket": bucket, "Key": object_key}
        if head.get("VersionId"):
            kwargs["VersionId"] = head["VersionId"]
        retention = client.get_object_retention(**kwargs).get("Retention", {})
        legal_hold = client.get_object_legal_hold(**kwargs).get("LegalHold", {})
    except Exception:
        record.object_lock_status = "unavailable"
        record.object_lock_mode = None
        record.object_lock_retain_until = None
        record.object_lock_legal_hold = None
        record.object_lock_verified_at = now
        db.commit()
        db.refresh(record)
        return object_lock_response(record)
    retain_until = retention.get("RetainUntilDate")
    if retain_until and retain_until.tzinfo:
        retain_until = retain_until.astimezone(UTC).replace(tzinfo=None)
    record.object_lock_status = "verified"
    record.object_lock_mode = retention.get("Mode")
    record.object_lock_retain_until = retain_until
    record.object_lock_legal_hold = legal_hold.get("Status") == "ON"
    record.object_lock_verified_at = now
    db.commit()
    db.refresh(record)
    return object_lock_response(record)


def create_disposition(
    db: Session,
    record: EvidenceRecord,
    action: str,
    reason: str,
    requested_by: str,
) -> EvidenceDisposition:
    if record.deleted_at:
        raise ValueError("Deleted evidence cannot be dispositioned")
    if action != "delete":
        raise ValueError("Only delete dispositions are supported")
    existing = db.scalar(
        select(EvidenceDisposition).where(
            EvidenceDisposition.tenant_id == record.tenant_id,
            EvidenceDisposition.evidence_id == record.evidence_id,
            EvidenceDisposition.status.in_(("pending", "approved")),
        )
    )
    if existing:
        raise ValueError("Evidence already has an active disposition")
    disposition = EvidenceDisposition(
        tenant_id=record.tenant_id,
        disposition_id=str(uuid4()),
        evidence_id=record.evidence_id,
        action=action,
        reason=reason,
        requested_by=requested_by,
    )
    db.add(disposition)
    db.commit()
    db.refresh(disposition)
    return disposition


def approve_disposition(
    db: Session,
    disposition: EvidenceDisposition,
    approved_by: str,
) -> EvidenceDisposition:
    if disposition.status != "pending":
        raise ValueError("Only pending dispositions can be approved")
    if disposition.requested_by == approved_by and approved_by != "development":
        raise ValueError("Disposition approval requires a different identity")
    disposition.status = "approved"
    disposition.approved_by = approved_by
    disposition.approved_at = utc_now()
    db.commit()
    db.refresh(disposition)
    return disposition


def reject_disposition(
    db: Session,
    disposition: EvidenceDisposition,
    rejected_by: str,
) -> EvidenceDisposition:
    if disposition.status != "pending":
        raise ValueError("Only pending dispositions can be rejected")
    disposition.status = "rejected"
    disposition.rejected_by = rejected_by
    disposition.rejected_at = utc_now()
    db.commit()
    db.refresh(disposition)
    return disposition


def execute_disposition(
    db: Session,
    tenant_id: str,
    disposition_id: str,
    executed_by: str,
) -> dict:
    disposition = db.scalar(
        select(EvidenceDisposition).where(
            EvidenceDisposition.tenant_id == tenant_id,
            EvidenceDisposition.disposition_id == disposition_id,
        )
    )
    if not disposition:
        raise ValueError("Evidence disposition not found")
    if disposition.status == "executed":
        return disposition_response(disposition)
    if disposition.status != "approved":
        raise ValueError("Only approved dispositions can be executed")
    record = db.scalar(
        select(EvidenceRecord).where(
            EvidenceRecord.tenant_id == tenant_id,
            EvidenceRecord.evidence_id == disposition.evidence_id,
        )
    )
    if not record:
        raise ValueError("Evidence record not found")
    if record.legal_hold:
        raise ValueError("Evidence under legal hold cannot be disposed")
    if record.storage_uri.startswith("s3://"):
        lock = verify_object_lock(db, record)
        if lock["status"] != "verified":
            raise ValueError("S3 Object Lock state must be verified before disposition")
        if lock["legal_hold"] is True:
            raise ValueError("S3 Object Lock legal hold prevents disposition")
        if lock["retain_until"] and lock["retain_until"] > utc_now():
            raise ValueError("S3 Object Lock retention prevents disposition")
    delete_evidence(record.storage_uri)
    now = utc_now()
    record.deleted_at = now
    record.deleted_by = executed_by
    record.deletion_reason = disposition.reason
    disposition.status = "executed"
    disposition.executed_by = executed_by
    disposition.executed_at = now
    disposition.error = None
    db.commit()
    db.refresh(disposition)
    return disposition_response(disposition)


def object_lock_response(record: EvidenceRecord) -> dict:
    return {
        "evidence_id": record.evidence_id,
        "status": record.object_lock_status,
        "mode": record.object_lock_mode,
        "retain_until": record.object_lock_retain_until,
        "legal_hold": record.object_lock_legal_hold,
        "verified_at": record.object_lock_verified_at,
    }


def disposition_response(disposition: EvidenceDisposition) -> dict:
    return {
        "disposition_id": disposition.disposition_id,
        "evidence_id": disposition.evidence_id,
        "action": disposition.action,
        "status": disposition.status,
        "reason": disposition.reason,
        "requested_by": disposition.requested_by,
        "requested_at": disposition.requested_at,
        "approved_by": disposition.approved_by,
        "approved_at": disposition.approved_at,
        "rejected_by": disposition.rejected_by,
        "rejected_at": disposition.rejected_at,
        "executed_by": disposition.executed_by,
        "executed_at": disposition.executed_at,
        "error": disposition.error,
    }


def mark_disposition_error(
    db: Session,
    tenant_id: str,
    disposition_id: str,
    error: str,
) -> None:
    disposition = db.scalar(
        select(EvidenceDisposition).where(
            EvidenceDisposition.tenant_id == tenant_id,
            EvidenceDisposition.disposition_id == disposition_id,
        )
    )
    if disposition:
        disposition.error = error


def evidence_health() -> dict:
    if settings.evidence_backend == "local":
        try:
            settings.evidence_local_directory.mkdir(parents=True, exist_ok=True)
            return {"backend": "local", "ok": True}
        except OSError as exc:
            return {"backend": "local", "ok": False, "error": type(exc).__name__}
    if settings.evidence_backend == "s3":
        try:
            _s3_client().head_bucket(Bucket=settings.evidence_bucket)
            return {"backend": "s3", "ok": True}
        except Exception as exc:
            return {"backend": "s3", "ok": False, "error": type(exc).__name__}
    return {"backend": settings.evidence_backend, "ok": False, "error": "unsupported_backend"}


def _object_key(tenant_id: str, evidence_id: str) -> str:
    safe_tenant = re.sub(r"[^A-Za-z0-9_.-]", "_", tenant_id)
    prefix = settings.evidence_prefix.strip("/")
    return "/".join(part for part in (prefix, safe_tenant, evidence_id) if part)


def _s3_location(storage_uri: str) -> tuple[str, str]:
    bucket_and_key = storage_uri.removeprefix("s3://")
    bucket, object_key = bucket_and_key.split("/", 1)
    return bucket, object_key


def _s3_client():
    import boto3

    kwargs = {}
    if settings.evidence_endpoint_url:
        kwargs["endpoint_url"] = settings.evidence_endpoint_url
    if settings.evidence_region:
        kwargs["region_name"] = settings.evidence_region
    return boto3.client("s3", **kwargs)
