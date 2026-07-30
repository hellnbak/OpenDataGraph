import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification import classify
from app.config import settings
from app.lifecycle import calculate_lifecycle
from app.models import ClassificationReview, ConnectorRun, DataAsset, GraphEdge
from connectors.sdk import Connector


async def ingest_connector(
    db: Session,
    connector: Connector,
    cursor: str | None = None,
    max_items: int = 500,
) -> dict:
    run = ConnectorRun(source=connector.source, source_account=connector.account, cursor=cursor)
    db.add(run)
    db.commit()
    try:
        batch = connector.scan(cursor=cursor, max_items=max_items)
        imported = updated = 0
        for normalized in batch.records:
            record = normalized.as_dict()
            metadata = record.pop("metadata")
            sample = record.pop("sample")
            asset = db.scalar(select(DataAsset).where(DataAsset.external_id == record["external_id"]))
            if asset:
                for key, value in record.items():
                    setattr(asset, key, value)
                asset.metadata_json = json.dumps(metadata)
                asset.last_seen_at = datetime.utcnow()
                updated += 1
            else:
                asset = DataAsset(**record, metadata_json=json.dumps(metadata))
                db.add(asset)
                imported += 1
            result = await classify(asset.name, asset.path, asset.mime_type, sample)
            asset.sensitivity = result.sensitivity
            asset.classification_labels = ", ".join(result.labels)
            asset.business_domain = result.business_domain
            asset.classification_reason = result.reason
            asset.classification_confidence = result.confidence
            lifecycle = calculate_lifecycle(asset.created_at, asset.modified_at, asset.last_accessed_at, result.sensitivity)
            asset.age_days = lifecycle.age_days
            asset.stale_score = lifecycle.stale_score
            asset.lifecycle_state = lifecycle.state
            asset.retention_action = lifecycle.action
            asset.retention_reason = lifecycle.reason
            db.flush()
            if result.confidence < settings.classification_review_threshold:
                pending = db.scalar(
                    select(ClassificationReview).where(
                        ClassificationReview.asset_id == asset.id,
                        ClassificationReview.status == "pending",
                    )
                )
                if not pending:
                    db.add(
                        ClassificationReview(
                            asset_id=asset.id,
                            original_sensitivity=result.sensitivity,
                            original_labels=", ".join(result.labels),
                            confidence=result.confidence,
                            reason=result.reason,
                        )
                    )
            _ensure_edge(db, "asset", str(asset.id), "owned_by", "identity", asset.owner)
            _ensure_edge(db, "asset", str(asset.id), "belongs_to", "business-domain", asset.business_domain)
            _ensure_edge(db, connector.source, connector.account, "contains", "asset", str(asset.id))
        run.status = "completed"
        run.imported = imported
        run.updated = updated
        run.next_cursor = batch.next_cursor
        run.finished_at = datetime.utcnow()
        db.commit()
        return {
            "ok": True,
            "run_id": run.id,
            "source": connector.source,
            "account": connector.account,
            "imported": imported,
            "updated": updated,
            "next_cursor": batch.next_cursor,
            "complete": batch.complete,
        }
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)[:2000]
        run.finished_at = datetime.utcnow()
        db.commit()
        raise


def _ensure_edge(
    db: Session,
    source_type: str,
    source_id: str,
    relationship: str,
    target_type: str,
    target_id: str,
) -> None:
    edge = db.scalar(
        select(GraphEdge).where(
            GraphEdge.source_type == source_type,
            GraphEdge.source_id == source_id,
            GraphEdge.relationship == relationship,
            GraphEdge.target_type == target_type,
            GraphEdge.target_id == target_id,
        )
    )
    if not edge:
        db.add(
            GraphEdge(
                source_type=source_type,
                source_id=source_id,
                relationship=relationship,
                target_type=target_type,
                target_id=target_id,
            )
        )
