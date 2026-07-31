import csv
import hashlib
import io
import json
import logging
from urllib.parse import urlparse
from uuid import uuid4
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GraphEdge, GraphExport, utc_now


CONTENT_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
    "graphml": "application/graphml+xml",
}


def create_graph_export(
    db: Session,
    tenant_id: str,
    export_format: str,
    relationships: list[str],
    sink_uri: str | None,
    max_edges: int,
    created_by: str,
) -> tuple[GraphExport, object]:
    from app.services.jobs import enqueue_job

    if export_format not in CONTENT_TYPES:
        raise ValueError("Unsupported graph export format")
    if not 1 <= max_edges <= settings.graph_async_export_max_edges:
        raise ValueError(
            f"Graph export edge limit must be 1 to {settings.graph_async_export_max_edges}"
        )
    relationships = sorted(
        set(_bounded_string(value, "relationship", 120) for value in relationships)
    )
    if sink_uri:
        _validate_sink_uri(sink_uri)
    export = GraphExport(
        tenant_id=tenant_id,
        export_id=str(uuid4()),
        export_format=export_format,
        relationships_json=json.dumps(relationships),
        max_edges=max_edges,
        sink_uri=sink_uri,
        created_by=created_by,
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    job = enqueue_job(
        db,
        tenant_id=tenant_id,
        job_type="graph.export",
        payload={"export_id": export.export_id},
        created_by=created_by,
        max_attempts=3,
    )
    return export, job


def execute_graph_export(
    db: Session,
    tenant_id: str,
    export_id: str,
) -> dict:
    record = graph_export_for_tenant(db, tenant_id, export_id)
    if not record:
        raise ValueError("Graph export not found")
    if record.status == "completed":
        return graph_export_response(record)
    record.status = "running"
    record.error = None
    db.commit()
    relationships = set(json.loads(record.relationships_json or "[]"))
    statement = select(GraphEdge).where(GraphEdge.tenant_id == tenant_id)
    if relationships:
        statement = statement.where(GraphEdge.relationship.in_(relationships))
    selected = list(
        db.scalars(statement.order_by(GraphEdge.id).limit(record.max_edges + 1)).all()
    )
    truncated = len(selected) > record.max_edges
    edges = selected[: record.max_edges]
    content = _serialize_edges(record.export_format, edges)
    if len(content) > settings.graph_export_max_bytes:
        raise ValueError("Graph export exceeds the configured byte limit")
    digest = hashlib.sha256(content).hexdigest()
    storage_uri = _store_export(record, content, digest)
    record.status = "completed"
    record.edge_count = len(edges)
    record.truncated = truncated
    record.storage_uri = storage_uri
    record.sha256 = digest
    record.size_bytes = len(content)
    record.error = None
    record.completed_at = utc_now()
    db.commit()
    db.refresh(record)
    _queue_completion_event(db, record)
    return graph_export_response(record)


def mark_graph_export_error(
    db: Session,
    tenant_id: str,
    export_id: str,
    error: str,
) -> None:
    record = graph_export_for_tenant(db, tenant_id, export_id)
    if record:
        record.status = "failed"
        record.error = error
        db.commit()


def load_graph_export(record: GraphExport) -> bytes:
    if not record.storage_uri or record.status != "completed":
        raise ValueError("Graph export is not available")
    if record.storage_uri.startswith("local://"):
        object_key = record.storage_uri.removeprefix("local://")
        root = settings.graph_export_local_directory.resolve()
        path = (root / object_key).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local graph export path")
        content = path.read_bytes()
    elif record.storage_uri.startswith("s3://"):
        bucket, key = _s3_location(record.storage_uri)
        content = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read(
            settings.graph_export_max_bytes + 1
        )
    else:
        raise ValueError("Unsupported graph export URI")
    if len(content) > settings.graph_export_max_bytes:
        raise ValueError("Stored graph export exceeds the configured byte limit")
    if record.sha256 and hashlib.sha256(content).hexdigest() != record.sha256:
        raise ValueError("Stored graph export integrity check failed")
    return content


def graph_export_for_tenant(
    db: Session,
    tenant_id: str,
    export_id: str,
) -> GraphExport | None:
    return db.scalar(
        select(GraphExport).where(
            GraphExport.tenant_id == tenant_id,
            GraphExport.export_id == export_id,
        )
    )


def graph_export_response(record: GraphExport) -> dict:
    return {
        "export_id": record.export_id,
        "format": record.export_format,
        "relationships": json.loads(record.relationships_json or "[]"),
        "max_edges": record.max_edges,
        "sink_uri": record.sink_uri,
        "status": record.status,
        "edge_count": record.edge_count,
        "truncated": record.truncated,
        "storage_uri": record.storage_uri,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "error": record.error,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "completed_at": record.completed_at,
    }


def _serialize_edges(export_format: str, edges: list[GraphEdge]) -> bytes:
    rows = [_edge_row(edge) for edge in edges]
    if export_format == "json":
        return json.dumps({"edges": rows}, separators=(",", ":"), sort_keys=True).encode()
    if export_format == "csv":
        output = io.StringIO()
        fieldnames = [
            "source_type",
            "source_id",
            "relationship",
            "target_type",
            "target_id",
            "metadata",
            "created_at",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode()
    node_ids: dict[tuple[str, str], str] = {}
    for edge in edges:
        for node in ((edge.source_type, edge.source_id), (edge.target_type, edge.target_id)):
            node_ids.setdefault(node, f"n{len(node_ids) + 1}")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '<key id="type" for="node" attr.name="type" attr.type="string"/>',
        '<key id="external_id" for="node" attr.name="external_id" attr.type="string"/>',
        '<key id="relationship" for="edge" attr.name="relationship" attr.type="string"/>',
        '<graph edgedefault="directed">',
    ]
    lines.extend(
        f'<node id="{node_id}"><data key="type">{escape(node[0])}</data>'
        f'<data key="external_id">{escape(node[1])}</data></node>'
        for node, node_id in node_ids.items()
    )
    lines.extend(
        f'<edge id="e{index}" source="{node_ids[(edge.source_type, edge.source_id)]}" '
        f'target="{node_ids[(edge.target_type, edge.target_id)]}">'
        f'<data key="relationship">{escape(edge.relationship)}</data></edge>'
        for index, edge in enumerate(edges, 1)
    )
    lines.extend(["</graph>", "</graphml>"])
    return "\n".join(lines).encode()


def _edge_row(edge: GraphEdge) -> dict:
    return {
        "source_type": edge.source_type,
        "source_id": edge.source_id,
        "relationship": edge.relationship,
        "target_type": edge.target_type,
        "target_id": edge.target_id,
        "metadata": edge.metadata_json,
        "created_at": edge.created_at.isoformat(),
    }


def _store_export(record: GraphExport, content: bytes, digest: str) -> str:
    extension = {"json": "json", "csv": "csv", "graphml": "graphml"}[
        record.export_format
    ]
    prefix = settings.graph_export_prefix.strip("/")
    object_key = "/".join(
        part
        for part in (
            prefix,
            record.tenant_id,
            f"{record.export_id}.{extension}",
        )
        if part
    )
    if record.sink_uri:
        _validate_sink_uri(record.sink_uri)
        bucket, key = _s3_location(record.sink_uri)
        _s3_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=CONTENT_TYPES[record.export_format],
            Metadata={"sha256": digest},
        )
        return record.sink_uri
    if settings.graph_export_backend == "local":
        root = settings.graph_export_local_directory.resolve()
        path = (root / object_key).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local graph export path")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return f"local://{object_key}"
    if settings.graph_export_backend == "s3":
        if not settings.graph_export_bucket:
            raise RuntimeError("ODG_GRAPH_EXPORT_BUCKET is required for S3 graph exports")
        _s3_client().put_object(
            Bucket=settings.graph_export_bucket,
            Key=object_key,
            Body=content,
            ContentType=CONTENT_TYPES[record.export_format],
            Metadata={"sha256": digest},
        )
        return f"s3://{settings.graph_export_bucket}/{object_key}"
    raise RuntimeError(f"Unsupported graph export backend: {settings.graph_export_backend}")


def _validate_sink_uri(sink_uri: str) -> None:
    parsed = urlparse(sink_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Graph export sink_uri must be an s3://bucket/key URI")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Graph export sink_uri cannot contain credentials or query parameters")
    if parsed.netloc not in settings.graph_export_allowed_sink_buckets:
        raise ValueError("Graph export sink bucket is not allowlisted")


def _s3_location(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Invalid S3 graph export URI")
    return parsed.netloc, parsed.path.lstrip("/")


def _s3_client():
    import boto3

    kwargs = {}
    if settings.graph_export_endpoint_url:
        kwargs["endpoint_url"] = settings.graph_export_endpoint_url
    if settings.graph_export_region:
        kwargs["region_name"] = settings.graph_export_region
    return boto3.client("s3", **kwargs)


def _bounded_string(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Graph export {field} is invalid")
    return value.strip()


def _queue_completion_event(db: Session, record: GraphExport) -> None:
    try:
        from app.services.integrations import queue_integration_event

        queue_integration_event(
            db,
            record.tenant_id,
            "graph.export.completed",
            graph_export_response(record),
            created_by=f"graph-export:{record.export_id}",
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("failed to queue graph export event")
