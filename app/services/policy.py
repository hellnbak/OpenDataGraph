import json
from datetime import datetime
from app.models import AIAgent, DataAsset, DecisionAudit

SENSITIVITY={"Public":0,"Internal":1,"Confidential":2,"Restricted":3,"Unclassified":2}
POLICY_VERSION="2026.07.2"

def evaluate(agent:AIAgent, asset:DataAsset, destination:str, action:str, purpose:str):
    reasons=[]; controls=["audit-log","identity-context"]; risk=20
    external=destination not in {x.strip() for x in agent.allowed_destinations.split(',') if x.strip()}
    if agent.approval_status != "Approved": reasons.append("AI agent is not approved for production data access"); risk+=45
    if SENSITIVITY.get(asset.sensitivity,2)>SENSITIVITY.get(agent.max_sensitivity,1): reasons.append(f"Asset sensitivity exceeds the agent's approved {agent.max_sensitivity} ceiling"); risk+=40
    if asset.business_domain and agent.allowed_domains and asset.business_domain not in [x.strip() for x in agent.allowed_domains.split(',')]: reasons.append("Business domain is outside the agent's approved purpose boundary"); risk+=25
    if external: reasons.append("Destination is not on the agent's approved destination list"); risk+=25
    if asset.public_access and asset.sensitivity in {"Confidential","Restricted"}: reasons.append("Sensitive asset has public exposure"); risk+=25
    if asset.sensitivity=="Restricted": controls += ["redact-direct-identifiers","private-model-only","no-training","retain-decision-logs-30d"]
    elif asset.sensitivity=="Confidential": controls += ["redaction","no-training","approved-enterprise-endpoint"]
    else: controls += ["standard-retention"]
    if action in {"train","fine-tune"}: reasons.append("Training use requires explicit data-owner approval"); risk+=30; controls.append("data-owner-approval")
    risk=min(100,risk)
    if agent.approval_status!="Approved" or risk>=80: decision="deny"
    elif risk>=50: decision="conditional"
    else: decision="allow"
    if not reasons: reasons=["Agent, purpose, data sensitivity, and destination are within policy"]
    return {"decision":decision,"risk_score":risk,"reasons":reasons,"controls":sorted(set(controls)),"confidence":min(.99,max(.60,asset.classification_confidence)),"policy_version":POLICY_VERSION,"expires_in_seconds":300}

def audit(db, req, result):
    row=DecisionAudit(agent_key=req.agent_key,asset_id=req.asset_id,action=req.action,destination=req.destination,purpose=req.purpose,decision=result["decision"],risk_score=result["risk_score"],policy_version=result["policy_version"],reasons_json=json.dumps(result["reasons"]),controls_json=json.dumps(result["controls"])); db.add(row); db.commit(); return row
