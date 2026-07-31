import json
import re
import secrets
from uuid import uuid4

from fastapi import Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import settings
from app.models import SCIMResource, utc_now


SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"


def scim_principal(
    authorization: str | None = Header(default=None),
) -> Principal:
    try:
        configured_tokens = json.loads(settings.scim_tokens_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "ODG_SCIM_TOKENS_JSON is invalid") from exc
    if not isinstance(configured_tokens, dict) or any(
        not isinstance(entry, dict) for entry in configured_tokens.values()
    ):
        raise HTTPException(500, "ODG_SCIM_TOKENS_JSON must contain token objects")
    if settings.scim_bearer_token and not configured_tokens:
        configured_tokens = {
            settings.scim_bearer_token: {
                "tenant_id": settings.default_tenant,
                "subject": "scim-client",
            }
        }
    if not configured_tokens:
        raise HTTPException(503, "SCIM provisioning is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    entry = next(
        (
            value
            for configured_token, value in configured_tokens.items()
            if secrets.compare_digest(token, configured_token)
        ),
        None,
    )
    if scheme.lower() != "bearer" or not entry:
        raise HTTPException(401, "A valid SCIM bearer token is required")
    tenant_id = entry.get("tenant_id")
    if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", tenant_id):
        raise HTTPException(500, "SCIM token has an invalid tenant binding")
    subject = entry.get("subject", "scim-client")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 320:
        raise HTTPException(500, "SCIM token has an invalid subject")
    return Principal(subject=subject, role="administrator", tenant_id=tenant_id)


def create_resource(db: Session, tenant_id: str, resource_type: str, payload: dict) -> SCIMResource:
    _validate_payload(resource_type, payload)
    resource = SCIMResource(
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=str(uuid4()),
        external_id=_string(payload.get("externalId"), 320),
        user_name=_string(payload.get("userName"), 320),
        display_name=_display_name(resource_type, payload),
        active=bool(payload.get("active", True)),
        data_json=json.dumps(payload),
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def replace_resource(db: Session, resource: SCIMResource, payload: dict) -> SCIMResource:
    _validate_payload(resource.resource_type, payload)
    resource.external_id = _string(payload.get("externalId"), 320)
    resource.user_name = _string(payload.get("userName"), 320)
    resource.display_name = _display_name(resource.resource_type, payload)
    resource.active = bool(payload.get("active", True))
    resource.data_json = json.dumps(payload)
    resource.updated_at = utc_now()
    db.commit()
    db.refresh(resource)
    return resource


def patch_resource(db: Session, resource: SCIMResource, operations: list[dict]) -> SCIMResource:
    payload = json.loads(resource.data_json or "{}")
    for operation in operations:
        action = str(operation.get("op", "")).lower()
        path = operation.get("path")
        if action not in {"add", "replace", "remove"}:
            raise ValueError("SCIM patch op must be add, replace, or remove")
        if path and not isinstance(path, str):
            raise ValueError("SCIM patch path must be a string")
        if action == "remove":
            if path:
                payload.pop(path, None)
            continue
        value = operation.get("value")
        if path:
            payload[path] = value
        elif isinstance(value, dict):
            payload.update(value)
        else:
            raise ValueError("SCIM patch without a path requires an object value")
    return replace_resource(db, resource, payload)


def resource_response(resource: SCIMResource) -> dict:
    payload = json.loads(resource.data_json or "{}")
    payload["id"] = resource.resource_id
    payload["externalId"] = resource.external_id
    payload["displayName"] = resource.display_name
    payload["active"] = resource.active
    if resource.resource_type == "User":
        payload["userName"] = resource.user_name
        payload["schemas"] = [SCIM_USER_SCHEMA]
    else:
        payload["schemas"] = [SCIM_GROUP_SCHEMA]
    payload["meta"] = {
        "resourceType": resource.resource_type,
        "created": resource.created_at,
        "lastModified": resource.updated_at,
        "location": f"/scim/v2/{resource.resource_type}s/{resource.resource_id}",
    }
    return payload


def list_response(resources: list[SCIMResource], start_index: int, total_results: int) -> dict:
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": total_results,
        "startIndex": start_index,
        "itemsPerPage": len(resources),
        "Resources": [resource_response(resource) for resource in resources],
    }


def filter_resources(
    db: Session,
    tenant_id: str,
    resource_type: str,
    filter_expression: str | None,
    start_index: int,
    count: int,
) -> tuple[list[SCIMResource], int]:
    statement = select(SCIMResource).where(
        SCIMResource.tenant_id == tenant_id,
        SCIMResource.resource_type == resource_type,
    )
    if filter_expression:
        match = re.fullmatch(r'(userName|externalId|displayName)\s+eq\s+"([^"]+)"', filter_expression)
        if not match:
            raise ValueError("Supported SCIM filters use userName, externalId, or displayName eq")
        field, value = match.groups()
        column = {
            "userName": SCIMResource.user_name,
            "externalId": SCIMResource.external_id,
            "displayName": SCIMResource.display_name,
        }[field]
        statement = statement.where(column == value)
    total_results = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    resources = list(
        db.scalars(
            statement.order_by(SCIMResource.created_at).offset(max(0, start_index - 1)).limit(count)
        ).all()
    )
    return resources, total_results


def _validate_payload(resource_type: str, payload: dict) -> None:
    if resource_type not in {"User", "Group"}:
        raise ValueError("Unsupported SCIM resource type")
    if not isinstance(payload, dict):
        raise ValueError("SCIM payload must be an object")
    if len(json.dumps(payload).encode()) > 65_536:
        raise ValueError("SCIM payload exceeds 64 KiB")
    if "password" in payload:
        raise ValueError("SCIM passwords are not accepted")
    if resource_type == "User" and not _string(payload.get("userName"), 320):
        raise ValueError("SCIM userName is required")


def _display_name(resource_type: str, payload: dict) -> str:
    value = payload.get("displayName")
    if not value and resource_type == "User":
        name = payload.get("name")
        value = name.get("formatted") if isinstance(name, dict) else None
        value = value or payload.get("userName")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SCIM displayName is required")
    return value.strip()[:320]


def _string(value, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SCIM string attributes must be non-empty strings")
    return value.strip()[:max_length]
