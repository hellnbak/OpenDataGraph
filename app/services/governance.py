import json
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GovernanceReviewTask, utc_now


OPEN_STATUSES = ("open", "in-progress")


def create_review_task(
    db: Session,
    tenant_id: str,
    task_type: str,
    subject_id: str,
    title: str,
    created_by: str,
    details: dict | None = None,
    priority: str = "normal",
    due_at=None,
) -> GovernanceReviewTask:
    existing = db.scalar(
        select(GovernanceReviewTask).where(
            GovernanceReviewTask.tenant_id == tenant_id,
            GovernanceReviewTask.task_type == task_type,
            GovernanceReviewTask.subject_id == subject_id,
            GovernanceReviewTask.status.in_(OPEN_STATUSES),
        )
    )
    if existing:
        return existing
    if priority not in {"low", "normal", "high", "critical"}:
        raise ValueError("Governance task priority is invalid")
    task = GovernanceReviewTask(
        tenant_id=tenant_id,
        task_id=str(uuid4()),
        task_type=task_type,
        subject_id=subject_id,
        title=title,
        priority=priority,
        details_json=json.dumps(details or {}),
        due_at=due_at
        or utc_now() + timedelta(hours=settings.governance_default_sla_hours),
        created_by=created_by,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    _queue_governance_event(db, task, "governance.review.created")
    return task


def assign_review_task(
    db: Session,
    task: GovernanceReviewTask,
    assigned_to: str,
) -> GovernanceReviewTask:
    if task.status not in OPEN_STATUSES:
        raise ValueError("Only open governance tasks can be assigned")
    task.assigned_to = assigned_to
    task.status = "in-progress"
    db.commit()
    db.refresh(task)
    return task


def complete_review_task(
    db: Session,
    tenant_id: str,
    task_type: str,
    subject_id: str,
    completed_by: str,
    outcome: str,
) -> int:
    tasks = list(
        db.scalars(
            select(GovernanceReviewTask).where(
                GovernanceReviewTask.tenant_id == tenant_id,
                GovernanceReviewTask.task_type == task_type,
                GovernanceReviewTask.subject_id == subject_id,
                GovernanceReviewTask.status.in_(OPEN_STATUSES),
            )
        ).all()
    )
    now = utc_now()
    for task in tasks:
        details = json.loads(task.details_json or "{}")
        details["outcome"] = outcome
        task.details_json = json.dumps(details)
        task.status = "completed"
        task.completed_by = completed_by
        task.completed_at = now
    db.commit()
    for task in tasks:
        _queue_governance_event(db, task, "governance.review.completed")
    return len(tasks)


def governance_sla_metrics(db: Session, tenant_id: str) -> dict:
    now = utc_now()
    due_soon = now + timedelta(hours=settings.governance_due_soon_hours)
    tasks = list(
        db.scalars(
            select(GovernanceReviewTask).where(
                GovernanceReviewTask.tenant_id == tenant_id
            )
        ).all()
    )
    open_tasks = [task for task in tasks if task.status in OPEN_STATUSES]
    completed = [task for task in tasks if task.completed_at is not None]
    resolution_hours = [
        (task.completed_at - task.created_at).total_seconds() / 3600
        for task in completed
    ]
    by_type: dict[str, dict[str, int]] = {}
    for task in tasks:
        metrics = by_type.setdefault(
            task.task_type,
            {"total": 0, "open": 0, "overdue": 0, "completed": 0},
        )
        metrics["total"] += 1
        if task.status in OPEN_STATUSES:
            metrics["open"] += 1
            if task.due_at < now:
                metrics["overdue"] += 1
        elif task.status == "completed":
            metrics["completed"] += 1
    return {
        "total": len(tasks),
        "open": len(open_tasks),
        "overdue": sum(task.due_at < now for task in open_tasks),
        "due_soon": sum(now <= task.due_at <= due_soon for task in open_tasks),
        "completed": len(completed),
        "average_resolution_hours": (
            round(sum(resolution_hours) / len(resolution_hours), 2)
            if resolution_hours
            else None
        ),
        "by_type": by_type,
    }


def notify_overdue_reviews(
    db: Session,
    tenant_id: str,
    limit: int = 500,
) -> dict:
    tasks = list(
        db.scalars(
            select(GovernanceReviewTask)
            .where(
                GovernanceReviewTask.tenant_id == tenant_id,
                GovernanceReviewTask.status.in_(OPEN_STATUSES),
                GovernanceReviewTask.due_at < utc_now(),
                GovernanceReviewTask.sla_notified_at.is_(None),
            )
            .order_by(GovernanceReviewTask.due_at)
            .limit(limit)
        ).all()
    )
    notified = 0
    for task in tasks:
        if _queue_governance_event(db, task, "governance.review.overdue"):
            task.sla_notified_at = utc_now()
            db.commit()
            notified += 1
    return {"examined": len(tasks), "notified": notified}


def review_task_response(task: GovernanceReviewTask) -> dict:
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "subject_id": task.subject_id,
        "title": task.title,
        "priority": task.priority,
        "status": task.status,
        "assigned_to": task.assigned_to,
        "details": json.loads(task.details_json or "{}"),
        "due_at": task.due_at,
        "overdue": task.status in OPEN_STATUSES and task.due_at < utc_now(),
        "created_by": task.created_by,
        "created_at": task.created_at,
        "completed_by": task.completed_by,
        "completed_at": task.completed_at,
        "sla_notified_at": task.sla_notified_at,
    }


def _queue_governance_event(
    db: Session,
    task: GovernanceReviewTask,
    event_type: str,
) -> bool:
    try:
        from app.services.integrations import queue_integration_event

        deliveries = queue_integration_event(
            db,
            task.tenant_id,
            event_type,
            review_task_response(task),
            created_by=f"governance:{task.task_id}",
        )
        return bool(deliveries)
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("failed to queue governance notification")
        return False
