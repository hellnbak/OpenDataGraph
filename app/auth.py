import json
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from .config import settings


ROLES = ["read-only", "auditor", "analyst", "connector-operator", "data-owner", "administrator"]


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


def current_principal(x_api_key: str | None = Header(default=None)) -> Principal:
    if settings.auth_disabled:
        return Principal(subject="development", role="administrator")
    try:
        keys = json.loads(settings.api_keys_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "ODG_API_KEYS_JSON is invalid") from exc
    entry = keys.get(x_api_key or "")
    if not entry:
        raise HTTPException(401, "A valid API key is required")
    role = entry.get("role", "read-only")
    if role not in ROLES:
        raise HTTPException(403, "API key has an unsupported role")
    return Principal(subject=entry.get("subject", "api-key"), role=role)


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
