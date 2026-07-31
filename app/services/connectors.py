import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification import classify
from app.config import settings
from app.lifecycle import calculate_lifecycle
from app.models import ClassificationReview, ConnectorRun, DataAsset, GraphEdge, utc_now
from app.services.search import index_asset
from app.services.schedules import ProviderRateLimitExceeded
from connectors.sdk import Connector


REDACTED_ERROR_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)((?:authorization|token|password|secret|api[_-]?key)"
        r"[\"'\s]*[:=][\"'\s]*)[^,\s;}\]]+"
    ),
    re.compile(r"(?i)([?&](?:authorization|token|password|secret|api[_-]?key)=)[^&\s]+"),
)


async def ingest_connector(
    db: Session,
    connector: Connector,
    cursor: str | None = None,
    max_items: int = 500,
    tenant_id: str = "default",
) -> dict:
    run = ConnectorRun(
        tenant_id=tenant_id,
        source=connector.source,
        source_account=connector.account,
        cursor=cursor,
        connector_version=(
            connector.manifest.version if getattr(connector, "manifest", None) else None
        ),
        capability_digest=(
            connector.manifest.digest() if getattr(connector, "manifest", None) else None
        ),
        capability_policy_version=getattr(connector, "capability_policy_version", None),
    )
    db.add(run)
    db.commit()
    try:
        batch = connector.scan(cursor=cursor, max_items=max_items)
        imported = updated = 0
        indexed_assets = []
        for normalized in batch.records:
            record = normalized.as_dict()
            metadata = record.pop("metadata")
            sample = record.pop("sample")
            asset = db.scalar(
                select(DataAsset).where(
                    DataAsset.tenant_id == tenant_id,
                    DataAsset.external_id == record["external_id"],
                )
            )
            if asset:
                for key, value in record.items():
                    setattr(asset, key, value)
                asset.metadata_json = json.dumps(metadata)
                asset.last_seen_at = utc_now()
                updated += 1
            else:
                asset = DataAsset(tenant_id=tenant_id, **record, metadata_json=json.dumps(metadata))
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
                        ClassificationReview.tenant_id == tenant_id,
                        ClassificationReview.asset_id == asset.id,
                        ClassificationReview.status == "pending",
                    )
                )
                if not pending:
                    db.add(
                        ClassificationReview(
                            tenant_id=tenant_id,
                            asset_id=asset.id,
                            original_sensitivity=result.sensitivity,
                            original_labels=", ".join(result.labels),
                            confidence=result.confidence,
                            reason=result.reason,
                        )
                    )
            _ensure_edge(db, tenant_id, "asset", str(asset.id), "owned_by", "identity", asset.owner)
            _ensure_edge(
                db,
                tenant_id,
                "asset",
                str(asset.id),
                "belongs_to",
                "business-domain",
                asset.business_domain,
            )
            _ensure_edge(
                db,
                tenant_id,
                connector.source,
                connector.account,
                "contains",
                "asset",
                str(asset.id),
            )
            indexed_assets.append(asset)
        run.status = "completed"
        run.imported = imported
        run.updated = updated
        run.next_cursor = batch.next_cursor
        run.finished_at = utc_now()
        db.commit()
        for asset in indexed_assets:
            index_asset(asset)
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
        safe_error = safe_connector_error(exc, _connector_secrets(connector))
        run_id = run.id
        db.rollback()
        failed_run = db.get(ConnectorRun, run_id)
        if failed_run:
            failed_run.status = "failed"
            failed_run.error = safe_error
            failed_run.finished_at = utc_now()
        db.commit()
        if isinstance(exc, ProviderRateLimitExceeded):
            raise
        raise RuntimeError(safe_error) from None


def safe_connector_error(
    error: Exception | str,
    sensitive_values: tuple[str, ...] = (),
) -> str:
    message = str(error).replace("\r", " ").replace("\n", " ")
    for value in sensitive_values:
        if len(value) >= 4:
            message = message.replace(value, "<redacted>")
    for pattern in REDACTED_ERROR_PATTERNS:
        message = pattern.sub(r"\1<redacted>", message)
    return message[:2000]


def _connector_secrets(connector: Connector) -> tuple[str, ...]:
    values = []
    token = getattr(connector, "token", None)
    if isinstance(token, str):
        values.append(token)
    credentials_info = getattr(connector, "credentials_info", None)
    if isinstance(credentials_info, dict):
        for key, value in credentials_info.items():
            if isinstance(value, str) and any(marker in key.lower() for marker in ("key", "secret", "token")):
                values.append(value)
    dsn = getattr(connector, "dsn", None)
    if isinstance(dsn, str):
        values.append(dsn)
    return tuple(values)


def _ensure_edge(
    db: Session,
    tenant_id: str,
    source_type: str,
    source_id: str,
    relationship: str,
    target_type: str,
    target_id: str,
) -> None:
    edge = db.scalar(
        select(GraphEdge).where(
            GraphEdge.tenant_id == tenant_id,
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
                tenant_id=tenant_id,
                source_type=source_type,
                source_id=source_id,
                relationship=relationship,
                target_type=target_type,
                target_id=target_id,
            )
        )
