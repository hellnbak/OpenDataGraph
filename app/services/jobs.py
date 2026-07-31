import asyncio
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BackgroundJob, utc_now
from app.observability import JOBS
from app.services.connectors import ingest_connector, safe_connector_error
from app.services.search import reindex_tenant
from connectors.gdrive import GoogleDriveConnector
from connectors.github import GitHubConnector
from connectors.gitlab import GitLabConnector
from connectors.s3 import S3Connector
from connectors.security import validate_https_url
from connectors.sharepoint import SharePointConnector


SUPPORTED_JOB_TYPES = {"connector.scan", "catalog.reindex"}
SUPPORTED_CONNECTORS = {"aws-s3", "google-drive", "github", "gitlab", "sharepoint"}


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
    _validate_payload(job_type, payload)
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
    try:
        payload = json.loads(job.payload_json)
        if job.job_type == "connector.scan":
            connector = _build_connector(payload)
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
        else:
            raise RuntimeError(f"Unsupported job type: {job.job_type}")
        db.refresh(job)
        job.status = "cancelled" if job.cancel_requested else "completed"
        job.result_json = json.dumps(result)
        job.error = None
        job.finished_at = utc_now()
        db.commit()
        JOBS.labels(job.job_type, job.status).inc()
    except Exception as exc:
        job.error = safe_connector_error(exc)
        if job.attempts >= job.max_attempts or job.cancel_requested:
            job.status = "cancelled" if job.cancel_requested else "failed"
            job.finished_at = utc_now()
        else:
            job.status = "pending"
            job.available_at = utc_now() + timedelta(seconds=min(300, 2**job.attempts))
            job.claimed_at = None
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


def _validate_payload(job_type: str, payload: dict) -> None:
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


def _build_connector(payload: dict):
    connector_type = payload["connector_type"]
    account = payload["account"]
    if connector_type == "aws-s3":
        return S3Connector(account, prefix=payload.get("prefix", ""), region=payload.get("region"))
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
        )
    if connector_type == "github":
        return GitHubConnector(
            account,
            secret or "",
            payload.get("api_url") or "https://api.github.com",
            allowed_hosts=settings.github_allowed_hosts,
        )
    if connector_type == "gitlab":
        return GitLabConnector(
            account,
            secret or "",
            payload.get("api_url") or "https://gitlab.com/api/v4",
            allowed_hosts=settings.gitlab_allowed_hosts,
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
