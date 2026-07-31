import json
from dataclasses import dataclass, replace
from importlib.metadata import entry_points
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ConnectorCapabilityPolicy, utc_now
from app.secrets import resolve_secret
from app.services.schedules import provider_request_guard
from connectors.gdrive import GoogleDriveConnector
from connectors.github import GitHubConnector
from connectors.gitlab import GitLabConnector
from connectors.postgresql import PostgreSQLConnector
from connectors.s3 import S3Connector
from connectors.sdk import Connector, ConnectorCapabilities, ConnectorManifest
from connectors.security import validate_https_url
from connectors.sharepoint import SharePointConnector


ConnectorFactory = Callable[[dict, Session, str], Connector]
PayloadValidator = Callable[[dict], None]


@dataclass(frozen=True)
class ConnectorRegistration:
    manifest: ConnectorManifest
    factory: ConnectorFactory
    validate_payload: PayloadValidator | None = None


_REGISTRY: dict[str, ConnectorRegistration] = {}
_PLUGINS_LOADED = False


def register_connector(registration: ConnectorRegistration) -> None:
    manifest = registration.manifest
    connector_type = manifest.connector_type
    if (
        not connector_type
        or len(connector_type) > 80
        or not connector_type.replace("-", "").isalnum()
    ):
        raise ValueError("Connector manifest type is invalid")
    if not manifest.version or len(manifest.version) > 40:
        raise ValueError("Connector manifest version is invalid")
    if manifest.capabilities.content_access not in {
        "metadata-only",
        "optional-sampled-content",
        "content-required",
    }:
        raise ValueError("Connector manifest content access is invalid")
    if connector_type in _REGISTRY:
        raise ValueError(f"Connector type is already registered: {connector_type}")
    _REGISTRY[connector_type] = registration


def connector_registration(connector_type: str) -> ConnectorRegistration:
    _load_plugins()
    registration = _REGISTRY.get(connector_type)
    if not registration:
        raise ValueError(f"Unsupported connector type: {connector_type}")
    return registration


def connector_manifests() -> list[ConnectorManifest]:
    _load_plugins()
    return [registration.manifest for _, registration in sorted(_REGISTRY.items())]


def build_connector(
    payload: dict,
    db: Session,
    tenant_id: str,
) -> tuple[Connector, ConnectorManifest, dict]:
    registration = connector_registration(payload["connector_type"])
    if registration.validate_payload:
        registration.validate_payload(payload)
    decision = enforce_connector_policy(db, tenant_id, registration.manifest)
    connector = registration.factory(payload, db, tenant_id)
    setattr(connector, "manifest", registration.manifest)
    setattr(connector, "capability_policy_version", decision["policy_version"])
    return connector, registration.manifest, decision


def govern_connector(
    connector: Connector,
    connector_type: str,
    db: Session,
    tenant_id: str,
) -> tuple[Connector, dict]:
    registration = connector_registration(connector_type)
    decision = enforce_connector_policy(db, tenant_id, registration.manifest)
    setattr(connector, "manifest", registration.manifest)
    setattr(connector, "capability_policy_version", decision["policy_version"])
    return connector, decision


def connector_policy(
    db: Session | None,
    tenant_id: str | None,
) -> tuple[dict, int | None]:
    configured = _policy_object(settings.connector_capability_policy_json)
    version = None
    if db is not None and tenant_id:
        stored = db.scalar(
            select(ConnectorCapabilityPolicy).where(
                ConnectorCapabilityPolicy.tenant_id == tenant_id
            )
        )
        if stored:
            configured = _merge_policy(configured, _policy_object(stored.policy_json))
            version = stored.version
    return _normalized_policy(configured), version


def set_connector_policy(
    db: Session,
    tenant_id: str,
    policy: dict,
    updated_by: str,
) -> ConnectorCapabilityPolicy:
    normalized = _normalized_policy(policy)
    record = db.scalar(
        select(ConnectorCapabilityPolicy).where(
            ConnectorCapabilityPolicy.tenant_id == tenant_id
        )
    )
    if record:
        record.version += 1
        record.policy_json = json.dumps(normalized, sort_keys=True)
        record.updated_by = updated_by
        record.updated_at = utc_now()
    else:
        record = ConnectorCapabilityPolicy(
            tenant_id=tenant_id,
            version=1,
            policy_json=json.dumps(normalized, sort_keys=True),
            updated_by=updated_by,
        )
        db.add(record)
    db.commit()
    db.refresh(record)
    return record


def evaluate_connector_policy(manifest: ConnectorManifest, policy: dict) -> dict:
    reasons = []
    allowed = policy["allowed_connectors"]
    denied = policy["denied_connectors"]
    if allowed and manifest.connector_type not in allowed:
        reasons.append("connector-not-allowlisted")
    if manifest.connector_type in denied:
        reasons.append("connector-denied")
    if manifest.capabilities.content_access not in policy["allowed_content_access"]:
        reasons.append("content-access-not-allowed")
    if policy["deny_destructive_actions"] and manifest.capabilities.destructive_actions:
        reasons.append("destructive-actions-not-allowed")
    if policy["require_incremental_cursor"] and not manifest.capabilities.incremental_cursor:
        reasons.append("incremental-cursor-required")
    if policy["require_opaque_cursor"] and not manifest.capabilities.opaque_cursor:
        reasons.append("opaque-cursor-required")
    if len(manifest.permissions) > policy["max_declared_permissions"]:
        reasons.append("permission-declaration-limit-exceeded")
    allowed_hosts = set(policy["allowed_egress_hosts"])
    if allowed_hosts and set(manifest.egress_hosts) - allowed_hosts:
        reasons.append("egress-host-not-allowed")
    if manifest.plugin and manifest.connector_type not in settings.connector_plugin_allowlist:
        reasons.append("plugin-not-allowlisted")
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "connector_type": manifest.connector_type,
        "connector_version": manifest.version,
        "capability_digest": manifest.digest(),
    }


def enforce_connector_policy(
    db: Session | None,
    tenant_id: str | None,
    manifest: ConnectorManifest,
) -> dict:
    policy, version = connector_policy(db, tenant_id)
    decision = evaluate_connector_policy(manifest, policy)
    decision["policy_version"] = version
    if not decision["allowed"]:
        raise ValueError(
            "Connector capability policy denied execution: "
            + ", ".join(decision["reasons"])
        )
    return decision


def connector_policy_response(record: ConnectorCapabilityPolicy | None, policy: dict) -> dict:
    return {
        "version": record.version if record else None,
        "policy": policy,
        "updated_by": record.updated_by if record else None,
        "updated_at": record.updated_at if record else None,
    }


def _load_plugins() -> None:
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    _PLUGINS_LOADED = True
    allowed = set(settings.connector_plugin_allowlist)
    if not allowed:
        return
    discovered = entry_points().select(group="opendatagraph.connectors")
    for entry_point in discovered:
        if entry_point.name not in allowed:
            continue
        loaded = entry_point.load()
        registration = loaded() if callable(loaded) and not isinstance(loaded, ConnectorRegistration) else loaded
        if not isinstance(registration, ConnectorRegistration):
            raise ValueError(f"Connector plugin registration is invalid: {entry_point.name}")
        manifest = replace(registration.manifest, plugin=True)
        register_connector(replace(registration, manifest=manifest))


def _policy_object(value: str | dict) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Connector capability policy must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Connector capability policy must be an object")
    return parsed


def _normalized_policy(policy: dict) -> dict:
    allowed_content = policy.get("allowed_content_access", ["metadata-only"])
    valid_content = {
        "metadata-only",
        "optional-sampled-content",
        "content-required",
    }
    if not isinstance(allowed_content, list) or not set(allowed_content) <= valid_content:
        raise ValueError("Connector capability policy content access is invalid")
    normalized = {
        "allowed_connectors": _string_list(policy.get("allowed_connectors", []), 200),
        "denied_connectors": _string_list(policy.get("denied_connectors", []), 200),
        "allowed_content_access": sorted(set(allowed_content)),
        "allowed_egress_hosts": _string_list(policy.get("allowed_egress_hosts", []), 500),
        "deny_destructive_actions": bool(policy.get("deny_destructive_actions", True)),
        "require_incremental_cursor": bool(policy.get("require_incremental_cursor", False)),
        "require_opaque_cursor": bool(policy.get("require_opaque_cursor", True)),
        "max_declared_permissions": policy.get("max_declared_permissions", 100),
    }
    if not isinstance(normalized["max_declared_permissions"], int) or not 1 <= normalized[
        "max_declared_permissions"
    ] <= 1000:
        raise ValueError("Connector capability policy permission limit is invalid")
    if set(normalized["allowed_connectors"]) & set(normalized["denied_connectors"]):
        raise ValueError("Connector capability policy cannot allow and deny the same connector")
    return normalized


def _merge_policy(base: dict, override: dict) -> dict:
    return {**base, **override}


def _string_list(value: object, maximum: int) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or any(not isinstance(item, str) or not item.strip() or len(item) > 255 for item in value)
    ):
        raise ValueError("Connector capability policy contains an invalid list")
    return sorted(set(item.strip().lower() for item in value))


def _guard(db: Session, tenant_id: str, connector_type: str):
    return provider_request_guard(db, tenant_id, connector_type)


def _s3_factory(payload: dict, db: Session, tenant_id: str) -> Connector:
    return S3Connector(
        payload["account"],
        prefix=payload.get("prefix", ""),
        region=payload.get("region"),
        before_request=_guard(db, tenant_id, "aws-s3"),
    )


def _gdrive_factory(payload: dict, db: Session, tenant_id: str) -> Connector:
    try:
        credentials_info = json.loads(resolve_secret(payload["secret_ref"]))
    except json.JSONDecodeError as exc:
        raise ValueError("Google Drive secret_ref must contain service-account JSON") from exc
    return GoogleDriveConnector(
        account=payload["account"],
        credentials_info=credentials_info,
        impersonate_user=payload.get("impersonate_user"),
        drive_id=payload.get("drive_id"),
        before_request=_guard(db, tenant_id, "google-drive"),
    )


def _github_factory(payload: dict, db: Session, tenant_id: str) -> Connector:
    return GitHubConnector(
        payload["account"],
        resolve_secret(payload["secret_ref"]),
        payload.get("api_url") or "https://api.github.com",
        allowed_hosts=settings.github_allowed_hosts,
        before_request=_guard(db, tenant_id, "github"),
    )


def _gitlab_factory(payload: dict, db: Session, tenant_id: str) -> Connector:
    return GitLabConnector(
        payload["account"],
        resolve_secret(payload["secret_ref"]),
        payload.get("api_url") or "https://gitlab.com/api/v4",
        allowed_hosts=settings.gitlab_allowed_hosts,
        before_request=_guard(db, tenant_id, "gitlab"),
    )


def _sharepoint_factory(payload: dict, db: Session, tenant_id: str) -> Connector:
    drive_id = payload.get("drive_id")
    if not drive_id:
        raise ValueError("drive_id is required for SharePoint")
    return SharePointConnector(
        payload.get("site_id") or payload["account"],
        drive_id,
        resolve_secret(payload["secret_ref"]),
        allowed_hosts=settings.sharepoint_allowed_hosts,
        before_request=_guard(db, tenant_id, "sharepoint"),
    )


def _postgresql_factory(payload: dict, db: Session, tenant_id: str) -> Connector:
    return PostgreSQLConnector(
        payload["account"],
        resolve_secret(payload["secret_ref"]),
        schemas=payload.get("schemas", []),
        before_request=_guard(db, tenant_id, "postgresql"),
    )


def _validate_github(payload: dict) -> None:
    validate_https_url(
        payload.get("api_url") or "https://api.github.com",
        settings.github_allowed_hosts,
    )


def _validate_gitlab(payload: dict) -> None:
    validate_https_url(
        payload.get("api_url") or "https://gitlab.com/api/v4",
        settings.gitlab_allowed_hosts,
    )


def _validate_sharepoint(payload: dict) -> None:
    if payload.get("cursor"):
        validate_https_url(payload["cursor"], settings.sharepoint_allowed_hosts)


def _validate_postgresql(payload: dict) -> None:
    schemas = payload.get("schemas", [])
    if (
        not isinstance(schemas, list)
        or len(schemas) > 100
        or any(
            not isinstance(schema, str) or not schema.strip() or len(schema) > 63
            for schema in schemas
        )
    ):
        raise ValueError("PostgreSQL connector schemas are invalid")


def _manifest(
    connector_type: str,
    display_name: str,
    permissions: tuple[str, ...],
    egress_hosts: tuple[str, ...],
    timestamp_provenance: tuple[str, ...],
    public_access: str,
    description: str,
) -> ConnectorManifest:
    return ConnectorManifest(
        connector_type=connector_type,
        display_name=display_name,
        version="1.8.0",
        permissions=permissions,
        egress_hosts=egress_hosts,
        capabilities=ConnectorCapabilities(
            timestamp_provenance=timestamp_provenance,
            public_access_interpretation=public_access,
        ),
        description=description,
    )


register_connector(
    ConnectorRegistration(
        _manifest(
            "aws-s3",
            "AWS S3",
            ("s3:ListBucket", "s3:GetObject", "s3:GetBucketPolicyStatus"),
            ("s3.amazonaws.com",),
            ("provider-object-last-modified",),
            "bucket-policy-status-or-unknown",
            "Metadata-only S3 object inventory",
        ),
        _s3_factory,
    )
)
register_connector(
    ConnectorRegistration(
        _manifest(
            "google-drive",
            "Google Drive",
            ("drive.metadata.readonly",),
            ("www.googleapis.com", "oauth2.googleapis.com"),
            ("provider-created-time", "provider-modified-time"),
            "anyone-permission",
            "Metadata-only Google Drive and shared-drive inventory",
        ),
        _gdrive_factory,
    )
)
register_connector(
    ConnectorRegistration(
        _manifest(
            "github",
            "GitHub",
            ("organization-repositories:read",),
            ("api.github.com",),
            ("provider-created-at", "provider-updated-at"),
            "repository-visibility",
            "Metadata-only GitHub repository inventory",
        ),
        _github_factory,
        _validate_github,
    )
)
register_connector(
    ConnectorRegistration(
        _manifest(
            "gitlab",
            "GitLab",
            ("read_api",),
            ("gitlab.com",),
            ("provider-created-at", "provider-last-activity-at"),
            "project-visibility",
            "Metadata-only GitLab project inventory",
        ),
        _gitlab_factory,
        _validate_gitlab,
    )
)
register_connector(
    ConnectorRegistration(
        _manifest(
            "sharepoint",
            "SharePoint / OneDrive",
            ("Files.Read.All", "Sites.Read.All"),
            ("graph.microsoft.com",),
            ("provider-created-date-time", "provider-last-modified-date-time"),
            "not-evaluated",
            "Metadata-only SharePoint and OneDrive delta inventory",
        ),
        _sharepoint_factory,
        _validate_sharepoint,
    )
)
register_connector(
    ConnectorRegistration(
        _manifest(
            "postgresql",
            "PostgreSQL",
            ("CONNECT", "schema:USAGE", "catalog-metadata-visibility"),
            (),
            ("catalog-scan-time",),
            "not-evaluated",
            "Metadata-only PostgreSQL table and view inventory",
        ),
        _postgresql_factory,
        _validate_postgresql,
    )
)
