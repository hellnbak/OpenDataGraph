import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import BackgroundJob, utc_now
from app.services.schedules import (
    ProviderRateLimitExceeded,
    configure_provider_budget,
    consume_provider_budget,
    create_schedule,
    enqueue_due_schedules,
)


def test_due_schedule_enqueues_reference_only_connector_job():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        schedule = create_schedule(
            db,
            "tenant-a",
            "github",
            "example",
            300,
            {
                "secret_ref": "env:ODG_GITHUB_TOKEN",
                "max_items": 100,
            },
            "operator",
        )
        assert schedule.next_run_at <= utc_now()
        assert enqueue_due_schedules(db) == 1
        job = db.scalar(select(BackgroundJob))
        assert job is not None
        payload = json.loads(job.payload_json)
        assert payload["secret_ref"] == "env:ODG_GITHUB_TOKEN"
        assert "token" not in payload
        db.refresh(schedule)
        assert schedule.next_run_at > utc_now()


def test_provider_budget_is_shared_and_bounded():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        configure_provider_budget(db, "tenant-a", "github", max_requests=2, window_seconds=60)
        consume_provider_budget(db, "tenant-a", "github")
        consume_provider_budget(db, "tenant-a", "github")
        with pytest.raises(ProviderRateLimitExceeded) as error:
            consume_provider_budget(db, "tenant-a", "github")
        assert error.value.retry_after_seconds > 0
        consume_provider_budget(db, "tenant-b", "github")
