from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    source: str
    source_account: str
    external_id: str
    name: str
    path: str
    mime_type: str
    size_bytes: int
    owner: str
    business_domain: str
    sensitivity: str
    classification_labels: str
    classification_reason: str
    classification_confidence: float
    created_at: datetime | None
    modified_at: datetime | None
    last_accessed_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    age_days: int
    stale_score: int
    lifecycle_state: str
    retention_action: str
    retention_reason: str
    public_access: bool
    encryption: str
    ai_access: str
    ai_access_reason: str


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    key: str
    name: str
    owner: str
    business_purpose: str
    framework: str
    models: str
    allowed_domains: str
    max_sensitivity: str
    allowed_destinations: str
    approval_status: str
    risk_level: str
    last_activity_at: datetime | None


class AgentCreate(BaseModel):
    key: str
    name: str
    owner: str
    business_purpose: str
    framework: str = "custom"
    models: str = ""
    allowed_domains: str = ""
    max_sensitivity: str = "Internal"
    allowed_destinations: str = "internal-rag,private-model"
    approval_status: str = "Approved"
    risk_level: str = "Medium"


class PolicyRequest(BaseModel):
    asset_id: int
    destination: str = Field(default="external-ai")
    action: str = Field(default="send")
    agent_key: str = "customer-support-copilot"
    purpose: str = "summarization"
    destination_region: str = "us"


class PolicyDecision(BaseModel):
    decision: str
    asset_id: int
    agent_key: str
    destination: str
    action: str
    purpose: str
    risk_score: int
    reasons: list[str]
    controls: list[str]
    confidence: float
    policy_version: str
    expires_in_seconds: int
    matched_policies: list[str] = Field(default_factory=list)


class S3ScanRequest(BaseModel):
    bucket: str
    prefix: str = ""
    region: str | None = None
    max_objects: int = Field(default=500, ge=1, le=5000)


class GDriveScanRequest(BaseModel):
    credentials_file: str = "secrets/google-drive-service-account.json"
    impersonate_user: str | None = None
    drive_id: str | None = None
    max_files: int = Field(default=500, ge=1, le=5000)


class DemoGenerateRequest(BaseModel):
    profile: str = "financial-services"
    samples: int = Field(default=240, ge=80, le=600)
    seed: int = Field(default=41, ge=0, le=999999)


class ConnectorScanRequest(BaseModel):
    account: str
    cursor: str | None = None
    max_items: int = Field(default=500, ge=1, le=5000)
    token: str | None = Field(default=None, repr=False)
    api_url: str | None = None
    project: str | None = None
    site_id: str | None = None
    drive_id: str | None = None


class ConnectorJobRequest(BaseModel):
    account: str
    secret_ref: str | None = Field(default=None, pattern=r"^(env|file):.+$")
    cursor: str | None = None
    max_items: int = Field(default=500, ge=1, le=5000)
    max_attempts: int = Field(default=3, ge=1, le=10)
    api_url: str | None = None
    site_id: str | None = None
    drive_id: str | None = None
    region: str | None = None
    prefix: str = ""
    impersonate_user: str | None = None


class ClassificationReviewResolution(BaseModel):
    status: str = Field(pattern="^(approved|rejected|corrected)$")
    sensitivity: str | None = None
    labels: list[str] = Field(default_factory=list)
    reviewer: str = "analyst"


class PolicySimulationRequest(BaseModel):
    asset_id: int
    agent_key: str
    destination: str
    purpose: str
    action: str = "send"


class AIUsageEventCreate(BaseModel):
    event_id: str = Field(min_length=3, max_length=240)
    agent_key: str
    user_identity: str
    asset_id: int
    model: str
    destination: str
    purpose: str
    action: str = "read"
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)


class BackgroundJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    tenant_id: str
    job_type: str
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    claimed_at: datetime | None
    finished_at: datetime | None
    cancel_requested: bool
    error: str | None
    created_by: str
    created_at: datetime


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    tenant_id: str
    category: str
    subject_type: str
    subject_id: str
    filename: str
    content_type: str
    sha256: str
    size_bytes: int
    metadata: dict = Field(default_factory=dict)
    retention_until: datetime | None
    legal_hold: bool
    deleted_at: datetime | None
    deleted_by: str | None
    deletion_reason: str | None
    object_lock_status: str
    object_lock_mode: str | None
    object_lock_retain_until: datetime | None
    object_lock_legal_hold: bool | None
    object_lock_verified_at: datetime | None
    created_by: str
    created_at: datetime


class ConnectorScheduleCreate(BaseModel):
    connector_type: str = Field(pattern="^(aws-s3|google-drive|github|gitlab|sharepoint)$")
    account: str = Field(min_length=1, max_length=240)
    schedule_type: str = Field(default="interval", pattern="^(interval|cron)$")
    interval_seconds: int = Field(default=3600, ge=60, le=604800)
    cron_expression: str | None = Field(default=None, min_length=9, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=120)
    maintenance_windows: list[dict] = Field(default_factory=list, max_length=20)
    enabled: bool = True
    secret_ref: str | None = Field(default=None, pattern=r"^(env|file):.+$")
    cursor: str | None = None
    max_items: int = Field(default=500, ge=1, le=5000)
    api_url: str | None = None
    site_id: str | None = None
    drive_id: str | None = None
    region: str | None = None
    prefix: str = ""
    impersonate_user: str | None = None


class ConnectorScheduleUpdate(BaseModel):
    enabled: bool | None = None
    schedule_type: str | None = Field(default=None, pattern="^(interval|cron)$")
    interval_seconds: int | None = Field(default=None, ge=60, le=604800)
    cron_expression: str | None = Field(default=None, min_length=9, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=120)
    maintenance_windows: list[dict] | None = Field(default=None, max_length=20)
    next_run_at: datetime | None = None


class ProviderRateLimitUpdate(BaseModel):
    max_requests: int = Field(ge=1, le=1_000_000)
    window_seconds: int = Field(ge=1, le=86400)


class EvidenceGovernanceUpdate(BaseModel):
    retention_until: datetime | None = None
    legal_hold: bool | None = None
    reason: str = Field(min_length=3, max_length=2000)


class PolicyBundleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.-]+$")
    version: int = Field(ge=1)
    policies: list[dict] = Field(min_length=1, max_length=200)


class PolicyExceptionCreate(BaseModel):
    policy_id: str | None = Field(default=None, max_length=160)
    agent_key: str | None = Field(default=None, max_length=120)
    asset_id: int | None = Field(default=None, ge=1)
    destination: str | None = Field(default=None, max_length=240)
    action: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=240)
    override_decision: str = Field(pattern="^(allow|conditional)$")
    reason: str = Field(min_length=3, max_length=2000)
    controls: list[str] = Field(default_factory=list, max_length=50)
    expires_at: datetime


class PolicyApproverDelegationCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=320)
    bundle_name: str | None = Field(default=None, min_length=1, max_length=160)
    can_approve_bundles: bool = True
    can_approve_exceptions: bool = False
    expires_at: datetime


class PolicyExceptionRenewalRequest(BaseModel):
    expires_at: datetime
    reason: str = Field(min_length=3, max_length=2000)


class EvidenceDispositionCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    action: str = Field(default="delete", pattern="^delete$")


class IntegrationReplayRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class IntegrationEndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mode: str = Field(default="observe", pattern="^(observe|enforce)$")
    event_format: str = Field(
        default="native",
        pattern="^(native|cloudevents|cef|splunk-hec)$",
    )
    url: str = Field(min_length=8, max_length=2048)
    secret_ref: str | None = Field(default=None, pattern=r"^(env|file):.+$")
    events: list[str] = Field(default_factory=lambda: ["policy.decision"], min_length=1, max_length=50)
    enabled: bool = True


class ServiceAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    owner: str = Field(min_length=1, max_length=320)
    role: str = Field(default="read-only", min_length=1, max_length=80)
    credential_days: int = Field(default=90, ge=1, le=365)


class ServiceAccountRotate(BaseModel):
    credential_days: int = Field(default=90, ge=1, le=365)
    grace_hours: int = Field(default=24, ge=0, le=168)


class GovernanceTaskAssign(BaseModel):
    assigned_to: str = Field(min_length=1, max_length=320)


class OwnershipCampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    scope: dict = Field(default_factory=dict)
    due_at: datetime


class OwnershipAttestation(BaseModel):
    confirmed: bool
    owner: str | None = Field(default=None, min_length=1, max_length=320)
    note: str = Field(default="", max_length=2000)
    remediation_action: str | None = Field(default=None, max_length=2000)
    remediation_due_at: datetime | None = None


class OwnershipRemediationUpdate(BaseModel):
    action: str = Field(min_length=3, max_length=2000)
    due_at: datetime


class GraphExportCreate(BaseModel):
    format: str = Field(default="json", pattern="^(json|csv|graphml)$")
    relationships: list[str] = Field(default_factory=list, max_length=100)
    sink_uri: str | None = Field(default=None, max_length=2048)
    max_edges: int = Field(default=250_000, ge=1, le=1_000_000)
