import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DataAsset


logger = logging.getLogger(__name__)


def asset_document(asset: DataAsset) -> dict:
    return {
        "asset_id": asset.id,
        "tenant_id": asset.tenant_id,
        "source": asset.source,
        "source_account": asset.source_account,
        "external_id": asset.external_id,
        "name": asset.name,
        "path": asset.path,
        "mime_type": asset.mime_type,
        "owner": asset.owner,
        "business_domain": asset.business_domain,
        "sensitivity": asset.sensitivity,
        "classification_labels": asset.classification_labels,
        "classification_reason": asset.classification_reason,
        "lifecycle_state": asset.lifecycle_state,
        "retention_action": asset.retention_action,
        "public_access": asset.public_access,
        "encryption": asset.encryption,
        "ai_access": asset.ai_access,
        "last_seen_at": asset.last_seen_at.isoformat() if asset.last_seen_at else None,
    }


def index_asset(asset: DataAsset) -> bool:
    if settings.search_backend != "opensearch":
        return False
    try:
        client = _client()
        _ensure_index(client)
        client.index(index=_index_name(), id=f"{asset.tenant_id}:{asset.id}", body=asset_document(asset), refresh=False)
        return True
    except Exception:
        if settings.opensearch_required:
            raise
        logger.exception("OpenSearch asset indexing failed")
        return False


def search_asset_ids(query: str, tenant_id: str, limit: int = 500) -> list[int] | None:
    if settings.search_backend != "opensearch":
        return None
    try:
        client = _client()
        _ensure_index(client)
        response = client.search(
            index=_index_name(),
            body={
                "size": limit,
                "query": {
                    "bool": {
                        "filter": [{"term": {"tenant_id": tenant_id}}],
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "name^4",
                                        "path^2",
                                        "owner",
                                        "business_domain",
                                        "classification_labels",
                                        "classification_reason",
                                    ],
                                }
                            }
                        ],
                    }
                },
            },
        )
        return [int(hit["_source"]["asset_id"]) for hit in response["hits"]["hits"]]
    except Exception:
        if settings.opensearch_required:
            raise
        logger.exception("OpenSearch query failed; using database fallback")
        return None


def reindex_tenant(db: Session, tenant_id: str) -> dict:
    if settings.search_backend != "opensearch":
        return {"indexed": 0, "backend": "database", "skipped": True}
    client = _client()
    _ensure_index(client)
    client.delete_by_query(
        index=_index_name(),
        body={"query": {"term": {"tenant_id": tenant_id}}},
        conflicts="proceed",
        refresh=True,
    )
    assets = list(db.scalars(select(DataAsset).where(DataAsset.tenant_id == tenant_id)).all())
    if assets:
        from opensearchpy.helpers import bulk

        bulk(
            client,
            [
                {
                    "_index": _index_name(),
                    "_id": f"{asset.tenant_id}:{asset.id}",
                    "_source": asset_document(asset),
                }
                for asset in assets
            ],
            refresh=True,
        )
    return {"indexed": len(assets), "backend": "opensearch", "skipped": False}


def search_health() -> dict:
    if settings.search_backend != "opensearch":
        return {"backend": "database", "ok": True}
    try:
        response = _client().cluster.health()
        return {"backend": "opensearch", "ok": True, "status": response.get("status")}
    except Exception as exc:
        return {"backend": "opensearch", "ok": False, "error": type(exc).__name__}


def _client():
    if not settings.opensearch_url:
        raise RuntimeError("ODG_OPENSEARCH_URL is required when OpenSearch is enabled")
    from opensearchpy import OpenSearch

    return OpenSearch(hosts=[settings.opensearch_url], timeout=10, max_retries=2, retry_on_timeout=True)


def _index_name() -> str:
    return f"{settings.opensearch_index_prefix}-assets-v1"


def _ensure_index(client) -> None:
    index_name = _index_name()
    if client.indices.exists(index=index_name):
        return
    client.indices.create(
        index=index_name,
        body={
            "mappings": {
                "properties": {
                    "asset_id": {"type": "long"},
                    "tenant_id": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "source_account": {"type": "keyword"},
                    "external_id": {"type": "keyword"},
                    "name": {"type": "text"},
                    "path": {"type": "text"},
                    "mime_type": {"type": "keyword"},
                    "owner": {"type": "text"},
                    "business_domain": {"type": "keyword"},
                    "sensitivity": {"type": "keyword"},
                    "classification_labels": {"type": "text"},
                    "classification_reason": {"type": "text"},
                    "lifecycle_state": {"type": "keyword"},
                    "retention_action": {"type": "keyword"},
                    "public_access": {"type": "boolean"},
                    "encryption": {"type": "keyword"},
                    "ai_access": {"type": "keyword"},
                    "last_seen_at": {"type": "date"},
                }
            }
        },
    )
