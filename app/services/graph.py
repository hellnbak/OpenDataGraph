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


def explain_paths(
    db: Session,
    tenant_id: str,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    max_depth: int,
    direction: str = "outbound",
    max_paths: int = 10,
) -> dict:
    bounded_depth = min(max_depth, settings.graph_max_depth)
    source = (source_type, source_id)
    target = (target_type, target_id)
    queue: list[tuple[tuple[str, str], list[GraphEdge], set[tuple[str, str]]]] = [
        (source, [], {source})
    ]
    paths: list[dict] = []
    while queue and len(paths) < max_paths:
        node, path, visited = queue.pop(0)
        if len(path) >= bounded_depth:
            continue
        conditions = []
        if direction in {"outbound", "both"}:
            conditions.append(
                and_(GraphEdge.source_type == node[0], GraphEdge.source_id == node[1])
            )
        if direction in {"inbound", "both"}:
            conditions.append(
                and_(GraphEdge.target_type == node[0], GraphEdge.target_id == node[1])
            )
        edges = db.scalars(
            select(GraphEdge)
            .where(GraphEdge.tenant_id == tenant_id, or_(*conditions))
            .order_by(GraphEdge.id)
            .limit(1000)
        )
        for edge in edges:
            if (edge.source_type, edge.source_id) == node:
                next_node = (edge.target_type, edge.target_id)
            else:
                next_node = (edge.source_type, edge.source_id)
            if next_node in visited:
                continue
            next_path = [*path, edge]
            if next_node == target:
                paths.append(_path_response(source, next_path, direction))
                if len(paths) >= max_paths:
                    break
            else:
                queue.append((next_node, next_path, {*visited, next_node}))
    return {
        "source": {"type": source_type, "id": source_id},
        "target": {"type": target_type, "id": target_id},
        "direction": direction,
        "max_depth": bounded_depth,
        "paths": paths,
        "found": bool(paths),
        "truncated": len(paths) >= max_paths,
    }


def export_graph_edges(
    db: Session,
    tenant_id: str,
    relationships: set[str],
    limit: int,
) -> dict:
    bounded_limit = min(limit, settings.graph_max_export_edges)
    statement = select(GraphEdge).where(GraphEdge.tenant_id == tenant_id)
    if relationships:
        statement = statement.where(GraphEdge.relationship.in_(relationships))
    statement = statement.order_by(GraphEdge.id).limit(bounded_limit + 1)
    rows = list(db.scalars(statement).all())
    truncated = len(rows) > bounded_limit
    rows = rows[:bounded_limit]
    return {
        "tenant_id": tenant_id,
        "edges": [_edge_response(edge) for edge in rows],
        "count": len(rows),
        "truncated": truncated,
    }


def _path_response(
    source: tuple[str, str],
    path: list[GraphEdge],
    direction: str,
) -> dict:
    current = source
    steps = []
    for edge in path:
        edge_source = (edge.source_type, edge.source_id)
        edge_target = (edge.target_type, edge.target_id)
        if current == edge_source:
            next_node = edge_target
            explanation = (
                f"{edge.source_type} {edge.source_id} {edge.relationship} "
                f"{edge.target_type} {edge.target_id}"
            )
        else:
            next_node = edge_source
            explanation = (
                f"{edge.target_type} {edge.target_id} is reached through inbound "
                f"{edge.relationship} from {edge.source_type} {edge.source_id}"
            )
        steps.append(
            {
                "edge": _edge_response(edge),
                "from": {"type": current[0], "id": current[1]},
                "to": {"type": next_node[0], "id": next_node[1]},
                "explanation": explanation,
            }
        )
        current = next_node
    return {
        "length": len(path),
        "direction": direction,
        "steps": steps,
        "explanation": " → ".join(step["explanation"] for step in steps),
    }


def _edge_response(edge: GraphEdge) -> dict:
    return {
        "id": edge.id,
        "source": {"type": edge.source_type, "id": edge.source_id},
        "relationship": edge.relationship,
        "target": {"type": edge.target_type, "id": edge.target_id},
        "metadata": json.loads(edge.metadata_json or "{}"),
        "created_at": edge.created_at,
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
