import base64
import hashlib
import hmac
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AIAgent, AIResource, DataAsset, SCIMResource
from app.schemas import (
    AuthZENActionSearchRequest,
    AuthZENEvaluationRequest,
    AuthZENResourceSearchRequest,
    AuthZENSubjectSearchRequest,
)
from app.services.evidence_signing import canonical_json
from app.services.runtime_authorization import evaluate_policy_only


ACTION_CATALOG = (
    "fine-tune",
    "invoke",
    "list",
    "read",
    "retrieve",
    "send",
    "train",
)
MAX_SCAN_PER_PAGE = 5000


def search_subjects(
    db: Session,
    tenant_id: str,
    request: AuthZENSubjectSearchRequest,
) -> dict:
    offset, digest = _request_state("subject", tenant_id, request)
    candidates = _subject_candidates(
        db,
        tenant_id,
        request.subject.type,
        offset,
    )
    lookup_cache = {}

    def permitted(candidate: dict) -> bool:
        evaluation = AuthZENEvaluationRequest(
            subject=candidate,
            action=request.action,
            resource=request.resource,
            context=request.context,
        )
        return evaluate_policy_only(
            db,
            tenant_id,
            evaluation,
            lookup_cache,
        )["decision"] != "deny"

    return _page_results(
        "subject",
        tenant_id,
        digest,
        offset,
        request.page.limit,
        candidates,
        permitted,
    )


def search_resources(
    db: Session,
    tenant_id: str,
    request: AuthZENResourceSearchRequest,
) -> dict:
    offset, digest = _request_state("resource", tenant_id, request)
    candidates = _resource_candidates(
        db,
        tenant_id,
        request.resource.type,
        offset,
    )
    lookup_cache = {}

    def permitted(candidate: dict) -> bool:
        evaluation = AuthZENEvaluationRequest(
            subject=request.subject,
            action=request.action,
            resource=candidate,
            context=request.context,
        )
        return evaluate_policy_only(
            db,
            tenant_id,
            evaluation,
            lookup_cache,
        )["decision"] != "deny"

    return _page_results(
        "resource",
        tenant_id,
        digest,
        offset,
        request.page.limit,
        candidates,
        permitted,
    )


def search_actions(
    db: Session,
    tenant_id: str,
    request: AuthZENActionSearchRequest,
) -> dict:
    offset, digest = _request_state("action", tenant_id, request)
    candidates = [
        {"name": action}
        for action in ACTION_CATALOG[offset : offset + MAX_SCAN_PER_PAGE + 1]
    ]
    lookup_cache = {}

    def permitted(candidate: dict) -> bool:
        evaluation = AuthZENEvaluationRequest(
            subject=request.subject,
            action=candidate,
            resource=request.resource,
            context=request.context,
        )
        return evaluate_policy_only(
            db,
            tenant_id,
            evaluation,
            lookup_cache,
        )["decision"] != "deny"

    return _page_results(
        "action",
        tenant_id,
        digest,
        offset,
        request.page.limit,
        candidates,
        permitted,
    )


def _subject_candidates(
    db: Session,
    tenant_id: str,
    subject_type: str,
    offset: int,
) -> list[dict]:
    if subject_type in {"agent", "ai_agent"}:
        rows = db.scalars(
            select(AIAgent)
            .where(AIAgent.tenant_id == tenant_id)
            .order_by(AIAgent.id)
            .offset(offset)
            .limit(MAX_SCAN_PER_PAGE + 1)
        )
        return [{"type": subject_type, "id": row.key} for row in rows]
    if subject_type == "user":
        rows = db.scalars(
            select(SCIMResource)
            .where(
                SCIMResource.tenant_id == tenant_id,
                SCIMResource.resource_type == "User",
                SCIMResource.active.is_(True),
            )
            .order_by(SCIMResource.id)
            .offset(offset)
            .limit(MAX_SCAN_PER_PAGE + 1)
        )
        return [
            {
                "type": "user",
                "id": row.user_name or row.resource_id,
            }
            for row in rows
        ]
    return []


def _resource_candidates(
    db: Session,
    tenant_id: str,
    resource_type: str,
    offset: int,
) -> list[dict]:
    if resource_type in {"asset", "data_asset"}:
        rows = db.scalars(
            select(DataAsset)
            .where(DataAsset.tenant_id == tenant_id)
            .order_by(DataAsset.id)
            .offset(offset)
            .limit(MAX_SCAN_PER_PAGE + 1)
        )
        return [
            {"type": resource_type, "id": row.external_id or str(row.id)}
            for row in rows
        ]
    if resource_type in {
        "model",
        "prompt",
        "vector-index",
        "tool",
        "endpoint",
        "ai-system",
    }:
        rows = db.scalars(
            select(AIResource)
            .where(
                AIResource.tenant_id == tenant_id,
                AIResource.resource_type == resource_type,
            )
            .order_by(AIResource.id)
            .offset(offset)
            .limit(MAX_SCAN_PER_PAGE + 1)
        )
        return [
            {"type": resource_type, "id": row.resource_key}
            for row in rows
        ]
    return []


def _page_results(
    kind: str,
    tenant_id: str,
    digest: str,
    offset: int,
    requested_limit: int,
    candidates: list[dict],
    permitted,
) -> dict:
    limit = min(requested_limit, max(1, settings.authzen_search_max), 500)
    results = []
    consumed = 0
    scan_exhausted = len(candidates) <= MAX_SCAN_PER_PAGE
    for candidate in candidates[:MAX_SCAN_PER_PAGE]:
        consumed += 1
        if permitted(candidate):
            results.append(candidate)
            if len(results) >= limit:
                scan_exhausted = False
                break
    next_offset = offset + consumed
    next_token = "" if scan_exhausted else _token(
        kind,
        tenant_id,
        digest,
        next_offset,
    )
    return {
        "page": {
            "next_token": next_token,
            "count": len(results),
        },
        "results": results,
    }


def _request_state(kind: str, tenant_id: str, request) -> tuple[int, str]:
    data = request.model_dump(mode="json")
    token = data["page"].pop("token", None)
    data["page"]["limit"] = min(
        data["page"]["limit"],
        max(1, settings.authzen_search_max),
        500,
    )
    digest = hashlib.sha256(canonical_json(data)).hexdigest()
    if not token:
        return 0, digest
    payload = _decode_token(token)
    if (
        payload.get("kind") != kind
        or payload.get("tenant_id") != tenant_id
        or payload.get("request_sha256") != digest
        or not isinstance(payload.get("offset"), int)
        or payload["offset"] < 0
    ):
        raise ValueError("AuthZEN pagination token does not match the request")
    return payload["offset"], digest


def _token(kind: str, tenant_id: str, digest: str, offset: int) -> str:
    payload = canonical_json(
        {
            "kind": kind,
            "tenant_id": tenant_id,
            "request_sha256": digest,
            "offset": offset,
        }
    )
    signature = hmac.new(_pagination_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + signature).decode().rstrip("=")


def _decode_token(token: str) -> dict:
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(token + padding)
        payload, signature = decoded.rsplit(b".", 1)
        expected = hmac.new(_pagination_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        return json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("AuthZEN pagination token is invalid") from exc


def _pagination_secret() -> bytes:
    if settings.authzen_pagination_secret:
        return settings.authzen_pagination_secret.encode()
    if settings.auth_disabled:
        return b"opendatagraph-development-pagination-only"
    raise ValueError(
        "ODG_AUTHZEN_PAGINATION_SECRET is required when authentication is enabled"
    )
