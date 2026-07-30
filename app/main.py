import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.s3 import scan_bucket
from .classification import classify, heuristic_classify
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .demo_data import DEMO_ASSETS
from .enterprise_demo import PROFILES, generate_enterprise_assets, profile_catalog, represented_count
from .lifecycle import calculate_lifecycle
from .models import DataAsset
from .schemas import AssetOut, DemoGenerateRequest, PolicyDecision, PolicyRequest, S3ScanRequest


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
                await enrich_asset(asset)
                db.add(asset)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.auto_seed_demo:
        await seed_demo()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {"ok": True, "version": "0.1.0", "assets": db.scalar(select(func.count(DataAsset.id)))}


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
    }


@app.post("/api/v1/policy/evaluate", response_model=PolicyDecision)
def evaluate_policy(req: PolicyRequest, db: Session = Depends(get_db)):
    asset = db.get(DataAsset, req.asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    external = req.destination.lower() not in {"internal-rag", "private-model", "bedrock-private"}
    controls = ["audit-log", "identity-context"]
    if asset.ai_access == "Deny":
        decision = "deny"
        reason = asset.ai_access_reason
    elif asset.sensitivity == "Restricted" and external:
        decision = "deny"
        reason = "Restricted data cannot be sent to an unapproved external AI destination."
        controls += ["private-model-only", "redaction-required"]
    elif asset.sensitivity in {"Restricted", "Confidential"}:
        decision = "conditional"
        reason = asset.ai_access_reason
        controls += ["no-training", "redaction", "approved-destination"]
    else:
        decision = "allow"
        reason = asset.ai_access_reason
        controls += ["standard-retention"]
    return PolicyDecision(decision=decision, asset_id=asset.id, destination=req.destination, action=req.action, reason=reason, controls=controls, confidence=asset.classification_confidence)


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
