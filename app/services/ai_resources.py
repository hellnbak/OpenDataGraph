import json
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    AIAgent,
    AILineageObservation,
    AIResource,
    AIResourceRelationship,
    DataAsset,
    GraphEdge,
    utc_now,
)


AI_RESOURCE_TYPES = {"model", "prompt", "vector-index", "tool", "endpoint", "ai-system"}
REFERENCE_TYPES = AI_RESOURCE_TYPES | {"agent", "asset", "data_asset", "dataset"}
FORBIDDEN_METADATA_KEYS = {
    "authorization",
    "credential",
    "credentials",
    "password",
    "prompt",
    "response",
    "secret",
    "token",
}


def create_ai_resource(
    db: Session,
    tenant_id: str,
    values: dict,
    created_by: str,
) -> AIResource:
    metadata = _bounded_metadata(values.pop("metadata", {}))
    resource = AIResource(
        tenant_id=tenant_id,
        metadata_json=json.dumps(metadata, sort_keys=True),
        created_by=created_by,
        **values,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def update_ai_resource(
    db: Session,
    resource: AIResource,
    changes: dict,
) -> AIResource:
    if "metadata" in changes:
        resource.metadata_json = json.dumps(
            _bounded_metadata(changes.pop("metadata")),
            sort_keys=True,
        )
    for field, value in changes.items():
        setattr(resource, field, value)
    resource.updated_at = utc_now()
    db.commit()
    db.refresh(resource)
    return resource


def ai_resource_response(resource: AIResource) -> dict:
    return {
        "resource_key": resource.resource_key,
        "resource_type": resource.resource_type,
        "name": resource.name,
        "owner": resource.owner,
        "provider": resource.provider,
        "region": resource.region,
        "status": resource.status,
        "risk_tier": resource.risk_tier,
        "metadata": json.loads(resource.metadata_json or "{}"),
        "created_by": resource.created_by,
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
    }


def declare_relationship(
    db: Session,
    tenant_id: str,
    source: dict,
    relationship: str,
    target: dict,
    expected: bool,
    metadata: dict,
    created_by: str,
) -> tuple[AIResourceRelationship, bool]:
    _validate_reference(db, tenant_id, source)
    _validate_reference(db, tenant_id, target)
    bounded_metadata = _bounded_metadata(metadata)
    existing = _relationship(db, tenant_id, source, relationship, target)
    if existing:
        existing.expected = expected
        existing.status = "active"
        existing.metadata_json = json.dumps(bounded_metadata, sort_keys=True)
        existing.updated_at = utc_now()
        _sync_graph_edge(db, existing)
        db.commit()
        db.refresh(existing)
        return existing, False
    record = AIResourceRelationship(
        tenant_id=tenant_id,
        relationship_id=str(uuid4()),
        source_type=source["type"],
        source_id=source["id"],
        relationship=relationship,
        target_type=target["type"],
        target_id=target["id"],
        expected=expected,
        metadata_json=json.dumps(bounded_metadata, sort_keys=True),
        created_by=created_by,
    )
    db.add(record)
    db.flush()
    _sync_graph_edge(db, record)
    db.commit()
    db.refresh(record)
    return record, True


def observe_relationship(
    db: Session,
    tenant_id: str,
    event_id: str,
    source: dict,
    relationship: str,
    target: dict,
    observed_at,
    metadata: dict,
    recorded_by: str,
) -> tuple[AILineageObservation, AIResourceRelationship, bool]:
    existing_event = db.scalar(
        select(AILineageObservation).where(
            AILineageObservation.tenant_id == tenant_id,
            AILineageObservation.event_id == event_id,
        )
    )
    if existing_event:
        if (
            existing_event.source_type != source["type"]
            or existing_event.source_id != source["id"]
            or existing_event.relationship != relationship
            or existing_event.target_type != target["type"]
            or existing_event.target_id != target["id"]
        ):
            raise ValueError(
                "AI lineage event id was already used for a different relationship"
            )
        relation = db.scalar(
            select(AIResourceRelationship).where(
                AIResourceRelationship.tenant_id == tenant_id,
                AIResourceRelationship.relationship_id
                == existing_event.relationship_id,
            )
        )
        return existing_event, relation, True
    _validate_reference(db, tenant_id, source)
    _validate_reference(db, tenant_id, target)
    bounded_metadata = _bounded_metadata(metadata)
    relation = _relationship(db, tenant_id, source, relationship, target)
    if not relation:
        relation = AIResourceRelationship(
            tenant_id=tenant_id,
            relationship_id=str(uuid4()),
            source_type=source["type"],
            source_id=source["id"],
            relationship=relationship,
            target_type=target["type"],
            target_id=target["id"],
            expected=False,
            metadata_json="{}",
            created_by=recorded_by,
        )
        db.add(relation)
        db.flush()
    drift_detected = not relation.expected or relation.status != "active"
    normalized_time = observed_at.replace(tzinfo=None)
    relation.observation_count += 1
    relation.first_observed_at = relation.first_observed_at or normalized_time
    relation.last_observed_at = normalized_time
    relation.updated_at = utc_now()
    observation = AILineageObservation(
        tenant_id=tenant_id,
        event_id=event_id,
        relationship_id=relation.relationship_id,
        source_type=source["type"],
        source_id=source["id"],
        relationship=relationship,
        target_type=target["type"],
        target_id=target["id"],
        drift_detected=drift_detected,
        metadata_json=json.dumps(bounded_metadata, sort_keys=True),
        observed_at=normalized_time,
    )
    db.add(observation)
    _sync_graph_edge(db, relation)
    db.commit()
    db.refresh(observation)
    db.refresh(relation)
    return observation, relation, False


def relationship_response(record: AIResourceRelationship) -> dict:
    return {
        "relationship_id": record.relationship_id,
        "source": {"type": record.source_type, "id": record.source_id},
        "relationship": record.relationship,
        "target": {"type": record.target_type, "id": record.target_id},
        "expected": record.expected,
        "status": record.status,
        "observation_count": record.observation_count,
        "metadata": json.loads(record.metadata_json or "{}"),
        "first_observed_at": record.first_observed_at,
        "last_observed_at": record.last_observed_at,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def observation_response(record: AILineageObservation) -> dict:
    return {
        "event_id": record.event_id,
        "relationship_id": record.relationship_id,
        "source": {"type": record.source_type, "id": record.source_id},
        "relationship": record.relationship,
        "target": {"type": record.target_type, "id": record.target_id},
        "drift_detected": record.drift_detected,
        "metadata": json.loads(record.metadata_json or "{}"),
        "observed_at": record.observed_at,
        "recorded_at": record.recorded_at,
    }


def _relationship(
    db: Session,
    tenant_id: str,
    source: dict,
    relationship: str,
    target: dict,
) -> AIResourceRelationship | None:
    return db.scalar(
        select(AIResourceRelationship).where(
            AIResourceRelationship.tenant_id == tenant_id,
            AIResourceRelationship.source_type == source["type"],
            AIResourceRelationship.source_id == source["id"],
            AIResourceRelationship.relationship == relationship,
            AIResourceRelationship.target_type == target["type"],
            AIResourceRelationship.target_id == target["id"],
        )
    )


def _validate_reference(db: Session, tenant_id: str, reference: dict) -> None:
    reference_type = reference["type"]
    reference_id = reference["id"]
    if reference_type not in REFERENCE_TYPES:
        raise ValueError("AI lineage reference type is unsupported")
    if reference_type in AI_RESOURCE_TYPES:
        found = db.scalar(
            select(AIResource.id).where(
                AIResource.tenant_id == tenant_id,
                AIResource.resource_type == reference_type,
                AIResource.resource_key == reference_id,
            )
        )
        if found is None:
            raise ValueError("AI lineage resource is not registered")
    elif reference_type == "agent":
        found = db.scalar(
            select(AIAgent.id).where(
                AIAgent.tenant_id == tenant_id,
                AIAgent.key == reference_id,
            )
        )
        if found is None:
            raise ValueError("AI lineage agent is not registered")
    elif reference_type in {"asset", "data_asset"}:
        conditions = [DataAsset.external_id == reference_id]
        try:
            conditions.append(DataAsset.id == int(reference_id))
        except ValueError:
            pass
        found = db.scalar(
            select(DataAsset.id).where(
                DataAsset.tenant_id == tenant_id,
                or_(*conditions),
            )
        )
        if found is None:
            raise ValueError("AI lineage data asset is not registered")


def _sync_graph_edge(db: Session, relationship: AIResourceRelationship) -> None:
    edge = db.scalar(
        select(GraphEdge).where(
            GraphEdge.tenant_id == relationship.tenant_id,
            GraphEdge.source_type == relationship.source_type,
            GraphEdge.source_id == relationship.source_id,
            GraphEdge.relationship == relationship.relationship,
            GraphEdge.target_type == relationship.target_type,
            GraphEdge.target_id == relationship.target_id,
        )
    )
    metadata = {
        "relationship_id": relationship.relationship_id,
        "expected": relationship.expected,
        "status": relationship.status,
        "observation_count": relationship.observation_count,
        "first_observed_at": (
            relationship.first_observed_at.isoformat()
            if relationship.first_observed_at
            else None
        ),
        "last_observed_at": (
            relationship.last_observed_at.isoformat()
            if relationship.last_observed_at
            else None
        ),
    }
    if edge:
        edge.metadata_json = json.dumps(metadata, sort_keys=True)
        return
    db.add(
        GraphEdge(
            tenant_id=relationship.tenant_id,
            source_type=relationship.source_type,
            source_id=relationship.source_id,
            relationship=relationship.relationship,
            target_type=relationship.target_type,
            target_id=relationship.target_id,
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def _bounded_metadata(metadata: dict) -> dict:
    if not isinstance(metadata, dict):
        raise ValueError("AI resource metadata must be an object")
    serialized = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode()) > 32_768:
        raise ValueError("AI resource metadata exceeds 32 KiB")

    def inspect(value, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).lower().replace("-", "_")
                if normalized in FORBIDDEN_METADATA_KEYS:
                    raise ValueError(
                        f"AI resource metadata cannot include {'.'.join((*path, str(key)))}"
                    )
                inspect(item, (*path, str(key)))
        elif isinstance(value, list):
            if len(value) > 1000:
                raise ValueError("AI resource metadata list is too large")
            for item in value:
                inspect(item, path)
        elif isinstance(value, str) and len(value) > 2000:
            raise ValueError("AI resource metadata value is too large")
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("AI resource metadata contains an unsupported value")

    inspect(metadata)
    return metadata
