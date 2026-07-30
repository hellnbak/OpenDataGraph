import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.s3 import scan_bucket
from connectors.gdrive import scan_drive
from connectors.github import GitHubConnector
from connectors.gitlab import GitLabConnector
from connectors.sharepoint import SharePointConnector
from .classification import classify, heuristic_classify
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .demo_data import DEMO_ASSETS
from .enterprise_demo import PROFILES, generate_enterprise_assets, profile_catalog, represented_count
from .lifecycle import calculate_lifecycle
from .agents import DEMO_AGENTS
from .auth import Principal, current_principal, oidc_configuration, require_role
from .services.connectors import ingest_connector
from .services.policy import audit as audit_decision, evaluate as evaluate_decision
from .models import AIAgent, AIUsageEvent, ClassificationReview, ConnectorRun, DataAsset, DecisionAudit, GraphEdge
from .schemas import (
    AgentCreate,
    AgentOut,
    AIUsageEventCreate,
    AssetOut,
    ClassificationReviewResolution,
    ConnectorScanRequest,
    DemoGenerateRequest,
    GDriveScanRequest,
    PolicyDecision,
    PolicyRequest,
    PolicySimulationRequest,
    S3ScanRequest,
)


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


async def seed_demo() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(func.count(DataAsset.id))) == 0:
            for item in DEMO_ASSETS:
                asset = DataAsset(**item)
                await enrich_asset(asset, deterministic=True)
                db.add(asset)
            db.commit()
        if db.scalar(select(func.count(AIAgent.id))) == 0:
            for item in DEMO_AGENTS:
                db.add(AIAgent(**item))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.auto_seed_demo:
        await seed_demo()
    yield


app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan)
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=FileResponse)
def dashboard(request: Request):
    del request
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {"ok": True, "version": "1.1.0", "assets": db.scalar(select(func.count(DataAsset.id)))}


@app.get("/api/v1/assets", response_model=list[AssetOut])
def list_assets(
    sensitivity: str | None = None,
    lifecycle: str | None = None,
    source: str | None = None,
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    stmt = select(DataAsset).order_by(DataAsset.stale_score.desc(), DataAsset.id.desc())
    if sensitivity:
        stmt = stmt.where(DataAsset.sensitivity == sensitivity)
    if lifecycle:
        stmt = stmt.where(DataAsset.lifecycle_state == lifecycle)
    if source:
        stmt = stmt.where(DataAsset.source == source)
    if search:
        stmt = stmt.where(DataAsset.name.ilike(f"%{search}%"))
    return list(db.scalars(stmt).all())


@app.get("/api/v1/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(DataAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    return asset


@app.get("/api/v1/summary")
def summary(db: Session = Depends(get_db)):
    assets = list(db.scalars(select(DataAsset)).all())
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
    return {
        "organization": profile.name if profile else "OpenDataGraph Demo",
        "industry": profile.industry if profile else "Starter Dataset",
        "profile": profile_key, "sample_records": len(assets), "total_assets": total_assets,
        "restricted_assets": restricted_assets, "stale_assets": stale_assets, "archive_candidates": archive_candidates,
        "ai_blocked": ai_blocked, "sensitivity": sensitivity, "lifecycle": lifecycle, "sources": sources, "domains": domains,
        "storage_bytes": storage_bytes, "priority_reviews": priority_reviews, "estimated_annual_savings": estimated_savings,
        "ai_readiness_score": max(18, min(94, round(88 - (restricted_assets/max(total_assets,1))*28 - (ai_blocked/max(total_assets,1))*22))),
        "connector_runs": db.scalar(select(func.count(ConnectorRun.id))) or 0,
        "pending_classification_reviews": db.scalar(
            select(func.count(ClassificationReview.id)).where(ClassificationReview.status == "pending")
        ) or 0,
        "ai_usage_events": db.scalar(select(func.count(AIUsageEvent.id))) or 0,
        "graph_edges": db.scalar(select(func.count(GraphEdge.id))) or 0,
    }


@app.get("/api/v1/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return list(db.scalars(select(AIAgent).order_by(AIAgent.risk_level.desc(), AIAgent.name)).all())

@app.post("/api/v1/agents", response_model=AgentOut)
def create_agent(req: AgentCreate, db: Session = Depends(get_db)):
    if db.scalar(select(AIAgent).where(AIAgent.key == req.key)):
        raise HTTPException(409, "Agent key already exists")
    agent=AIAgent(**req.model_dump()); db.add(agent); db.commit(); db.refresh(agent); return agent

@app.get("/api/v1/policy/audit")
def policy_audit(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)):
    rows=list(db.scalars(select(DecisionAudit).order_by(DecisionAudit.created_at.desc()).limit(limit)).all())
    return [{"id":r.id,"created_at":r.created_at,"agent_key":r.agent_key,"asset_id":r.asset_id,"action":r.action,"destination":r.destination,"purpose":r.purpose,"decision":r.decision,"risk_score":r.risk_score,"policy_version":r.policy_version,"reasons":json.loads(r.reasons_json),"controls":json.loads(r.controls_json)} for r in rows]

@app.post("/api/v1/policy/evaluate", response_model=PolicyDecision)
def evaluate_policy(req: PolicyRequest, db: Session = Depends(get_db)):
    asset=db.get(DataAsset,req.asset_id)
    if not asset: raise HTTPException(404,"Asset not found")
    agent=db.scalar(select(AIAgent).where(AIAgent.key==req.agent_key))
    if not agent: raise HTTPException(404,"AI agent not found")
    result=evaluate_decision(agent,asset,req.destination,req.action,req.purpose)
    audit_decision(db,req,result)
    return PolicyDecision(asset_id=asset.id,agent_key=agent.key,destination=req.destination,action=req.action,purpose=req.purpose,**result)


@app.post("/api/v1/connectors/s3/scan")
async def scan_s3(req: S3ScanRequest, db: Session = Depends(get_db)):
    imported = 0
    updated = 0
    try:
        records = list(scan_bucket(req.bucket, req.prefix, req.region, req.max_objects))
    except Exception as exc:
        raise HTTPException(400, f"S3 scan failed: {exc}") from exc
    for record in records:
        existing = db.scalar(select(DataAsset).where(DataAsset.external_id == record["external_id"]))
        metadata = record.pop("metadata")
        if existing:
            asset = existing
            for key, value in record.items():
                setattr(asset, key, value)
            asset.last_seen_at = datetime.utcnow()
            updated += 1
        else:
            asset = DataAsset(**record, metadata_json=json.dumps(metadata))
            db.add(asset)
            imported += 1
        await enrich_asset(asset)
    db.commit()
    return {"ok": True, "bucket": req.bucket, "imported": imported, "updated": updated}


@app.post("/api/v1/connectors/google-drive/scan")
async def scan_google_drive(req: GDriveScanRequest, db: Session = Depends(get_db)):
    imported=updated=0
    try: records=list(scan_drive(req.credentials_file,req.impersonate_user,req.drive_id,req.max_files))
    except Exception as exc: raise HTTPException(400,f"Google Drive scan failed: {exc}") from exc
    for record in records:
        existing=db.scalar(select(DataAsset).where(DataAsset.external_id==record["external_id"]))
        metadata=record.pop("metadata")
        if existing:
            asset=existing
            for key,value in record.items(): setattr(asset,key,value)
            asset.metadata_json=json.dumps(metadata); asset.last_seen_at=datetime.utcnow(); updated+=1
        else:
            asset=DataAsset(**record,metadata_json=json.dumps(metadata)); db.add(asset); imported+=1
        await enrich_asset(asset)
    db.commit()
    return {"ok":True,"imported":imported,"updated":updated,"source":"google-drive"}


@app.post("/api/v1/demo/reset")
async def reset_demo(db: Session = Depends(get_db)):
    db.query(DataAsset).delete()
    db.commit()
    await seed_demo()
    return {"ok": True}


@app.get("/api/v1/demo/profiles")
def demo_profiles():
    return profile_catalog()


@app.post("/api/v1/demo/generate")
async def generate_demo(req: DemoGenerateRequest, db: Session = Depends(get_db)):
    try:
        profile, records = generate_enterprise_assets(req.profile, req.samples, req.seed)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown demo profile: {req.profile}") from exc
    db.query(DataAsset).delete()
    db.commit()
    for record in records:
        asset = DataAsset(**record)
        await enrich_asset(asset, deterministic=True)
        db.add(asset)
    db.commit()
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
    del principal
    if not req.token:
        raise HTTPException(400, "A short-lived connector token is required")
    if connector_type == "github":
        connector = GitHubConnector(req.account, req.token, req.api_url or "https://api.github.com")
    elif connector_type == "gitlab":
        connector = GitLabConnector(req.account, req.token, req.api_url or "https://gitlab.com/api/v4")
    elif connector_type == "sharepoint":
        if not req.site_id or not req.drive_id:
            raise HTTPException(400, "site_id and drive_id are required for SharePoint")
        connector = SharePointConnector(req.site_id, req.drive_id, req.token)
    else:
        raise HTTPException(404, "Supported connector types: github, gitlab, sharepoint")
    try:
        return await ingest_connector(db, connector, req.cursor, req.max_items)
    except Exception as exc:
        raise HTTPException(400, f"{connector_type} scan failed: {exc}") from exc


@app.get("/api/v1/connectors/runs")
def connector_runs(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    del principal
    rows = list(db.scalars(select(ConnectorRun).order_by(ConnectorRun.started_at.desc()).limit(limit)).all())
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
    del principal
    rows = list(
        db.scalars(
            select(ClassificationReview)
            .where(ClassificationReview.status == status)
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
    review = db.get(ClassificationReview, review_id)
    if not review:
        raise HTTPException(404, "Classification review not found")
    asset = db.get(DataAsset, review.asset_id)
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
    review.resolved_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "review_id": review.id, "status": review.status, "asset_id": asset.id}


@app.post("/api/v1/policy/simulate")
def simulate_policy(
    req: PolicySimulationRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    del principal
    asset = db.get(DataAsset, req.asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    agent = db.scalar(select(AIAgent).where(AIAgent.key == req.agent_key))
    if not agent:
        raise HTTPException(404, "AI agent not found")
    result = evaluate_decision(agent, asset, req.destination, req.action, req.purpose)
    return {"simulation": True, "asset_id": asset.id, "agent_key": agent.key, **result}


@app.post("/api/v1/ai-usage/events")
def ingest_ai_usage_event(
    req: AIUsageEventCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    del principal
    existing = db.scalar(select(AIUsageEvent).where(AIUsageEvent.event_id == req.event_id))
    if existing:
        return {"ok": True, "idempotent": True, "event_id": existing.event_id, "decision": existing.decision}
    asset = db.get(DataAsset, req.asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    agent = db.scalar(select(AIAgent).where(AIAgent.key == req.agent_key))
    if not agent:
        raise HTTPException(404, "AI agent not found")
    result = evaluate_decision(agent, asset, req.destination, req.action, req.purpose)
    event = AIUsageEvent(
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
    del principal
    rows = list(db.scalars(select(AIUsageEvent).order_by(AIUsageEvent.occurred_at.desc()).limit(limit)).all())
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
    del principal
    statement = select(GraphEdge).order_by(GraphEdge.created_at.desc())
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
