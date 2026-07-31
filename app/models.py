from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TenantMixin:
    tenant_id: Mapped[str] = mapped_column(String(120), default="default", index=True)


class DataAsset(TenantMixin, Base):
    __tablename__ = "data_assets"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_asset_tenant_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_account: Mapped[str] = mapped_column(String(160), default="demo")
    external_id: Mapped[str] = mapped_column(String(1024), index=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    path: Mapped[str] = mapped_column(String(2048))
    mime_type: Mapped[str] = mapped_column(String(160), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    owner: Mapped[str] = mapped_column(String(256), default="unknown")
    business_domain: Mapped[str] = mapped_column(String(80), default="Unknown")
    sensitivity: Mapped[str] = mapped_column(String(40), default="Unclassified", index=True)
    classification_labels: Mapped[str] = mapped_column(Text, default="")
    classification_reason: Mapped[str] = mapped_column(Text, default="Not yet classified")
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    age_days: Mapped[int] = mapped_column(Integer, default=0)
    stale_score: Mapped[int] = mapped_column(Integer, default=0)
    lifecycle_state: Mapped[str] = mapped_column(String(40), default="Active", index=True)
    retention_action: Mapped[str] = mapped_column(String(80), default="Retain")
    retention_reason: Mapped[str] = mapped_column(Text, default="Within lifecycle policy")
    public_access: Mapped[bool] = mapped_column(Boolean, default=False)
    encryption: Mapped[str] = mapped_column(String(80), default="Unknown")
    ai_access: Mapped[str] = mapped_column(String(40), default="Review", index=True)
    ai_access_reason: Mapped[str] = mapped_column(Text, default="Classification pending")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class AIAgent(TenantMixin, Base):
    __tablename__ = "ai_agents"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_agent_tenant_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(240))
    owner: Mapped[str] = mapped_column(String(240))
    business_purpose: Mapped[str] = mapped_column(Text)
    framework: Mapped[str] = mapped_column(String(120), default="custom")
    models: Mapped[str] = mapped_column(Text, default="")
    allowed_domains: Mapped[str] = mapped_column(Text, default="")
    max_sensitivity: Mapped[str] = mapped_column(String(40), default="Internal")
    allowed_destinations: Mapped[str] = mapped_column(Text, default="internal-rag,private-model")
    approval_status: Mapped[str] = mapped_column(String(40), default="Approved")
    risk_level: Mapped[str] = mapped_column(String(40), default="Medium")
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DecisionAudit(TenantMixin, Base):
    __tablename__ = "decision_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    agent_key: Mapped[str] = mapped_column(String(120), index=True)
    asset_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(160))
    purpose: Mapped[str] = mapped_column(String(240))
    decision: Mapped[str] = mapped_column(String(40), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    policy_version: Mapped[str] = mapped_column(String(40))
    reasons_json: Mapped[str] = mapped_column(Text)
    controls_json: Mapped[str] = mapped_column(Text)


class ConnectorRun(TenantMixin, Base):
    __tablename__ = "connector_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    source_account: Mapped[str] = mapped_column(String(240), default="default")
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ClassificationReview(TenantMixin, Base):
    __tablename__ = "classification_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    original_sensitivity: Mapped[str] = mapped_column(String(40))
    original_labels: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text)
    corrected_sensitivity: Mapped[str | None] = mapped_column(String(40), nullable=True)
    corrected_labels: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AIUsageEvent(TenantMixin, Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_id", name="uq_usage_event_tenant_event_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(240), index=True)
    agent_key: Mapped[str] = mapped_column(String(120), index=True)
    user_identity: Mapped[str] = mapped_column(String(320), index=True)
    asset_id: Mapped[int] = mapped_column(Integer, index=True)
    model: Mapped[str] = mapped_column(String(240))
    destination: Mapped[str] = mapped_column(String(240))
    purpose: Mapped[str] = mapped_column(String(240))
    action: Mapped[str] = mapped_column(String(80))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    decision: Mapped[str] = mapped_column(String(40), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class GraphEdge(TenantMixin, Base):
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    source_id: Mapped[str] = mapped_column(String(320), index=True)
    relationship: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str] = mapped_column(String(320), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BackgroundJob(TenantMixin, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "job_id", name="uq_job_tenant_job_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), index=True)
    job_type: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class EvidenceRecord(TenantMixin, Base):
    __tablename__ = "evidence_records"
    __table_args__ = (UniqueConstraint("tenant_id", "evidence_id", name="uq_evidence_tenant_evidence_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(36), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    subject_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_id: Mapped[str] = mapped_column(String(320), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(240))
    storage_uri: Mapped[str] = mapped_column(String(2048))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    deleted_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ConnectorSchedule(TenantMixin, Base):
    __tablename__ = "connector_schedules"
    __table_args__ = (UniqueConstraint("tenant_id", "schedule_id", name="uq_schedule_tenant_schedule_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[str] = mapped_column(String(36), index=True)
    connector_type: Mapped[str] = mapped_column(String(80), index=True)
    account: Mapped[str] = mapped_column(String(240))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ProviderRateLimit(TenantMixin, Base):
    __tablename__ = "provider_rate_limits"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uq_rate_limit_tenant_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    max_requests: Mapped[int] = mapped_column(Integer)
    window_seconds: Mapped[int] = mapped_column(Integer)
    used_requests: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SCIMResource(TenantMixin, Base):
    __tablename__ = "scim_resources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "resource_id", name="uq_scim_tenant_type_resource"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    external_id: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    user_name: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(320))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PolicyBundle(TenantMixin, Base):
    __tablename__ = "policy_bundles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bundle_id", name="uq_policy_bundle_tenant_id"),
        UniqueConstraint("tenant_id", "name", "version", name="uq_policy_bundle_tenant_name_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bundle_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    definition_json: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(320))
    approved_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PolicyException(TenantMixin, Base):
    __tablename__ = "policy_exceptions"
    __table_args__ = (UniqueConstraint("tenant_id", "exception_id", name="uq_policy_exception_tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exception_id: Mapped[str] = mapped_column(String(36), index=True)
    policy_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    agent_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    destination: Mapped[str | None] = mapped_column(String(240), nullable=True)
    action: Mapped[str | None] = mapped_column(String(80), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(240), nullable=True)
    override_decision: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    controls_json: Mapped[str] = mapped_column(Text, default="[]")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(320))
    approved_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class IntegrationEndpoint(TenantMixin, Base):
    __tablename__ = "integration_endpoints"
    __table_args__ = (
        UniqueConstraint("tenant_id", "endpoint_id", name="uq_integration_endpoint_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_integration_endpoint_tenant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    endpoint_type: Mapped[str] = mapped_column(String(40), default="webhook")
    mode: Mapped[str] = mapped_column(String(40), default="observe")
    url: Mapped[str] = mapped_column(String(2048))
    secret_ref: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    events_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class IntegrationDelivery(TenantMixin, Base):
    __tablename__ = "integration_deliveries"
    __table_args__ = (UniqueConstraint("tenant_id", "delivery_id", name="uq_integration_delivery_tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(36), index=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LineageEvent(TenantMixin, Base):
    __tablename__ = "lineage_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_id", name="uq_lineage_event_tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    run_id: Mapped[str] = mapped_column(String(320), index=True)
    job_namespace: Mapped[str] = mapped_column(String(320), index=True)
    job_name: Mapped[str] = mapped_column(String(320), index=True)
    producer: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
