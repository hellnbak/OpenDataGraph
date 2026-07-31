import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BackgroundJob, utc_now
from app.observability import JOBS
from app.services.connectors import ingest_connector, safe_connector_error
from app.services.evidence import (
    execute_disposition,
    mark_disposition_error,
    purge_expired_evidence,
)
from app.services.evidence_packages import (
    execute_evidence_package,
    mark_evidence_package_error,
)
from app.services.governance import notify_overdue_reviews
from app.services.graph_exports import execute_graph_export, mark_graph_export_error
from app.services.identity import execute_deprovision, mark_deprovision_error
from app.services.integrations import deliver_integration, mark_delivery_dead_letter
from app.services.ownership import execute_scheduled_campaign
from app.services.schedules import ProviderRateLimitExceeded, provider_request_guard
from app.services.search import reindex_tenant
from connectors.gdrive import GoogleDriveConnector
from connectors.github import GitHubConnector
from connectors.gitlab import GitLabConnector
from connectors.postgresql import PostgreSQLConnector
from connectors.s3 import S3Connector
from connectors.security import validate_https_url
from connectors.sharepoint import SharePointConnector


SUPPORTED_JOB_TYPES = {
    "connector.scan",
    "catalog.reindex",
    "evidence.retention",
    "evidence.disposition",
    "identity.deprovision",
    "integration.deliver",
    "governance.sla-notify",
    "graph.export",
    "ownership.campaign.launch",
    "governance.evidence-package",
}
SUPPORTED_CONNECTORS = {
    "aws-s3",
    "google-drive",
    "github",
    "gitlab",
    "sharepoint",
    "postgresql",
}


def enqueue_job(
    db: Session,
    tenant_id: str,
    job_type: str,
    payload: dict,
    created_by: str,
    max_attempts: int = 3,
) -> BackgroundJob:
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError(f"Unsupported job type: {job_type}")
    validate_job_payload(job_type, payload)
    job = BackgroundJob(
        tenant_id=tenant_id,
        job_id=str(uuid4()),
        job_type=job_type,
        payload_json=json.dumps(payload),
        created_by=created_by,
        max_attempts=max_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next_job(db: Session) -> BackgroundJob | None:
    now = utc_now()
    candidate = db.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.status == "pending",
            BackgroundJob.available_at <= now,
            BackgroundJob.cancel_requested.is_(False),
        )
        .order_by(BackgroundJob.created_at)
        .limit(1)
    )
    if not candidate:
        return None
    claimed = db.execute(
        update(BackgroundJob)
        .where(BackgroundJob.id == candidate.id, BackgroundJob.status == "pending")
        .values(status="running", claimed_at=now, attempts=BackgroundJob.attempts + 1)
    )
    db.commit()
    if claimed.rowcount != 1:
        return None
    return db.get(BackgroundJob, candidate.id)


def execute_job(db: Session, job: BackgroundJob) -> None:
    if job.cancel_requested:
        job.status = "cancelled"
        job.finished_at = utc_now()
        db.commit()
        JOBS.labels(job.job_type, job.status).inc()
        return
    payload = {}
    try:
        payload = json.loads(job.payload_json)
        if job.job_type == "connector.scan":
            connector = _build_connector(payload, db, job.tenant_id)
            result = asyncio.run(
                ingest_connector(
                    db,
                    connector,
                    cursor=payload.get("cursor"),
                    max_items=int(payload.get("max_items", 500)),
                    tenant_id=job.tenant_id,
                )
            )
        elif job.job_type == "catalog.reindex":
            result = reindex_tenant(db, job.tenant_id)
        elif job.job_type == "evidence.retention":
            result = purge_expired_evidence(
                db,
                job.tenant_id,
                deleted_by=f"job:{job.job_id}",
                limit=int(payload.get("limit", 500)),
            )
        elif job.job_type == "evidence.disposition":
            result = execute_disposition(
                db,
                job.tenant_id,
                payload["disposition_id"],
                executed_by=f"job:{job.job_id}",
            )
        elif job.job_type == "identity.deprovision":
            result = execute_deprovision(
                db,
                job.tenant_id,
                payload["workflow_id"],
            )
        elif job.job_type == "integration.deliver":
            result = deliver_integration(db, job.tenant_id, payload["delivery_id"])
        elif job.job_type == "governance.sla-notify":
            result = notify_overdue_reviews(
                db,
                job.tenant_id,
                int(payload.get("limit", 500)),
            )
        elif job.job_type == "graph.export":
            result = execute_graph_export(
                db,
                job.tenant_id,
                payload["export_id"],
            )
        elif job.job_type == "ownership.campaign.launch":
            result = execute_scheduled_campaign(
                db,
                job.tenant_id,
                payload["schedule_id"],
                payload["scheduled_for"],
            )
        elif job.job_type == "governance.evidence-package":
            result = execute_evidence_package(
                db,
                job.tenant_id,
                payload["package_id"],
            )
        else:
            raise RuntimeError(f"Unsupported job type: {job.job_type}")
        db.refresh(job)
        job.status = "cancelled" if job.cancel_requested else "completed"
        job.result_json = json.dumps(result, default=str)
        job.error = None
        job.finished_at = utc_now()
        db.commit()
        JOBS.labels(job.job_type, job.status).inc()
    except Exception as exc:
        job.error = safe_connector_error(exc)
        final_failure = job.attempts >= job.max_attempts or job.cancel_requested
        if final_failure:
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.finished_at = utc_now()
            if job.job_type == "integration.deliver" and not job.cancel_requested:
                mark_delivery_dead_letter(
                    db,
                    job.tenant_id,
                    payload["delivery_id"],
                    job.error,
                )
        else:
            job.status = "pending"
            retry_seconds = (
                exc.retry_after_seconds
                if isinstance(exc, ProviderRateLimitExceeded)
                else min(300, 2**job.attempts)
            )
            job.available_at = utc_now() + timedelta(seconds=retry_seconds)
            job.claimed_at = None
        if job.job_type == "identity.deprovision" and payload.get("workflow_id"):
            mark_deprovision_error(
                db,
                job.tenant_id,
                payload["workflow_id"],
                job.error,
                final_failure and not job.cancel_requested,
            )
        elif job.job_type == "evidence.disposition" and payload.get("disposition_id"):
            mark_disposition_error(
                db,
                job.tenant_id,
                payload["disposition_id"],
                job.error,
            )
        elif job.job_type == "graph.export" and payload.get("export_id"):
            mark_graph_export_error(
                db,
                job.tenant_id,
                payload["export_id"],
                job.error,
            )
        elif job.job_type == "governance.evidence-package" and payload.get(
            "package_id"
        ):
            mark_evidence_package_error(
                db,
                job.tenant_id,
                payload["package_id"],
                job.error,
            )
        db.commit()
        JOBS.labels(job.job_type, job.status).inc()


def recover_stale_jobs(db: Session) -> int:
    cutoff = utc_now() - timedelta(seconds=settings.worker_claim_timeout_seconds)
    failed = db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.status == "running",
            BackgroundJob.claimed_at < cutoff,
            BackgroundJob.attempts >= BackgroundJob.max_attempts,
        )
        .values(
            status="failed",
            finished_at=utc_now(),
            error="Worker claim expired after the maximum number of attempts",
        )
    )
    recovered = db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.status == "running",
            BackgroundJob.claimed_at < cutoff,
            BackgroundJob.attempts < BackgroundJob.max_attempts,
        )
        .values(
            status="pending",
            claimed_at=None,
            available_at=utc_now(),
            error="Recovered after worker claim timeout",
        )
    )
    db.commit()
    return failed.rowcount + recovered.rowcount


def cancel_job(db: Session, job: BackgroundJob) -> BackgroundJob:
    job.cancel_requested = True
    if job.status == "pending":
        job.status = "cancelled"
        job.finished_at = utc_now()
    db.commit()
    db.refresh(job)
    return job


def retry_job(db: Session, job: BackgroundJob) -> BackgroundJob:
    if job.status not in {"failed", "cancelled"}:
        raise ValueError("Only failed or cancelled jobs can be retried")
    job.status = "pending"
    job.cancel_requested = False
    job.available_at = utc_now()
    job.claimed_at = None
    job.finished_at = None
    job.error = None
    job.attempts = 0
    db.commit()
    db.refresh(job)
    return job


def validate_job_payload(job_type: str, payload: dict) -> None:
    serialized = json.dumps(payload)
    if len(serialized.encode()) > 16_384:
        raise ValueError("Job payload exceeds 16 KiB")
    if job_type == "connector.scan":
        connector_type = payload.get("connector_type")
        if connector_type not in SUPPORTED_CONNECTORS:
            raise ValueError(f"Unsupported connector type: {connector_type}")
        forbidden = {"token", "password", "secret", "authorization", "credentials"}
        if forbidden & {key.lower() for key in payload}:
            raise ValueError("Connector credentials must be supplied by secret_ref")
        secret_ref = payload.get("secret_ref")
        if connector_type not in {"aws-s3"} and not secret_ref:
            raise ValueError(f"secret_ref is required for {connector_type}")
        if connector_type == "github":
            validate_https_url(
                payload.get("api_url") or "https://api.github.com",
                settings.github_allowed_hosts,
            )
        elif connector_type == "gitlab":
            validate_https_url(
                payload.get("api_url") or "https://gitlab.com/api/v4",
                settings.gitlab_allowed_hosts,
            )
        elif connector_type == "sharepoint" and payload.get("cursor"):
            validate_https_url(payload["cursor"], settings.sharepoint_allowed_hosts)
        elif connector_type == "postgresql":
            schemas = payload.get("schemas", [])
            if (
                not isinstance(schemas, list)
                or len(schemas) > 100
                or any(
                    not isinstance(schema, str)
                    or not schema.strip()
                    or len(schema) > 63
                    for schema in schemas
                )
            ):
                raise ValueError("PostgreSQL connector schemas are invalid")
    elif job_type == "integration.deliver":
        if set(payload) != {"delivery_id"} or not isinstance(payload.get("delivery_id"), str):
            raise ValueError("Integration delivery jobs require only delivery_id")
    elif job_type == "identity.deprovision":
        if set(payload) != {"workflow_id"} or not isinstance(payload.get("workflow_id"), str):
            raise ValueError("Identity deprovision jobs require only workflow_id")
    elif job_type == "evidence.disposition":
        if set(payload) != {"disposition_id"} or not isinstance(payload.get("disposition_id"), str):
            raise ValueError("Evidence disposition jobs require only disposition_id")
    elif job_type == "graph.export":
        if set(payload) != {"export_id"} or not isinstance(payload.get("export_id"), str):
            raise ValueError("Graph export jobs require only export_id")
    elif job_type == "governance.sla-notify":
        if set(payload) != {"limit"} or not isinstance(payload.get("limit"), int):
            raise ValueError("Governance notification jobs require only an integer limit")
        if not 1 <= payload["limit"] <= 5000:
            raise ValueError("Governance notification job limit must be 1 to 5000")
    elif job_type == "ownership.campaign.launch":
        if set(payload) != {"schedule_id", "scheduled_for"}:
            raise ValueError(
                "Ownership campaign launch jobs require schedule_id and scheduled_for"
            )
        if not isinstance(payload.get("schedule_id"), str):
            raise ValueError("Ownership campaign schedule_id is invalid")
        try:
            datetime.fromisoformat(payload.get("scheduled_for", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError("Ownership campaign scheduled_for is invalid") from exc
    elif job_type == "governance.evidence-package":
        if set(payload) != {"package_id"} or not isinstance(
            payload.get("package_id"),
            str,
        ):
            raise ValueError(
                "Governance evidence package jobs require only package_id"
            )


def _build_connector(payload: dict, db: Session, tenant_id: str):
    connector_type = payload["connector_type"]
    account = payload["account"]
    guard = provider_request_guard(db, tenant_id, connector_type)
    if connector_type == "aws-s3":
        return S3Connector(
            account,
            prefix=payload.get("prefix", ""),
            region=payload.get("region"),
            before_request=guard,
        )
    secret = resolve_secret(payload["secret_ref"]) if payload.get("secret_ref") else None
    if connector_type == "google-drive":
        try:
            credentials_info = json.loads(secret or "")
        except json.JSONDecodeError as exc:
            raise ValueError("Google Drive secret_ref must contain service-account JSON") from exc
        return GoogleDriveConnector(
            account=account,
            credentials_info=credentials_info,
            impersonate_user=payload.get("impersonate_user"),
            drive_id=payload.get("drive_id"),
            before_request=guard,
        )
    if connector_type == "github":
        return GitHubConnector(
            account,
            secret or "",
            payload.get("api_url") or "https://api.github.com",
            allowed_hosts=settings.github_allowed_hosts,
            before_request=guard,
        )
    if connector_type == "gitlab":
        return GitLabConnector(
            account,
            secret or "",
            payload.get("api_url") or "https://gitlab.com/api/v4",
            allowed_hosts=settings.gitlab_allowed_hosts,
            before_request=guard,
        )
    if connector_type == "sharepoint":
        site_id = payload.get("site_id") or account
        drive_id = payload.get("drive_id")
        if not drive_id:
            raise ValueError("drive_id is required for SharePoint")
        return SharePointConnector(
            site_id,
            drive_id,
            secret or "",
            allowed_hosts=settings.sharepoint_allowed_hosts,
            before_request=guard,
        )
    if connector_type == "postgresql":
        return PostgreSQLConnector(
            account,
            secret or "",
            schemas=payload.get("schemas", []),
            before_request=guard,
        )
    raise ValueError(f"Unsupported connector type: {connector_type}")


def resolve_secret(reference: str) -> str:
    if reference.startswith("env:"):
        name = reference.removeprefix("env:")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise ValueError("Environment secret references must use uppercase variable names")
        value = os.getenv(name)
        if value is None:
            raise ValueError(f"Secret environment variable is not set: {name}")
        return value
    if reference.startswith("file:"):
        path = Path(reference.removeprefix("file:")).expanduser().resolve()
        if not any(path.is_relative_to(root) for root in settings.secret_file_roots):
            raise ValueError("Secret file is outside ODG_SECRET_FILE_ROOTS")
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Secret files must not exceed 1 MiB")
        return path.read_text(encoding="utf-8").strip()
    raise ValueError("Secret references must use env:NAME or file:/path")
