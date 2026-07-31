import json
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import utc_now
from app.services.jobs import claim_next_job, enqueue_job, execute_job, recover_stale_jobs, resolve_secret


def test_database_queue_claims_and_completes_reindex_job(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        job = enqueue_job(db, "tenant-a", "catalog.reindex", {}, "operator")
        claimed = claim_next_job(db)
        assert claimed is not None
        assert claimed.job_id == job.job_id
        assert claimed.status == "running"
        execute_job(db, claimed)
        db.refresh(claimed)
        assert claimed.status == "completed"
        assert json.loads(claimed.result_json)["skipped"]


def test_connector_job_rejects_inline_credentials():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        with pytest.raises(ValueError, match="secret_ref"):
            enqueue_job(
                db,
                "tenant-a",
                "connector.scan",
                {
                    "connector_type": "github",
                    "account": "example",
                    "token": "not-persisted",
                },
                "operator",
            )


def test_connector_job_rejects_unapproved_endpoint(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "github_allowed_hosts", ("api.github.com",))
    with session_factory() as db:
        with pytest.raises(ValueError, match="allowlist"):
            enqueue_job(
                db,
                "tenant-a",
                "connector.scan",
                {
                    "connector_type": "github",
                    "account": "example",
                    "secret_ref": "env:ODG_GITHUB_TOKEN",
                    "api_url": "https://unapproved.example.invalid",
                },
                "operator",
            )


def test_secret_file_must_be_bounded_and_under_approved_root(tmp_path, monkeypatch):
    secret_root = tmp_path / "secrets"
    secret_root.mkdir()
    approved = secret_root / "token"
    approved.write_text("token-value\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.write_text("outside", encoding="utf-8")
    monkeypatch.setattr(settings, "secret_file_roots", (secret_root.resolve(),))

    assert resolve_secret(f"file:{approved}") == "token-value"
    with pytest.raises(ValueError, match="outside"):
        resolve_secret(f"file:{outside}")


def test_stale_jobs_fail_after_exhausting_attempts(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "worker_claim_timeout_seconds", 10)
    with session_factory() as db:
        job = enqueue_job(db, "tenant-a", "catalog.reindex", {}, "operator", max_attempts=1)
        job.status = "running"
        job.attempts = 1
        job.claimed_at = utc_now() - timedelta(seconds=20)
        db.commit()

        assert recover_stale_jobs(db) == 1
        db.refresh(job)
        assert job.status == "failed"
        assert job.finished_at is not None
