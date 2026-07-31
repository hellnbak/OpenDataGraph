import hashlib
import json
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GraphEdge, LineageEvent


def ingest_openlineage_event(db: Session, tenant_id: str, payload: dict) -> dict:
    _validate_openlineage(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    event_id = hashlib.sha256(canonical.encode()).hexdigest()
    existing = db.scalar(
        select(LineageEvent).where(
            LineageEvent.tenant_id == tenant_id,
            LineageEvent.event_id == event_id,
        )
    )
    if existing:
        return {"ok": True, "idempotent": True, "event_id": event_id, "edges_created": 0}
    run_id = payload["run"]["runId"]
    job_namespace = payload["job"]["namespace"]
    job_name = payload["job"]["name"]
    event = LineageEvent(
        tenant_id=tenant_id,
        event_id=event_id,
        event_type=payload["eventType"],
        event_time=_event_time(payload["eventTime"]),
        run_id=run_id,
        job_namespace=job_namespace,
        job_name=job_name,
        producer=payload.get("producer"),
        payload_json=canonical,
    )
    db.add(event)
    job_id = f"{job_namespace}/{job_name}"
    created = _ensure_edge(
        db,
        tenant_id,
        "lineage-run",
        run_id,
        "instance_of",
        "lineage-job",
        job_id,
        {"event_id": event_id, "event_type": payload["eventType"]},
    )
    input_ids = []
    output_ids = []
    for dataset in payload.get("inputs", []):
        dataset_id = f"{dataset['namespace']}/{dataset['name']}"
        input_ids.append(dataset_id)
        created += _ensure_edge(
            db,
            tenant_id,
            "dataset",
            dataset_id,
            "input_to",
            "lineage-job",
            job_id,
            {"event_id": event_id, "run_id": run_id},
        )
    for dataset in payload.get("outputs", []):
        dataset_id = f"{dataset['namespace']}/{dataset['name']}"
        output_ids.append(dataset_id)
        created += _ensure_edge(
            db,
            tenant_id,
            "lineage-job",
            job_id,
            "produces",
            "dataset",
            dataset_id,
            {"event_id": event_id, "run_id": run_id},
        )
    for input_id in input_ids:
        for output_id in output_ids:
            created += _ensure_edge(
                db,
                tenant_id,
                "dataset",
                input_id,
                "transforms_into",
                "dataset",
                output_id,
                {"event_id": event_id, "run_id": run_id, "job": job_id},
            )
    db.commit()
    return {"ok": True, "idempotent": False, "event_id": event_id, "edges_created": created}


def query_graph(
    db: Session,
    tenant_id: str,
    start_type: str,
    start_id: str,
    max_depth: int,
    direction: str,
    relationships: set[str],
    max_edges: int = 5000,
) -> dict:
    bounded_depth = min(max_depth, settings.graph_max_depth)
    start = (start_type, start_id)
    frontier = {start}
    depths = {start: 0}
    edges_by_id: dict[int, GraphEdge] = {}
    truncated = False
    for depth in range(1, bounded_depth + 1):
        if not frontier or len(edges_by_id) >= max_edges:
            truncated = len(edges_by_id) >= max_edges
            break
        conditions = []
        for node_type, node_id in frontier:
            if direction in {"outbound", "both"}:
                conditions.append(and_(GraphEdge.source_type == node_type, GraphEdge.source_id == node_id))
            if direction in {"inbound", "both"}:
                conditions.append(and_(GraphEdge.target_type == node_type, GraphEdge.target_id == node_id))
        statement = select(GraphEdge).where(GraphEdge.tenant_id == tenant_id, or_(*conditions))
        if relationships:
            statement = statement.where(GraphEdge.relationship.in_(relationships))
        rows = list(db.scalars(statement.limit(max_edges - len(edges_by_id))).all())
        next_frontier = set()
        for edge in rows:
            edges_by_id[edge.id] = edge
            for node in (
                (edge.source_type, edge.source_id),
                (edge.target_type, edge.target_id),
            ):
                if node not in depths:
                    depths[node] = depth
                    next_frontier.add(node)
        frontier = next_frontier
    nodes = [
        {"type": node_type, "id": node_id, "depth": depth}
        for (node_type, node_id), depth in sorted(depths.items(), key=lambda item: (item[1], item[0]))
    ]
    edges = [
        {
            "id": edge.id,
            "source": {"type": edge.source_type, "id": edge.source_id},
            "relationship": edge.relationship,
            "target": {"type": edge.target_type, "id": edge.target_id},
            "metadata": json.loads(edge.metadata_json or "{}"),
            "created_at": edge.created_at,
        }
        for edge in edges_by_id.values()
    ]
    return {
        "start": {"type": start_type, "id": start_id},
        "direction": direction,
        "max_depth": bounded_depth,
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
    }


def _ensure_edge(
    db: Session,
    tenant_id: str,
    source_type: str,
    source_id: str,
    relationship: str,
    target_type: str,
    target_id: str,
    metadata: dict,
) -> int:
    existing = db.scalar(
        select(GraphEdge).where(
            GraphEdge.tenant_id == tenant_id,
            GraphEdge.source_type == source_type,
            GraphEdge.source_id == source_id,
            GraphEdge.relationship == relationship,
            GraphEdge.target_type == target_type,
            GraphEdge.target_id == target_id,
        )
    )
    if existing:
        existing.metadata_json = json.dumps(metadata)
        return 0
    db.add(
        GraphEdge(
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            relationship=relationship,
            target_type=target_type,
            target_id=target_id,
            metadata_json=json.dumps(metadata),
        )
    )
    return 1


def _validate_openlineage(payload: dict) -> None:
    if not isinstance(payload, dict) or len(json.dumps(payload).encode()) > 1024 * 1024:
        raise ValueError("OpenLineage event must be an object no larger than 1 MiB")
    if payload.get("eventType") not in {"START", "RUNNING", "COMPLETE", "ABORT", "FAIL", "OTHER"}:
        raise ValueError("OpenLineage eventType is invalid")
    if not isinstance(payload.get("eventTime"), str):
        raise ValueError("OpenLineage eventTime is required")
    run = payload.get("run")
    job = payload.get("job")
    if not isinstance(run, dict) or not isinstance(run.get("runId"), str) or not run["runId"]:
        raise ValueError("OpenLineage run.runId is required")
    if not isinstance(job, dict) or not all(isinstance(job.get(key), str) and job[key] for key in ("namespace", "name")):
        raise ValueError("OpenLineage job namespace and name are required")
    for collection in ("inputs", "outputs"):
        datasets = payload.get(collection, [])
        if not isinstance(datasets, list) or len(datasets) > 1000:
            raise ValueError(f"OpenLineage {collection} must be a bounded array")
        for dataset in datasets:
            if not isinstance(dataset, dict) or not all(
                isinstance(dataset.get(key), str) and dataset[key] for key in ("namespace", "name")
            ):
                raise ValueError(f"OpenLineage {collection} require namespace and name")


def _event_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError("OpenLineage eventTime must be ISO 8601") from exc
