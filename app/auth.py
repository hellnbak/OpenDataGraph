import json
import re
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from .config import settings


ROLES = ["read-only", "auditor", "analyst", "connector-operator", "data-owner", "administrator"]


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    tenant_id: str


def current_principal(x_api_key: str | None = Header(default=None)) -> Principal:
    if settings.auth_disabled:
        return Principal(subject="development", role="administrator", tenant_id=settings.default_tenant)
    try:
        keys = json.loads(settings.api_keys_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "ODG_API_KEYS_JSON is invalid") from exc
    if not isinstance(keys, dict):
        raise HTTPException(500, "ODG_API_KEYS_JSON must contain a JSON object")
    entry = keys.get(x_api_key or "")
    if not entry:
        raise HTTPException(401, "A valid API key is required")
    if not isinstance(entry, dict):
        raise HTTPException(500, "ODG_API_KEYS_JSON entries must contain JSON objects")
    role = entry.get("role", "read-only")
    if role not in ROLES:
        raise HTTPException(403, "API key has an unsupported role")
    tenant_id = entry.get("tenant_id") or entry.get("tenant") or settings.default_tenant
    if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", tenant_id):
        raise HTTPException(403, "API key has an invalid tenant")
    subject = entry.get("subject", "api-key")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 320:
        raise HTTPException(403, "API key has an invalid subject")
    return Principal(subject=subject, role=role, tenant_id=tenant_id)


def require_role(minimum_role: str):
    minimum = ROLES.index(minimum_role)

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if ROLES.index(principal.role) < minimum:
            raise HTTPException(403, f"{minimum_role} role required")
        return principal

    return dependency


def oidc_configuration() -> dict:
    return {
        "enabled": bool(settings.oidc_issuer and settings.oidc_audience),
        "issuer": settings.oidc_issuer or None,
        "audience": settings.oidc_audience or None,
        "validation": "integration-boundary",
    }
