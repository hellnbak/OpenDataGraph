from datetime import timedelta
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AIAgent,
    AILineageObservation,
    AIResource,
    EnforcementEvent,
    GenAITelemetryEvent,
    PolicyBundle,
    PolicyRollout,
    RuntimeDecisionReceipt,
    utc_now,
)


FRAMEWORK_DIRECTORY = Path(__file__).resolve().parents[2] / "policies" / "frameworks"
EVIDENCE_MODELS = {
    "ai_agents": (AIAgent, None),
    "ai_lineage": (AILineageObservation, AILineageObservation.recorded_at),
    "ai_resources": (AIResource, AIResource.created_at),
    "enforcement_events": (EnforcementEvent, EnforcementEvent.occurred_at),
    "genai_telemetry": (GenAITelemetryEvent, GenAITelemetryEvent.occurred_at),
    "policy_bundles": (PolicyBundle, PolicyBundle.created_at),
    "policy_rollouts": (PolicyRollout, PolicyRollout.created_at),
    "runtime_receipts": (RuntimeDecisionReceipt, RuntimeDecisionReceipt.created_at),
}


def list_frameworks() -> list[dict]:
    return [
        {
            "id": framework["id"],
            "title": framework["title"],
            "source": framework.get("source", ""),
            "control_count": len(framework.get("controls", [])),
            "disclaimer": framework["disclaimer"],
        }
        for framework in _frameworks()
    ]


def framework_coverage(
    db: Session,
    tenant_id: str,
    framework_id: str,
    days: int,
) -> dict:
    framework = next((item for item in _frameworks() if item["id"] == framework_id), None)
    if not framework:
        raise ValueError("Governance framework not found")
    since = utc_now() - timedelta(days=days)
    evidence_counts = {}
    for evidence_type in {
        item
        for control in framework.get("controls", [])
        for item in control.get("evidence_types", [])
    }:
        model_config = EVIDENCE_MODELS.get(evidence_type)
        if not model_config:
            evidence_counts[evidence_type] = 0
            continue
        model, timestamp = model_config
        statement = select(func.count(model.id)).where(model.tenant_id == tenant_id)
        if timestamp is not None:
            statement = statement.where(timestamp >= since)
        evidence_counts[evidence_type] = db.scalar(statement) or 0
    controls = []
    for control in framework.get("controls", []):
        evidence = [
            {"type": item, "count": evidence_counts.get(item, 0)}
            for item in control.get("evidence_types", [])
        ]
        evidenced = all(item["count"] > 0 for item in evidence)
        controls.append(
            {
                "id": control["id"],
                "function": control["function"],
                "title": control["title"],
                "status": "evidenced" if evidenced else "gap",
                "evidence": evidence,
            }
        )
    evidenced_count = sum(item["status"] == "evidenced" for item in controls)
    return {
        "framework": {
            "id": framework["id"],
            "title": framework["title"],
            "source": framework.get("source", ""),
        },
        "window_days": days,
        "generated_at": utc_now(),
        "summary": {
            "controls": len(controls),
            "evidenced": evidenced_count,
            "gaps": len(controls) - evidenced_count,
            "coverage_percentage": round(100 * evidenced_count / len(controls), 1) if controls else 0.0,
        },
        "controls": controls,
        "disclaimer": framework["disclaimer"],
    }


def _frameworks() -> list[dict]:
    frameworks = []
    for path in sorted(FRAMEWORK_DIRECTORY.glob("*.yaml")):
        with path.open(encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
        if isinstance(value, dict) and value.get("id") and isinstance(value.get("controls"), list):
            frameworks.append(value)
    return frameworks
