from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class DataAsset(Base):
    __tablename__ = "data_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    source_account: Mapped[str] = mapped_column(String(160), default="demo")
    external_id: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
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
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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

class AIAgent(Base):
    __tablename__ = "ai_agents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
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

class DecisionAudit(Base):
    __tablename__ = "decision_audits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
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


class ConnectorRun(Base):
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
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ClassificationReview(Base):
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AIUsageEvent(Base):
    __tablename__ = "ai_usage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(240), unique=True, index=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    source_id: Mapped[str] = mapped_column(String(320), index=True)
    relationship: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str] = mapped_column(String(320), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
