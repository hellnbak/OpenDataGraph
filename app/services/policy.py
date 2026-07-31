import json
import logging
import time
from threading import RLock

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AIAgent, DataAsset, DecisionAudit, PolicyBundle, PolicyException, utc_now
from app.services.policy_engine import (
    PolicyMatch,
    evaluate_policies,
    evaluate_policy_definitions,
    load_policies,
)


SENSITIVITY = {"Public": 0, "Internal": 1, "Confidential": 2, "Restricted": 3, "Unclassified": 2}
POLICY_VERSION = "1.9.0"
_POLICY_CACHE: dict[tuple[int, str], tuple[float, str, list[dict]]] = {}
_POLICY_CACHE_LOCK = RLock()


def evaluate(
    agent: AIAgent,
    asset: DataAsset,
    destination: str,
    action: str,
    purpose: str,
    db: Session | None = None,
    tenant_id: str = "default",
    policy_definitions: list[dict] | None = None,
    policy_version_override: str | None = None,
) -> dict:
    reasons = []
    controls = ["audit-log", "identity-context", "tenant-context"]
    risk = 20
    external = destination not in {item.strip() for item in agent.allowed_destinations.split(",") if item.strip()}
    destination_type = "public_ai" if external else "approved_private_ai"
    context = {
        "sensitivity": asset.sensitivity,
        "destination_type": destination_type,
        "agent_status": agent.approval_status.lower(),
        "action": action,
        "purpose": purpose,
    }
    if policy_definitions is None:
        policy_matches, policy_version = effective_policy_matches(
            context,
            db,
            tenant_id,
        )
    else:
        policy_matches = evaluate_policy_definitions(context, policy_definitions)
        policy_version = policy_version_override or "candidate"
    for match in policy_matches:
        reasons.append(match.reason)
        controls.extend(match.controls)
        risk = max(risk, match.risk_score)
    if agent.approval_status != "Approved":
        reasons.append("AI agent is not approved for production data access")
        risk += 45
    if SENSITIVITY.get(asset.sensitivity, 2) > SENSITIVITY.get(agent.max_sensitivity, 1):
        reasons.append(f"Asset sensitivity exceeds the agent's approved {agent.max_sensitivity} ceiling")
        risk += 40
    approved_domains = [item.strip() for item in agent.allowed_domains.split(",")]
    if asset.business_domain and agent.allowed_domains and asset.business_domain not in approved_domains:
        reasons.append("Business domain is outside the agent's approved purpose boundary")
        risk += 25
    if external:
        reasons.append("Destination is not on the agent's approved destination list")
        risk += 25
    if asset.public_access and asset.sensitivity in {"Confidential", "Restricted"}:
        reasons.append("Sensitive asset has public exposure")
        risk += 25
    if asset.sensitivity == "Restricted":
        controls += ["redact-direct-identifiers", "private-model-only", "no-training", "retain-decision-logs-30d"]
    elif asset.sensitivity == "Confidential":
        controls += ["redaction", "no-training", "approved-enterprise-endpoint"]
    else:
        controls += ["standard-retention"]
    if action in {"train", "fine-tune"}:
        reasons.append("Training use requires explicit data-owner approval")
        risk += 30
        controls.append("data-owner-approval")
    risk = min(100, risk)
    policy_decision = policy_matches[0].decision if policy_matches else "allow"
    if agent.approval_status != "Approved" or risk >= 80 or policy_decision == "deny":
        decision = "deny"
    elif risk >= 50 or policy_decision == "conditional":
        decision = "conditional"
    else:
        decision = "allow"
    if not reasons:
        reasons = ["Agent, purpose, data sensitivity, and destination are within policy"]
    exception = (
        _matching_exception(
            db,
            tenant_id,
            agent.key,
            asset.id,
            destination,
            action,
            purpose,
            [match.policy_id for match in policy_matches],
        )
        if db and asset.id is not None
        else None
    )
    if exception:
        decision = exception.override_decision
        reasons.append(f"Approved exception: {exception.reason}")
        controls.extend(json.loads(exception.controls_json or "[]"))
    return {
        "decision": decision,
        "risk_score": risk,
        "reasons": list(dict.fromkeys(reasons)),
        "controls": sorted(set(controls)),
        "confidence": min(0.99, max(0.60, asset.classification_confidence)),
        "policy_version": policy_version,
        "expires_in_seconds": 300,
        "matched_policies": [match.policy_id for match in policy_matches],
    }


def effective_policy_matches(
    context: dict,
    db: Session | None,
    tenant_id: str,
) -> tuple[list[PolicyMatch], str]:
    if not db:
        return evaluate_policies(context, settings.policy_directory), POLICY_VERSION
    policies, version = _effective_policy_definitions(db, tenant_id)
    return evaluate_policy_definitions(context, policies), version


def invalidate_policy_cache(tenant_id: str | None = None) -> None:
    with _POLICY_CACHE_LOCK:
        if tenant_id is None:
            _POLICY_CACHE.clear()
        else:
            for key in [key for key in _POLICY_CACHE if key[1] == tenant_id]:
                _POLICY_CACHE.pop(key, None)


def _effective_policy_definitions(
    db: Session,
    tenant_id: str,
) -> tuple[list[dict], str]:
    now = time.monotonic()
    cache_key = (id(db.get_bind()), tenant_id)
    with _POLICY_CACHE_LOCK:
        cached = _POLICY_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[2], cached[1]
    active_bundle = db.scalar(
        select(PolicyBundle)
        .where(
            PolicyBundle.tenant_id == tenant_id,
            PolicyBundle.status == "active",
        )
        .order_by(PolicyBundle.activated_at.desc(), PolicyBundle.id.desc())
        .limit(1)
    )
    if active_bundle:
        definitions = json.loads(active_bundle.definition_json)
        version = f"{active_bundle.name}:v{active_bundle.version}"
    else:
        definitions = load_policies(settings.policy_directory)
        version = POLICY_VERSION
    with _POLICY_CACHE_LOCK:
        _POLICY_CACHE[cache_key] = (
            now + max(0, settings.policy_cache_seconds),
            version,
            definitions,
        )
    return definitions, version


def _matching_exception(
    db: Session,
    tenant_id: str,
    agent_key: str,
    asset_id: int,
    destination: str,
    action: str,
    purpose: str,
    matched_policy_ids: list[str],
) -> PolicyException | None:
    policy_scope = PolicyException.policy_id.is_(None)
    if matched_policy_ids:
        policy_scope = or_(
            policy_scope,
            PolicyException.policy_id.in_(matched_policy_ids),
        )
    candidates = db.scalars(
        select(PolicyException).where(
            PolicyException.tenant_id == tenant_id,
            PolicyException.active.is_(True),
            PolicyException.expires_at > utc_now(),
            policy_scope,
            or_(
                PolicyException.agent_key.is_(None),
                PolicyException.agent_key == agent_key,
            ),
            or_(
                PolicyException.asset_id.is_(None),
                PolicyException.asset_id == asset_id,
            ),
            or_(
                PolicyException.destination.is_(None),
                PolicyException.destination == destination,
            ),
            or_(
                PolicyException.action.is_(None),
                PolicyException.action == action,
            ),
            or_(
                PolicyException.purpose.is_(None),
                PolicyException.purpose == purpose,
            ),
        )
    )
    for exception in candidates:
        if exception.policy_id and exception.policy_id not in matched_policy_ids:
            continue
        if exception.agent_key and exception.agent_key != agent_key:
            continue
        if exception.asset_id and exception.asset_id != asset_id:
            continue
        if exception.destination and exception.destination != destination:
            continue
        if exception.action and exception.action != action:
            continue
        if exception.purpose and exception.purpose != purpose:
            continue
        return exception
    return None


def audit(db, req, result, tenant_id: str = "default"):
    row = DecisionAudit(
        tenant_id=tenant_id,
        agent_key=req.agent_key,
        asset_id=req.asset_id,
        action=req.action,
        destination=req.destination,
        purpose=req.purpose,
        decision=result["decision"],
        risk_score=result["risk_score"],
        policy_version=result["policy_version"],
        reasons_json=json.dumps(result["reasons"]),
        controls_json=json.dumps(result["controls"]),
    )
    db.add(row)
    db.commit()
    try:
        from app.services.integrations import queue_integration_event

        queue_integration_event(
            db,
            tenant_id,
            "policy.decision",
            {
                "audit_id": row.id,
                "decision": result["decision"],
                "risk_score": result["risk_score"],
                "policy_version": result["policy_version"],
                "matched_policies": result["matched_policies"],
                "agent_key": req.agent_key,
                "asset_id": req.asset_id,
                "action": req.action,
                "destination": req.destination,
                "purpose": req.purpose,
            },
            created_by="policy-engine",
        )
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("failed to queue policy integration delivery")
    return row
