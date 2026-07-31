import hashlib
import json
import re
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.gdrive import GoogleDriveConnector
from connectors.github import GitHubConnector
from connectors.gitlab import GitLabConnector
from connectors.s3 import S3Connector
from connectors.sharepoint import SharePointConnector
from .classification import classify, heuristic_classify
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .demo_data import DEMO_ASSETS
from .enterprise_demo import PROFILES, generate_enterprise_assets, profile_catalog, represented_count
from .lifecycle import calculate_lifecycle
from .agents import DEMO_AGENTS
from .auth import Principal, current_principal, oidc_configuration, require_role
from .models import (
    AIAgent,
    AIUsageEvent,
    BackgroundJob,
    ClassificationReview,
    ConnectorSchedule,
    ConnectorRun,
    DataAsset,
    DecisionAudit,
    EvidenceDisposition,
    EvidenceRecord,
    GraphEdge,
    IdentityDeprovisionWorkflow,
    IntegrationDelivery,
    IntegrationEndpoint,
    LineageEvent,
    PolicyBundle,
    utc_now,
)
from .observability import configure_observability
from .services.connectors import ingest_connector, safe_connector_error
from .services.evidence import evidence_health, load_evidence, store_evidence
from .services.jobs import cancel_job, enqueue_job, resolve_secret, retry_job
from .services.policy import audit as audit_decision, evaluate as evaluate_decision
from .services.search import index_asset, search_asset_ids, search_health
from .services.schedules import ProviderRateLimitExceeded, provider_request_guard
from .schemas import (
    AgentCreate,
    AgentOut,
    AIUsageEventCreate,
    AssetOut,
    BackgroundJobOut,
    ClassificationReviewResolution,
    ConnectorJobRequest,
    ConnectorScanRequest,
    DemoGenerateRequest,
    EvidenceOut,
    GDriveScanRequest,
    PolicyDecision,
    PolicyRequest,
    PolicySimulationRequest,
    S3ScanRequest,
)
from .v13 import router as v13_router
from .v14 import router as v14_router


async def enrich_asset(asset: DataAsset, deterministic: bool = False) -> None:
    result = heuristic_classify(asset.name, asset.path, asset.mime_type) if deterministic else await classify(asset.name, asset.path, asset.mime_type)
    asset.sensitivity = result.sensitivity
    asset.classification_labels = ", ".join(result.labels)
    asset.business_domain = result.business_domain
    asset.classification_reason = result.reason
    asset.classification_confidence = result.confidence
    lifecycle = calculate_lifecycle(asset.created_at, asset.modified_at, asset.last_accessed_at, result.sensitivity)
    asset.age_days = lifecycle.age_days
    asset.stale_score = lifecycle.stale_score
    asset.lifecycle_state = lifecycle.state
    asset.retention_action = lifecycle.action
    asset.retention_reason = lifecycle.reason
    if asset.public_access and result.sensitivity in {"Confidential", "Restricted"}:
        asset.ai_access = "Deny"
        asset.ai_access_reason = "Sensitive asset has public exposure and requires remediation before AI use."
    elif result.sensitivity == "Restricted":
        asset.ai_access = "Conditional"
        asset.ai_access_reason = "Restricted data requires an approved private model, redaction, and audit logging."
    elif result.sensitivity == "Confidential":
        asset.ai_access = "Conditional"
        asset.ai_access_reason = "Use approved enterprise AI destinations with no-training guarantees."
    else:
        asset.ai_access = "Allow"
        asset.ai_access_reason = "No high-risk indicators detected; standard enterprise controls apply."


async def seed_demo(tenant_id: str | None = None) -> None:
    tenant_id = tenant_id or settings.default_tenant
    db = SessionLocal()
    try:
        if db.scalar(select(func.count(DataAsset.id)).where(DataAsset.tenant_id == tenant_id)) == 0:
            for item in DEMO_ASSETS:
                asset = DataAsset(tenant_id=tenant_id, **item)
                await enrich_asset(asset, deterministic=True)
                db.add(asset)
            db.commit()
        if db.scalar(select(func.count(AIAgent.id)).where(AIAgent.tenant_id == tenant_id)) == 0:
            for item in DEMO_AGENTS:
                db.add(AIAgent(tenant_id=tenant_id, **item))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    if settings.auto_seed_demo:
        await seed_demo()
    yield


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
configure_observability(app)
app.include_router(v14_router)
app.include_router(v13_router)
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.exception_handler(ProviderRateLimitExceeded)
def provider_rate_limit_handler(_request: Request, exc: ProviderRateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc), "provider": exc.provider},
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


@app.get("/", response_class=FileResponse)
def dashboard(request: Request):
    del request
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"ok": True, "version": settings.version}


@app.get("/ready")
def readiness(db: Session = Depends(get_db)):
    db.execute(select(1))
    search = search_health()
    evidence = evidence_health()
    ready = evidence["ok"] and (search["ok"] or not settings.opensearch_required)
    return Response(
        content=json.dumps({"ok": ready, "database": {"ok": True}, "search": search, "evidence": evidence}),
        status_code=200 if ready else 503,
        media_type="application/json",
    )


@app.get("/api/v1/assets", response_model=list[AssetOut])
def list_assets(
    sensitivity: str | None = None,
    lifecycle: str | None = None,
    source: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    stmt = (
        select(DataAsset)
        .where(DataAsset.tenant_id == principal.tenant_id)
        .order_by(DataAsset.stale_score.desc(), DataAsset.id.desc())
    )
    if sensitivity:
        stmt = stmt.where(DataAsset.sensitivity == sensitivity)
    if lifecycle:
        stmt = stmt.where(DataAsset.lifecycle_state == lifecycle)
    if source:
        stmt = stmt.where(DataAsset.source == source)
    if search:
        asset_ids = search_asset_ids(search, principal.tenant_id)
        if asset_ids is not None:
            if not asset_ids:
                return []
            stmt = stmt.where(DataAsset.id.in_(asset_ids))
        else:
            pattern = f"%{search}%"
            stmt = stmt.where((DataAsset.name.ilike(pattern)) | (DataAsset.path.ilike(pattern)))
    return list(db.scalars(stmt).all())


@app.get("/api/v1/assets/{asset_id}", response_model=AssetOut)
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    asset = _asset_for_tenant(db, asset_id, principal.tenant_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    return asset


@app.get("/api/v1/summary")
def summary(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    tenant_id = principal.tenant_id
    assets = list(db.scalars(select(DataAsset).where(DataAsset.tenant_id == tenant_id)).all())
    sensitivity, lifecycle, sources, domains = {}, {}, {}, {}
    total_assets = restricted_assets = stale_assets = ai_blocked = priority_reviews = 0
    storage_bytes = annual_storage_cost = 0
    profile_key = "starter"
    for asset in assets:
        weight = represented_count(asset)
        total_assets += weight
        sensitivity[asset.sensitivity] = sensitivity.get(asset.sensitivity, 0) + weight
        lifecycle[asset.lifecycle_state] = lifecycle.get(asset.lifecycle_state, 0) + weight
        sources[asset.source] = sources.get(asset.source, 0) + weight
        domains[asset.business_domain] = domains.get(asset.business_domain, 0) + weight
        restricted_assets += weight if asset.sensitivity == "Restricted" else 0
        stale_assets += weight if asset.lifecycle_state in {"Stale", "Aging"} else 0
        ai_blocked += weight if asset.ai_access == "Deny" else 0
        priority_reviews += weight if asset.retention_action == "Priority owner review" else 0
        storage_bytes += asset.size_bytes * weight
        try:
            meta = json.loads(asset.metadata_json or "{}")
            annual_storage_cost += float(meta.get("annual_storage_cost_share", 0))
            profile_key = meta.get("demo_profile", profile_key)
        except (ValueError, TypeError):
            pass
    profile = PROFILES.get(profile_key)
    archive_candidates = sum(weighted for state, weighted in lifecycle.items() if state in {"Aging", "Stale"})
    estimated_savings = round(annual_storage_cost * (archive_candidates / max(total_assets, 1)) * .55)
    active_policy_bundle = db.scalar(
        select(PolicyBundle).where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.status == "active",
        )
    )
    return {
        "organization": profile.name if profile else "OpenDataGraph Demo",
        "industry": profile.industry if profile else "Starter Dataset",
        "profile": profile_key, "sample_records": len(assets), "total_assets": total_assets,
        "restricted_assets": restricted_assets, "stale_assets": stale_assets, "archive_candidates": archive_candidates,
        "ai_blocked": ai_blocked, "sensitivity": sensitivity, "lifecycle": lifecycle, "sources": sources, "domains": domains,
        "storage_bytes": storage_bytes, "priority_reviews": priority_reviews, "estimated_annual_savings": estimated_savings,
        "ai_readiness_score": max(18, min(94, round(88 - (restricted_assets/max(total_assets,1))*28 - (ai_blocked/max(total_assets,1))*22))),
        "tenant_id": tenant_id,
        "connector_runs": db.scalar(
            select(func.count(ConnectorRun.id)).where(ConnectorRun.tenant_id == tenant_id)
        )
        or 0,
        "pending_classification_reviews": db.scalar(
            select(func.count(ClassificationReview.id)).where(
                ClassificationReview.tenant_id == tenant_id,
                ClassificationReview.status == "pending",
            )
        ) or 0,
        "ai_usage_events": db.scalar(
            select(func.count(AIUsageEvent.id)).where(AIUsageEvent.tenant_id == tenant_id)
        )
        or 0,
        "graph_edges": db.scalar(select(func.count(GraphEdge.id)).where(GraphEdge.tenant_id == tenant_id)) or 0,
        "background_jobs": db.scalar(
            select(func.count(BackgroundJob.id)).where(BackgroundJob.tenant_id == tenant_id)
        )
        or 0,
        "evidence_records": db.scalar(
            select(func.count(EvidenceRecord.id)).where(EvidenceRecord.tenant_id == tenant_id)
        )
        or 0,
        "connector_schedules": db.scalar(
            select(func.count(ConnectorSchedule.id)).where(
                ConnectorSchedule.tenant_id == tenant_id,
                ConnectorSchedule.enabled.is_(True),
            )
        )
        or 0,
        "integration_endpoints": db.scalar(
            select(func.count(IntegrationEndpoint.id)).where(
                IntegrationEndpoint.tenant_id == tenant_id,
                IntegrationEndpoint.enabled.is_(True),
            )
        )
        or 0,
        "integration_deliveries": db.scalar(
            select(func.count(IntegrationDelivery.id)).where(
                IntegrationDelivery.tenant_id == tenant_id
            )
        )
        or 0,
        "dead_letter_deliveries": db.scalar(
            select(func.count(IntegrationDelivery.id)).where(
                IntegrationDelivery.tenant_id == tenant_id,
                IntegrationDelivery.status == "dead-letter",
            )
        )
        or 0,
        "pending_evidence_dispositions": db.scalar(
            select(func.count(EvidenceDisposition.id)).where(
                EvidenceDisposition.tenant_id == tenant_id,
                EvidenceDisposition.status == "pending",
            )
        )
        or 0,
        "identity_deprovisioning": db.scalar(
            select(func.count(IdentityDeprovisionWorkflow.id)).where(
                IdentityDeprovisionWorkflow.tenant_id == tenant_id,
                IdentityDeprovisionWorkflow.status.in_(("pending", "running")),
            )
        )
        or 0,
        "lineage_events": db.scalar(
            select(func.count(LineageEvent.id)).where(LineageEvent.tenant_id == tenant_id)
        )
        or 0,
        "active_policy_bundle": (
            {"name": active_policy_bundle.name, "version": active_policy_bundle.version}
            if active_policy_bundle
            else None
        ),
        "search_backend": settings.search_backend,
    }


@app.get("/api/v1/agents", response_model=list[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    statement = (
        select(AIAgent)
        .where(AIAgent.tenant_id == principal.tenant_id)
        .order_by(AIAgent.risk_level.desc(), AIAgent.name)
    )
    return list(db.scalars(statement).all())

@app.post("/api/v1/agents", response_model=AgentOut)
def create_agent(
    req: AgentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    if db.scalar(
        select(AIAgent).where(AIAgent.tenant_id == principal.tenant_id, AIAgent.key == req.key)
    ):
        raise HTTPException(409, "Agent key already exists")
    agent = AIAgent(tenant_id=principal.tenant_id, **req.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent

@app.get("/api/v1/policy/audit")
def policy_audit(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    rows = list(
        db.scalars(
            select(DecisionAudit)
            .where(DecisionAudit.tenant_id == principal.tenant_id)
            .order_by(DecisionAudit.created_at.desc())
            .limit(limit)
        ).all()
    )
    return [
        {
            "id": row.id,
            "created_at": row.created_at,
            "agent_key": row.agent_key,
            "asset_id": row.asset_id,
            "action": row.action,
            "destination": row.destination,
            "purpose": row.purpose,
            "decision": row.decision,
            "risk_score": row.risk_score,
            "policy_version": row.policy_version,
            "reasons": json.loads(row.reasons_json),
            "controls": json.loads(row.controls_json),
        }
        for row in rows
    ]

@app.post("/api/v1/policy/evaluate", response_model=PolicyDecision)
def evaluate_policy(
    req: PolicyRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    asset = _asset_for_tenant(db, req.asset_id, principal.tenant_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    agent = _agent_for_tenant(db, req.agent_key, principal.tenant_id)
    if not agent:
        raise HTTPException(404, "AI agent not found")
    result = evaluate_decision(
        agent,
        asset,
        req.destination,
        req.action,
        req.purpose,
        db,
        principal.tenant_id,
    )
    audit_decision(db, req, result, principal.tenant_id)
    return PolicyDecision(
        asset_id=asset.id,
        agent_key=agent.key,
        destination=req.destination,
        action=req.action,
        purpose=req.purpose,
        **result,
    )


@app.post("/api/v1/connectors/s3/scan")
async def scan_s3(
    req: S3ScanRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    try:
        connector = S3Connector(
            req.bucket,
            req.prefix,
            req.region,
            before_request=provider_request_guard(db, principal.tenant_id, "aws-s3"),
        )
        return await ingest_connector(
            db,
            connector,
            max_items=req.max_objects,
            tenant_id=principal.tenant_id,
        )
    except ProviderRateLimitExceeded:
        raise
    except Exception as exc:
        raise HTTPException(400, f"S3 scan failed: {safe_connector_error(exc)}") from exc


@app.post("/api/v1/connectors/google-drive/scan")
async def scan_google_drive(
    req: GDriveScanRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    try:
        credentials_info = json.loads(resolve_secret(f"file:{req.credentials_file}"))
        connector = GoogleDriveConnector(
            account=req.drive_id or req.impersonate_user or "my-drive",
            credentials_info=credentials_info,
            impersonate_user=req.impersonate_user,
            drive_id=req.drive_id,
            before_request=provider_request_guard(db, principal.tenant_id, "google-drive"),
        )
        return await ingest_connector(
            db,
            connector,
            max_items=req.max_files,
            tenant_id=principal.tenant_id,
        )
    except ProviderRateLimitExceeded:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Google Drive scan failed: {safe_connector_error(exc)}") from exc


@app.post("/api/v1/demo/reset")
async def reset_demo(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    db.query(DataAsset).filter(DataAsset.tenant_id == principal.tenant_id).delete()
    db.commit()
    await seed_demo(principal.tenant_id)
    return {"ok": True}


@app.get("/api/v1/demo/profiles")
def demo_profiles(principal: Principal = Depends(require_role("read-only"))):
    del principal
    return profile_catalog()


@app.post("/api/v1/demo/generate")
async def generate_demo(
    req: DemoGenerateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    try:
        profile, records = generate_enterprise_assets(req.profile, req.samples, req.seed)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown demo profile: {req.profile}") from exc
    db.query(DataAsset).filter(DataAsset.tenant_id == principal.tenant_id).delete()
    db.commit()
    for record in records:
        asset = DataAsset(tenant_id=principal.tenant_id, **record)
        await enrich_asset(asset, deterministic=True)
        db.add(asset)
    db.commit()
    for asset in db.scalars(select(DataAsset).where(DataAsset.tenant_id == principal.tenant_id)):
        index_asset(asset)
    return {"ok": True, "profile": profile.key, "organization": profile.name,
            "sample_records": len(records), "represented_assets": profile.represented_assets}


@app.get("/api/v1/auth/configuration")
def auth_configuration(principal: Principal = Depends(current_principal)):
    return {"auth_disabled": settings.auth_disabled, "principal": principal.__dict__, "oidc": oidc_configuration()}


@app.post("/api/v1/connectors/{connector_type}/scan")
async def scan_connector(
    connector_type: str,
    req: ConnectorScanRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    if not req.token:
        raise HTTPException(400, "A short-lived connector token is required")
    try:
        if connector_type == "github":
            connector = GitHubConnector(
                req.account,
                req.token,
                req.api_url or "https://api.github.com",
                allowed_hosts=settings.github_allowed_hosts,
                before_request=provider_request_guard(db, principal.tenant_id, "github"),
            )
        elif connector_type == "gitlab":
            connector = GitLabConnector(
                req.account,
                req.token,
                req.api_url or "https://gitlab.com/api/v4",
                allowed_hosts=settings.gitlab_allowed_hosts,
                before_request=provider_request_guard(db, principal.tenant_id, "gitlab"),
            )
        elif connector_type == "sharepoint":
            if not req.site_id or not req.drive_id:
                raise HTTPException(400, "site_id and drive_id are required for SharePoint")
            connector = SharePointConnector(
                req.site_id,
                req.drive_id,
                req.token,
                allowed_hosts=settings.sharepoint_allowed_hosts,
                before_request=provider_request_guard(db, principal.tenant_id, "sharepoint"),
            )
        else:
            raise HTTPException(404, "Supported connector types: github, gitlab, sharepoint")
        return await ingest_connector(
            db,
            connector,
            req.cursor,
            req.max_items,
            tenant_id=principal.tenant_id,
        )
    except HTTPException:
        raise
    except ProviderRateLimitExceeded:
        raise
    except Exception as exc:
        raise HTTPException(400, f"{connector_type} scan failed: {safe_connector_error(exc)}") from exc


@app.post("/api/v1/connectors/{connector_type}/jobs", response_model=BackgroundJobOut, status_code=202)
def enqueue_connector_job(
    connector_type: str,
    req: ConnectorJobRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    payload = {"connector_type": connector_type, **req.model_dump(exclude_none=True, exclude={"max_attempts"})}
    try:
        return enqueue_job(
            db,
            tenant_id=principal.tenant_id,
            job_type="connector.scan",
            payload=payload,
            created_by=principal.subject,
            max_attempts=req.max_attempts,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/v1/connectors/runs")
def connector_runs(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    rows = list(
        db.scalars(
            select(ConnectorRun)
            .where(ConnectorRun.tenant_id == principal.tenant_id)
            .order_by(ConnectorRun.started_at.desc())
            .limit(limit)
        ).all()
    )
    return [
        {
            "id": row.id,
            "source": row.source,
            "source_account": row.source_account,
            "status": row.status,
            "cursor": row.cursor,
            "next_cursor": row.next_cursor,
            "imported": row.imported,
            "updated": row.updated,
            "error": row.error,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }
        for row in rows
    ]


@app.get("/api/v1/classification/reviews")
def classification_reviews(
    status: str = "pending",
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    rows = list(
        db.scalars(
            select(ClassificationReview)
            .where(
                ClassificationReview.tenant_id == principal.tenant_id,
                ClassificationReview.status == status,
            )
            .order_by(ClassificationReview.confidence, ClassificationReview.created_at)
        ).all()
    )
    return [
        {
            "id": row.id,
            "asset_id": row.asset_id,
            "status": row.status,
            "original_sensitivity": row.original_sensitivity,
            "original_labels": row.original_labels,
            "confidence": row.confidence,
            "reason": row.reason,
            "corrected_sensitivity": row.corrected_sensitivity,
            "corrected_labels": row.corrected_labels,
            "reviewer": row.reviewer,
            "created_at": row.created_at,
            "resolved_at": row.resolved_at,
        }
        for row in rows
    ]


@app.post("/api/v1/classification/reviews/{review_id}")
def resolve_classification_review(
    review_id: int,
    req: ClassificationReviewResolution,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    review = db.scalar(
        select(ClassificationReview).where(
            ClassificationReview.id == review_id,
            ClassificationReview.tenant_id == principal.tenant_id,
        )
    )
    if not review:
        raise HTTPException(404, "Classification review not found")
    asset = _asset_for_tenant(db, review.asset_id, principal.tenant_id)
    if not asset:
        raise HTTPException(404, "Reviewed asset not found")
    if req.status == "corrected":
        if not req.sensitivity:
            raise HTTPException(400, "A corrected sensitivity is required")
        asset.sensitivity = req.sensitivity
        if req.labels:
            asset.classification_labels = ", ".join(req.labels)
        asset.classification_reason = f"Corrected by {req.reviewer or principal.subject} during human review."
        asset.classification_confidence = 1.0
    review.status = req.status
    review.corrected_sensitivity = req.sensitivity
    review.corrected_labels = ", ".join(req.labels) if req.labels else None
    review.reviewer = req.reviewer or principal.subject
    review.resolved_at = utc_now()
    db.commit()
    index_asset(asset)
    return {"ok": True, "review_id": review.id, "status": review.status, "asset_id": asset.id}


@app.post("/api/v1/policy/simulate")
def simulate_policy(
    req: PolicySimulationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    asset = _asset_for_tenant(db, req.asset_id, principal.tenant_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    agent = _agent_for_tenant(db, req.agent_key, principal.tenant_id)
    if not agent:
        raise HTTPException(404, "AI agent not found")
    result = evaluate_decision(
        agent,
        asset,
        req.destination,
        req.action,
        req.purpose,
        db,
        principal.tenant_id,
    )
    return {"simulation": True, "asset_id": asset.id, "agent_key": agent.key, **result}


@app.post("/api/v1/ai-usage/events")
def ingest_ai_usage_event(
    req: AIUsageEventCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    existing = db.scalar(
        select(AIUsageEvent).where(
            AIUsageEvent.tenant_id == principal.tenant_id,
            AIUsageEvent.event_id == req.event_id,
        )
    )
    if existing:
        return {"ok": True, "idempotent": True, "event_id": existing.event_id, "decision": existing.decision}
    asset = _asset_for_tenant(db, req.asset_id, principal.tenant_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    agent = _agent_for_tenant(db, req.agent_key, principal.tenant_id)
    if not agent:
        raise HTTPException(404, "AI agent not found")
    result = evaluate_decision(
        agent,
        asset,
        req.destination,
        req.action,
        req.purpose,
        db,
        principal.tenant_id,
    )
    event = AIUsageEvent(
        tenant_id=principal.tenant_id,
        event_id=req.event_id,
        agent_key=req.agent_key,
        user_identity=req.user_identity,
        asset_id=req.asset_id,
        model=req.model,
        destination=req.destination,
        purpose=req.purpose,
        action=req.action,
        occurred_at=req.timestamp.replace(tzinfo=None),
        metadata_json=json.dumps(req.metadata),
        decision=result["decision"],
        risk_score=result["risk_score"],
    )
    db.add(event)
    db.add(
        GraphEdge(
            tenant_id=principal.tenant_id,
            source_type="agent",
            source_id=req.agent_key,
            relationship="accessed",
            target_type="asset",
            target_id=str(req.asset_id),
            metadata_json=json.dumps({"event_id": req.event_id, "model": req.model, "decision": result["decision"]}),
        )
    )
    agent.last_activity_at = req.timestamp.replace(tzinfo=None)
    db.commit()
    return {
        "ok": True,
        "idempotent": False,
        "event_id": event.event_id,
        "decision": event.decision,
        "risk_score": event.risk_score,
        "matched_policies": result["matched_policies"],
    }


@app.get("/api/v1/ai-usage/events")
def list_ai_usage_events(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    rows = list(
        db.scalars(
            select(AIUsageEvent)
            .where(AIUsageEvent.tenant_id == principal.tenant_id)
            .order_by(AIUsageEvent.occurred_at.desc())
            .limit(limit)
        ).all()
    )
    return [
        {
            "event_id": row.event_id,
            "agent_key": row.agent_key,
            "user_identity": row.user_identity,
            "asset_id": row.asset_id,
            "model": row.model,
            "destination": row.destination,
            "purpose": row.purpose,
            "action": row.action,
            "timestamp": row.occurred_at,
            "metadata": json.loads(row.metadata_json),
            "decision": row.decision,
            "risk_score": row.risk_score,
        }
        for row in rows
    ]


@app.get("/api/v1/graph/relationships")
def graph_relationships(
    asset_id: int | None = None,
    agent_key: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("read-only")),
):
    statement = (
        select(GraphEdge)
        .where(GraphEdge.tenant_id == principal.tenant_id)
        .order_by(GraphEdge.created_at.desc())
    )
    if asset_id is not None:
        statement = statement.where(
            ((GraphEdge.source_type == "asset") & (GraphEdge.source_id == str(asset_id)))
            | ((GraphEdge.target_type == "asset") & (GraphEdge.target_id == str(asset_id)))
        )
    if agent_key:
        statement = statement.where(GraphEdge.source_type == "agent", GraphEdge.source_id == agent_key)
    rows = list(db.scalars(statement.limit(limit)).all())
    return [
        {
            "id": row.id,
            "source": {"type": row.source_type, "id": row.source_id},
            "relationship": row.relationship,
            "target": {"type": row.target_type, "id": row.target_id},
            "metadata": json.loads(row.metadata_json),
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.post("/api/v1/search/reindex", response_model=BackgroundJobOut, status_code=202)
def enqueue_reindex(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    return enqueue_job(
        db,
        tenant_id=principal.tenant_id,
        job_type="catalog.reindex",
        payload={},
        created_by=principal.subject,
    )


@app.get("/api/v1/jobs", response_model=list[BackgroundJobOut])
def list_jobs(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = (
        select(BackgroundJob)
        .where(BackgroundJob.tenant_id == principal.tenant_id)
        .order_by(BackgroundJob.created_at.desc())
    )
    if status:
        statement = statement.where(BackgroundJob.status == status)
    return list(db.scalars(statement.limit(limit)).all())


@app.get("/api/v1/jobs/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    job = _job_for_tenant(db, job_id, principal.tenant_id)
    if not job:
        raise HTTPException(404, "Background job not found")
    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "job_type": job.job_type,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "available_at": job.available_at,
        "claimed_at": job.claimed_at,
        "finished_at": job.finished_at,
        "cancel_requested": job.cancel_requested,
        "error": job.error,
        "result": json.loads(job.result_json or "{}"),
        "created_by": job.created_by,
        "created_at": job.created_at,
    }


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=BackgroundJobOut)
def request_job_cancellation(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    job = _job_for_tenant(db, job_id, principal.tenant_id)
    if not job:
        raise HTTPException(404, "Background job not found")
    _authorize_job_control(job, principal)
    return cancel_job(db, job)


@app.post("/api/v1/jobs/{job_id}/retry", response_model=BackgroundJobOut)
def request_job_retry(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("connector-operator")),
):
    job = _job_for_tenant(db, job_id, principal.tenant_id)
    if not job:
        raise HTTPException(404, "Background job not found")
    _authorize_job_control(job, principal)
    try:
        return retry_job(db, job)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/v1/evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    category: str = Form(..., min_length=1, max_length=120),
    subject_type: str = Form(..., min_length=1, max_length=80),
    subject_id: str = Form(..., min_length=1, max_length=320),
    metadata_json: str = Form("{}", max_length=16_384),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("data-owner")),
):
    content = await file.read(settings.evidence_max_bytes + 1)
    if len(content) > settings.evidence_max_bytes:
        raise HTTPException(413, f"Evidence exceeds the {settings.evidence_max_bytes}-byte limit")
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "metadata_json must be valid JSON") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(400, "metadata_json must contain a JSON object")
    evidence_id = str(uuid4())
    try:
        storage_uri, digest = store_evidence(
            principal.tenant_id,
            evidence_id,
            content,
            file.content_type or "application/octet-stream",
        )
    except (RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(503, f"Evidence storage failed: {exc}") from exc
    record = EvidenceRecord(
        tenant_id=principal.tenant_id,
        evidence_id=evidence_id,
        category=category,
        subject_type=subject_type,
        subject_id=subject_id,
        filename=Path(file.filename or "evidence.bin").name[:512],
        content_type=file.content_type or "application/octet-stream",
        storage_uri=storage_uri,
        sha256=digest,
        size_bytes=len(content),
        metadata_json=json.dumps(metadata),
        retention_until=(
            utc_now() + timedelta(days=settings.evidence_default_retention_days)
            if settings.evidence_default_retention_days > 0
            else None
        ),
        created_by=principal.subject,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _evidence_response(record)


@app.get("/api/v1/evidence", response_model=list[EvidenceOut])
def list_evidence(
    subject_type: str | None = None,
    subject_id: str | None = None,
    include_deleted: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = (
        select(EvidenceRecord)
        .where(EvidenceRecord.tenant_id == principal.tenant_id)
        .order_by(EvidenceRecord.created_at.desc())
    )
    if subject_type:
        statement = statement.where(EvidenceRecord.subject_type == subject_type)
    if subject_id:
        statement = statement.where(EvidenceRecord.subject_id == subject_id)
    if not include_deleted:
        statement = statement.where(EvidenceRecord.deleted_at.is_(None))
    return [_evidence_response(record) for record in db.scalars(statement.limit(limit)).all()]


@app.get("/api/v1/evidence/{evidence_id}/download")
def download_evidence(
    evidence_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    record = db.scalar(
        select(EvidenceRecord).where(
            EvidenceRecord.tenant_id == principal.tenant_id,
            EvidenceRecord.evidence_id == evidence_id,
        )
    )
    if not record:
        raise HTTPException(404, "Evidence record not found")
    if record.deleted_at:
        raise HTTPException(410, "Evidence object has been deleted")
    try:
        content = load_evidence(record.storage_uri)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(503, f"Evidence retrieval failed: {exc}") from exc
    if hashlib.sha256(content).hexdigest() != record.sha256:
        raise HTTPException(503, "Evidence integrity verification failed")
    filename = re.sub(r"[\r\n\"]", "_", Path(record.filename).name)
    return Response(
        content=content,
        media_type=record.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-SHA256": record.sha256,
            "X-Content-Type-Options": "nosniff",
        },
    )


def _asset_for_tenant(db: Session, asset_id: int, tenant_id: str) -> DataAsset | None:
    return db.scalar(
        select(DataAsset).where(
            DataAsset.id == asset_id,
            DataAsset.tenant_id == tenant_id,
        )
    )


def _agent_for_tenant(db: Session, agent_key: str, tenant_id: str) -> AIAgent | None:
    return db.scalar(
        select(AIAgent).where(
            AIAgent.key == agent_key,
            AIAgent.tenant_id == tenant_id,
        )
    )


def _job_for_tenant(db: Session, job_id: str, tenant_id: str) -> BackgroundJob | None:
    return db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.job_id == job_id,
            BackgroundJob.tenant_id == tenant_id,
        )
    )


def _authorize_job_control(job: BackgroundJob, principal: Principal) -> None:
    if job.job_type != "connector.scan" and principal.role != "administrator":
        raise HTTPException(403, "administrator role required for non-connector jobs")


def _evidence_response(record: EvidenceRecord) -> dict:
    return {
        "evidence_id": record.evidence_id,
        "tenant_id": record.tenant_id,
        "category": record.category,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "filename": record.filename,
        "content_type": record.content_type,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "metadata": json.loads(record.metadata_json or "{}"),
        "retention_until": record.retention_until,
        "legal_hold": record.legal_hold,
        "deleted_at": record.deleted_at,
        "deleted_by": record.deleted_by,
        "deletion_reason": record.deletion_reason,
        "object_lock_status": record.object_lock_status,
        "object_lock_mode": record.object_lock_mode,
        "object_lock_retain_until": record.object_lock_retain_until,
        "object_lock_legal_hold": record.object_lock_legal_hold,
        "object_lock_verified_at": record.object_lock_verified_at,
        "created_by": record.created_by,
        "created_at": record.created_at,
    }
