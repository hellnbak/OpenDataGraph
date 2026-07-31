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


def current_principal(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    if settings.auth_disabled:
        return Principal(subject="development", role="administrator", tenant_id=settings.default_tenant)
    x_api_key = x_api_key if isinstance(x_api_key, str) else None
    authorization = authorization if isinstance(authorization, str) else None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Authorization must use a Bearer token")
        return _oidc_principal(token)
    return _api_key_principal(x_api_key)


def _api_key_principal(x_api_key: str | None) -> Principal:
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


def _oidc_principal(token: str) -> Principal:
    try:
        import jwt

        unverified = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_iss": False,
                "verify_exp": False,
            },
        )
        providers = _oidc_providers()
        issuer = unverified.get("iss")
        provider = next((item for item in providers.values() if item.get("issuer") == issuer), None)
        if not provider:
            raise HTTPException(401, "OIDC issuer is not configured")
        algorithms = provider.get("algorithms", ["RS256"])
        if not isinstance(algorithms, list) or not algorithms or any(
            algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
            for algorithm in algorithms
        ):
            raise HTTPException(500, "OIDC provider algorithms are invalid")
        jwks_url = provider.get("jwks_url")
        audience = provider.get("audience")
        if not isinstance(jwks_url, str) or not jwks_url.startswith("https://"):
            raise HTTPException(500, "OIDC provider jwks_url must use HTTPS")
        if not isinstance(audience, str) or not audience:
            raise HTTPException(500, "OIDC provider audience is required")
        signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=algorithms,
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, "OIDC token validation failed") from exc
    role = _claim_value(claims, provider.get("role_claim", "role"))
    role_mapping = provider.get("role_mapping", {})
    if isinstance(role, str) and isinstance(role_mapping, dict):
        role = role_mapping.get(role, role)
    if isinstance(role, list):
        mapped = [role_mapping.get(item, item) for item in role] if isinstance(role_mapping, dict) else role
        supported = [item for item in mapped if item in ROLES]
        role = max(supported, key=ROLES.index) if supported else None
    if role not in ROLES:
        raise HTTPException(403, "OIDC token has an unsupported role")
    tenant_id = _claim_value(claims, provider.get("tenant_claim", "tenant_id"))
    if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", tenant_id):
        raise HTTPException(403, "OIDC token has an invalid tenant")
    subject = _claim_value(claims, provider.get("subject_claim", "sub"))
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 320:
        raise HTTPException(403, "OIDC token has an invalid subject")
    return Principal(subject=subject, role=role, tenant_id=tenant_id)


def _claim_value(claims: dict, claim_name: object):
    if not isinstance(claim_name, str) or not claim_name:
        return None
    value = claims
    for segment in claim_name.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def _oidc_providers() -> dict[str, dict]:
    try:
        providers = json.loads(settings.oidc_providers_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(500, "ODG_OIDC_PROVIDERS_JSON is invalid") from exc
    if not isinstance(providers, dict) or any(not isinstance(value, dict) for value in providers.values()):
        raise HTTPException(500, "ODG_OIDC_PROVIDERS_JSON must contain provider objects")
    if (
        not providers
        and settings.oidc_issuer
        and settings.oidc_audience
        and settings.oidc_jwks_url
    ):
        providers = {
            "legacy": {
                "issuer": settings.oidc_issuer,
                "audience": settings.oidc_audience,
                "jwks_url": settings.oidc_jwks_url,
            }
        }
    return providers


def require_role(minimum_role: str):
    minimum = ROLES.index(minimum_role)

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if ROLES.index(principal.role) < minimum:
            raise HTTPException(403, f"{minimum_role} role required")
        return principal

    return dependency


def oidc_configuration() -> dict:
    providers = _oidc_providers()
    return {
        "enabled": bool(providers),
        "providers": [
            {
                "name": name,
                "issuer": provider.get("issuer"),
                "audience": provider.get("audience"),
            }
            for name, provider in providers.items()
        ],
        "validation": "signature-issuer-audience-expiry",
    }
