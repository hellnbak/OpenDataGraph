import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import ConnectorSchedule, ProviderRateLimit, utc_now


class ProviderRateLimitExceeded(RuntimeError):
    def __init__(self, provider: str, retry_after_seconds: int):
        super().__init__(f"Provider request budget exhausted for {provider}")
        self.provider = provider
        self.retry_after_seconds = max(1, retry_after_seconds)


def create_schedule(
    db: Session,
    tenant_id: str,
    connector_type: str,
    account: str,
    interval_seconds: int,
    payload: dict,
    created_by: str,
    enabled: bool = True,
) -> ConnectorSchedule:
    from app.services.jobs import validate_job_payload

    normalized_payload = {
        "connector_type": connector_type,
        "account": account,
        **payload,
    }
    validate_job_payload("connector.scan", normalized_payload)
    schedule = ConnectorSchedule(
        tenant_id=tenant_id,
        schedule_id=str(uuid4()),
        connector_type=connector_type,
        account=account,
        interval_seconds=interval_seconds,
        payload_json=json.dumps(normalized_payload),
        enabled=enabled,
        next_run_at=utc_now(),
        created_by=created_by,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def enqueue_due_schedules(db: Session, limit: int = 50) -> int:
    from app.services.jobs import enqueue_job

    now = utc_now()
    due = list(
        db.scalars(
            select(ConnectorSchedule)
            .where(
                ConnectorSchedule.enabled.is_(True),
                ConnectorSchedule.next_run_at <= now,
            )
            .order_by(ConnectorSchedule.next_run_at)
            .limit(limit)
        ).all()
    )
    enqueued = 0
    for schedule in due:
        next_run = schedule.next_run_at
        while next_run <= now:
            next_run += timedelta(seconds=schedule.interval_seconds)
        claimed = db.execute(
            update(ConnectorSchedule)
            .where(
                ConnectorSchedule.id == schedule.id,
                ConnectorSchedule.enabled.is_(True),
                ConnectorSchedule.next_run_at == schedule.next_run_at,
            )
            .values(next_run_at=next_run, last_enqueued_at=now, updated_at=now)
        )
        db.commit()
        if claimed.rowcount != 1:
            continue
        enqueue_job(
            db,
            tenant_id=schedule.tenant_id,
            job_type="connector.scan",
            payload=json.loads(schedule.payload_json),
            created_by=f"schedule:{schedule.schedule_id}",
        )
        enqueued += 1
    return enqueued


def configure_provider_budget(
    db: Session,
    tenant_id: str,
    provider: str,
    max_requests: int,
    window_seconds: int,
) -> ProviderRateLimit:
    budget = db.scalar(
        select(ProviderRateLimit).where(
            ProviderRateLimit.tenant_id == tenant_id,
            ProviderRateLimit.provider == provider,
        )
    )
    now = utc_now()
    if budget:
        budget.max_requests = max_requests
        budget.window_seconds = window_seconds
        budget.used_requests = 0
        budget.window_started_at = now
        budget.updated_at = now
    else:
        budget = ProviderRateLimit(
            tenant_id=tenant_id,
            provider=provider,
            max_requests=max_requests,
            window_seconds=window_seconds,
            window_started_at=now,
            updated_at=now,
        )
        db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def consume_provider_budget(db: Session, tenant_id: str, provider: str, units: int = 1) -> None:
    for _ in range(3):
        budget = db.scalar(
            select(ProviderRateLimit).where(
                ProviderRateLimit.tenant_id == tenant_id,
                ProviderRateLimit.provider == provider,
            )
        )
        if not budget:
            return
        now = utc_now()
        window_ends = budget.window_started_at + timedelta(seconds=budget.window_seconds)
        if now >= window_ends:
            changed = db.execute(
                update(ProviderRateLimit)
                .where(
                    ProviderRateLimit.id == budget.id,
                    ProviderRateLimit.window_started_at == budget.window_started_at,
                )
                .values(
                    used_requests=0,
                    window_started_at=now,
                    updated_at=now,
                )
            )
            db.commit()
            if changed.rowcount == 1:
                continue
            continue
        if budget.used_requests + units > budget.max_requests:
            raise ProviderRateLimitExceeded(provider, int((window_ends - now).total_seconds()) + 1)
        changed = db.execute(
            update(ProviderRateLimit)
            .where(
                ProviderRateLimit.id == budget.id,
                ProviderRateLimit.used_requests == budget.used_requests,
                ProviderRateLimit.window_started_at == budget.window_started_at,
            )
            .values(
                used_requests=budget.used_requests + units,
                updated_at=now,
            )
        )
        db.commit()
        if changed.rowcount == 1:
            return
    raise RuntimeError("Provider request budget could not be updated")


def provider_request_guard(db: Session, tenant_id: str, provider: str):
    def guard() -> None:
        consume_provider_budget(db, tenant_id, provider)

    return guard
