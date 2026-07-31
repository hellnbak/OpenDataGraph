import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    schedule_type: str = "interval",
    cron_expression: str | None = None,
    timezone_name: str = "UTC",
    maintenance_windows: list[dict] | None = None,
) -> ConnectorSchedule:
    from app.services.jobs import validate_job_payload
    from connectors.registry import connector_registration, enforce_connector_policy

    normalized_payload = {
        "connector_type": connector_type,
        "account": account,
        **payload,
    }
    validate_job_payload("connector.scan", normalized_payload)
    registration = connector_registration(connector_type)
    enforce_connector_policy(db, tenant_id, registration.manifest)
    maintenance_windows = maintenance_windows or []
    validate_schedule_definition(
        schedule_type,
        interval_seconds,
        cron_expression,
        timezone_name,
        maintenance_windows,
    )
    now = utc_now()
    schedule = ConnectorSchedule(
        tenant_id=tenant_id,
        schedule_id=str(uuid4()),
        connector_type=connector_type,
        account=account,
        interval_seconds=interval_seconds,
        schedule_type=schedule_type,
        cron_expression=cron_expression,
        timezone=timezone_name,
        maintenance_windows_json=json.dumps(maintenance_windows),
        payload_json=json.dumps(normalized_payload),
        enabled=enabled,
        next_run_at=(
            next_cron_run(cron_expression or "", timezone_name, now, maintenance_windows)
            if schedule_type == "cron"
            else skip_maintenance(now, timezone_name, maintenance_windows)
        ),
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
        next_run = next_schedule_run(schedule, now)
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


def validate_schedule_definition(
    schedule_type: str,
    interval_seconds: int,
    cron_expression: str | None,
    timezone_name: str,
    maintenance_windows: list[dict],
) -> None:
    if schedule_type not in {"interval", "cron"}:
        raise ValueError("Schedule type must be interval or cron")
    if not 60 <= interval_seconds <= 604800:
        raise ValueError("Interval must be between 60 seconds and 7 days")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Schedule timezone is invalid") from exc
    if schedule_type == "cron":
        if not cron_expression:
            raise ValueError("Cron schedules require cron_expression")
        _parse_cron(cron_expression)
    elif cron_expression:
        raise ValueError("Interval schedules cannot define cron_expression")
    _validate_maintenance_windows(maintenance_windows)


def next_schedule_run(schedule: ConnectorSchedule, after: datetime) -> datetime:
    windows = json.loads(schedule.maintenance_windows_json or "[]")
    if schedule.schedule_type == "cron":
        return next_cron_run(schedule.cron_expression or "", schedule.timezone, after, windows)
    candidate = schedule.next_run_at
    while candidate <= after:
        candidate += timedelta(seconds=schedule.interval_seconds)
    return skip_maintenance(candidate, schedule.timezone, windows)


def next_cron_run(
    expression: str,
    timezone_name: str,
    after: datetime,
    maintenance_windows: list[dict] | None = None,
) -> datetime:
    minutes, hours, days, months, weekdays, day_wildcard, weekday_wildcard = _parse_cron(expression)
    timezone = ZoneInfo(timezone_name)
    after_utc = after.astimezone(UTC) if after.tzinfo else after.replace(tzinfo=UTC)
    candidate = after_utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
    maintenance_windows = maintenance_windows or []
    for _ in range(527_040):
        local = candidate.astimezone(timezone)
        cron_weekday = (local.weekday() + 1) % 7
        day_match = local.day in days
        weekday_match = cron_weekday in weekdays
        calendar_match = (
            day_match and weekday_match
            if day_wildcard or weekday_wildcard
            else day_match or weekday_match
        )
        if (
            local.minute in minutes
            and local.hour in hours
            and local.month in months
            and calendar_match
            and not _in_maintenance(local, maintenance_windows)
        ):
            return candidate.replace(tzinfo=None)
        candidate += timedelta(minutes=1)
    raise ValueError("Cron schedule has no eligible run within one year")


def skip_maintenance(
    candidate: datetime,
    timezone_name: str,
    maintenance_windows: list[dict],
) -> datetime:
    timezone = ZoneInfo(timezone_name)
    aware = candidate.astimezone(UTC) if candidate.tzinfo else candidate.replace(tzinfo=UTC)
    for _ in range(10_080):
        if not _in_maintenance(aware.astimezone(timezone), maintenance_windows):
            return aware.replace(tzinfo=None)
        aware += timedelta(minutes=1)
    raise ValueError("Maintenance windows leave no eligible time within seven days")


def _parse_cron(
    expression: str,
) -> tuple[set[int], set[int], set[int], set[int], set[int], bool, bool]:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron expression must contain five fields")
    minute, hour, day, month, weekday = fields
    return (
        _parse_cron_field(minute, 0, 59),
        _parse_cron_field(hour, 0, 23),
        _parse_cron_field(day, 1, 31),
        _parse_cron_field(month, 1, 12),
        _parse_cron_field(weekday, 0, 7, normalize_weekday=True),
        day == "*",
        weekday == "*",
    )


def _parse_cron_field(
    field: str,
    minimum: int,
    maximum: int,
    normalize_weekday: bool = False,
) -> set[int]:
    values: set[int] = set()
    for item in field.split(","):
        base, separator, step_text = item.partition("/")
        if separator:
            if not step_text.isdigit() or int(step_text) < 1:
                raise ValueError("Cron steps must be positive integers")
            step = int(step_text)
        else:
            step = 1
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError("Cron ranges must use integers")
            start, end = int(start_text), int(end_text)
        elif base.isdigit():
            start = end = int(base)
        else:
            raise ValueError("Cron fields support integers, ranges, lists, and steps")
        if start < minimum or end > maximum or start > end:
            raise ValueError("Cron field value is outside its allowed range")
        for value in range(start, end + 1, step):
            values.add(0 if normalize_weekday and value == 7 else value)
    if not values:
        raise ValueError("Cron field cannot be empty")
    return values


def _validate_maintenance_windows(windows: list[dict]) -> None:
    if not isinstance(windows, list) or len(windows) > 20:
        raise ValueError("Maintenance windows must be an array of at most 20 entries")
    for window in windows:
        if not isinstance(window, dict) or set(window) - {"days", "start", "end"}:
            raise ValueError("Maintenance windows support only days, start, and end")
        days = window.get("days", list(range(7)))
        if (
            not isinstance(days, list)
            or not days
            or any(not isinstance(day, int) or day < 0 or day > 6 for day in days)
        ):
            raise ValueError("Maintenance window days must use Monday=0 through Sunday=6")
        start = _clock_minutes(window.get("start"))
        end = _clock_minutes(window.get("end"))
        if start == end:
            raise ValueError("Maintenance window start and end must differ")


def _clock_minutes(value: object) -> int:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError("Maintenance window times must use HH:MM")
    hour_text, minute_text = value.split(":")
    if not hour_text.isdigit() or not minute_text.isdigit():
        raise ValueError("Maintenance window times must use HH:MM")
    hour, minute = int(hour_text), int(minute_text)
    if hour > 23 or minute > 59:
        raise ValueError("Maintenance window times must use a valid 24-hour clock")
    return hour * 60 + minute


def _in_maintenance(local: datetime, windows: list[dict]) -> bool:
    current = local.hour * 60 + local.minute
    for window in windows:
        days = set(window.get("days", range(7)))
        start = _clock_minutes(window["start"])
        end = _clock_minutes(window["end"])
        if start < end and local.weekday() in days and start <= current < end:
            return True
        if start > end:
            if local.weekday() in days and current >= start:
                return True
            previous_day = (local.weekday() - 1) % 7
            if previous_day in days and current < end:
                return True
    return False


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
