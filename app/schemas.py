from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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


class PolicyRequest(BaseModel):
    asset_id: int
    destination: str = Field(default="external-ai", examples=["openai", "claude", "internal-rag"])
    action: str = Field(default="send", examples=["send", "summarize", "embed", "train"])
    actor: str = "demo-agent"


class PolicyDecision(BaseModel):
    decision: str
    asset_id: int
    destination: str
    action: str
    reason: str
    controls: list[str]
    confidence: float


class S3ScanRequest(BaseModel):
    bucket: str
    prefix: str = ""
    region: str | None = None
    max_objects: int = Field(default=500, ge=1, le=5000)


class DemoGenerateRequest(BaseModel):
    profile: str = "financial-services"
    samples: int = Field(default=240, ge=80, le=600)
    seed: int = Field(default=41, ge=0, le=999999)
