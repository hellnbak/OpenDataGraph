import json
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal, require_role
from app.config import settings
from app.database import get_db
from app.models import (
    DataAsset,
    EnforcementEvent,
    GenAITelemetryEvent,
    GovernanceOutboxEvent,
    PolicyReplay,
    PolicyRollout,
    RuntimeDecisionReceipt,
)
from app.schemas import (
    AuthZENActionSearchRequest,
    AuthZENEvaluationRequest,
    AuthZENResourceSearchRequest,
    AuthZENSubjectSearchRequest,
    EnforcementEventCreate,
    GovernanceFrameworkCoverageRequest,
    PolicyReplayCreate,
    PolicyRolloutAdvance,
    PolicyRolloutCreate,
)
from app.services.authzen_search import search_actions, search_resources, search_subjects
from app.services.enforcement import EnforcementConflict, enforcement_response, record_enforcement_event
from app.services.genai_telemetry import ingest_otlp_genai, telemetry_response
from app.services.governance_frameworks import framework_coverage, list_frameworks
from app.services.outbox import dispatch_outbox_events, outbox_response
from app.services.policy_rollouts import (
    advance_rollout,
    create_rollout,
    replay_response,
    replay_rollout,
    rollout_response,
)
from app.services.runtime_authorization import evaluate_access, receipt_response


router = APIRouter()
MCP_PROTOCOL_VERSION = "2026-07-28"


@router.post("/access/v1/search/subject")
def authzen_subject_search(
    req: AuthZENSubjectSearchRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    return _authzen_search(search_subjects, db, principal.tenant_id, req)


@router.post("/access/v1/search/resource")
def authzen_resource_search(
    req: AuthZENResourceSearchRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    return _authzen_search(search_resources, db, principal.tenant_id, req)


@router.post("/access/v1/search/action")
def authzen_action_search(
    req: AuthZENActionSearchRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    return _authzen_search(search_actions, db, principal.tenant_id, req)


@router.post("/api/v1/runtime/enforcement-events", status_code=201)
def create_enforcement_event(
    req: EnforcementEventCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    try:
        event, idempotent = record_enforcement_event(
            db,
            principal.tenant_id,
            req.model_dump(),
            principal.subject,
        )
    except EnforcementConflict as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Enforcement event already exists") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    return {"idempotent": idempotent, **enforcement_response(event)}


@router.get("/api/v1/runtime/enforcement-events")
def list_enforcement_events(
    receipt_id: str | None = Query(default=None, max_length=36),
    outcome: str | None = Query(default=None, pattern="^(applied|rejected|failed)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(EnforcementEvent).where(EnforcementEvent.tenant_id == principal.tenant_id)
    if receipt_id:
        statement = statement.where(EnforcementEvent.receipt_id == receipt_id)
    if outcome:
        statement = statement.where(EnforcementEvent.outcome == outcome)
    rows = db.scalars(statement.order_by(EnforcementEvent.occurred_at.desc()).limit(limit))
    return [enforcement_response(row) for row in rows]


@router.post("/api/v1/policy/rollouts", status_code=201)
def create_policy_rollout(
    req: PolicyRolloutCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    try:
        return rollout_response(
            create_rollout(db, principal.tenant_id, req.model_dump(), principal.subject)
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Policy rollout already exists") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/v1/policy/rollouts")
def list_policy_rollouts(
    status: str | None = Query(default=None, pattern="^(active|completed)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(PolicyRollout).where(PolicyRollout.tenant_id == principal.tenant_id)
    if status:
        statement = statement.where(PolicyRollout.status == status)
    rows = db.scalars(statement.order_by(PolicyRollout.updated_at.desc()).limit(limit))
    return [rollout_response(row) for row in rows]


@router.get("/api/v1/policy/rollouts/{rollout_id}")
def get_policy_rollout(
    rollout_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    rollout = _rollout(db, principal.tenant_id, rollout_id)
    if not rollout:
        raise HTTPException(404, "Policy rollout not found")
    return rollout_response(rollout)


@router.post("/api/v1/policy/rollouts/{rollout_id}/advance")
def advance_policy_rollout(
    rollout_id: str,
    req: PolicyRolloutAdvance,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    rollout = _rollout(db, principal.tenant_id, rollout_id)
    if not rollout:
        raise HTTPException(404, "Policy rollout not found")
    try:
        return rollout_response(
            advance_rollout(db, rollout, req.stage, req.traffic_percentage, principal.subject)
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/v1/policy/rollouts/{rollout_id}/replays", status_code=201)
def create_policy_replay(
    rollout_id: str,
    req: PolicyReplayCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    rollout = _rollout(db, principal.tenant_id, rollout_id)
    if not rollout:
        raise HTTPException(404, "Policy rollout not found")
    try:
        return replay_response(replay_rollout(db, rollout, req.limit, principal.subject))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/v1/policy/rollouts/{rollout_id}/replays")
def list_policy_replays(
    rollout_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    if not _rollout(db, principal.tenant_id, rollout_id):
        raise HTTPException(404, "Policy rollout not found")
    rows = db.scalars(
        select(PolicyReplay)
        .where(PolicyReplay.tenant_id == principal.tenant_id, PolicyReplay.rollout_id == rollout_id)
        .order_by(PolicyReplay.created_at.desc())
        .limit(limit)
    )
    return [replay_response(row) for row in rows]


@router.post("/v1/traces")
@router.post("/api/v1/telemetry/genai/otlp")
def ingest_genai_traces(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("analyst")),
):
    try:
        return ingest_otlp_genai(db, principal.tenant_id, payload, principal.subject)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Telemetry event conflicts with existing data") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/v1/telemetry/genai/events")
def list_genai_events(
    agent_key: str | None = Query(default=None, max_length=320),
    model: str | None = Query(default=None, max_length=320),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(GenAITelemetryEvent).where(GenAITelemetryEvent.tenant_id == principal.tenant_id)
    if agent_key:
        statement = statement.where(GenAITelemetryEvent.agent_key == agent_key)
    if model:
        statement = statement.where(GenAITelemetryEvent.model == model)
    rows = db.scalars(statement.order_by(GenAITelemetryEvent.occurred_at.desc()).limit(limit))
    return [telemetry_response(row) for row in rows]


@router.get("/api/v1/integrations/outbox")
def list_governance_outbox(
    status: str | None = Query(default=None, pattern="^(pending|dispatching|dispatched|failed)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    statement = select(GovernanceOutboxEvent).where(GovernanceOutboxEvent.tenant_id == principal.tenant_id)
    if status:
        statement = statement.where(GovernanceOutboxEvent.status == status)
    rows = db.scalars(statement.order_by(GovernanceOutboxEvent.created_at.desc()).limit(limit))
    return [outbox_response(row) for row in rows]


@router.post("/api/v1/integrations/outbox/dispatch")
def dispatch_governance_outbox(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("administrator")),
):
    return dispatch_outbox_events(db, limit, principal.tenant_id)


@router.get("/api/v1/governance/frameworks")
def governance_frameworks(
    _principal: Principal = Depends(require_role("read-only")),
):
    return list_frameworks()


@router.post("/api/v1/governance/frameworks/{framework_id}/coverage")
def governance_framework_report(
    framework_id: str,
    req: GovernanceFrameworkCoverageRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role("auditor")),
):
    try:
        return framework_coverage(db, principal.tenant_id, framework_id, req.days)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


def remote_mcp_principal(
    authorization: str | None = Header(default=None),
    principal: Principal = Depends(require_role("analyst")),
) -> Principal:
    if not settings.remote_mcp_enabled:
        raise HTTPException(404, "Remote MCP gateway is disabled")
    if not settings.auth_disabled and not (authorization or "").lower().startswith("bearer "):
        raise HTTPException(401, "Remote MCP requires an OIDC Bearer token")
    return principal


@router.post("/mcp")
def remote_mcp(
    request: Request,
    payload: dict = Body(...),
    protocol_version: str | None = Header(default=None, alias="MCP-Protocol-Version"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(remote_mcp_principal),
):
    if protocol_version != MCP_PROTOCOL_VERSION:
        raise HTTPException(400, f"MCP-Protocol-Version must be {MCP_PROTOCOL_VERSION}")
    if len(json.dumps(payload, separators=(",", ":")).encode()) > 256 * 1024:
        raise HTTPException(400, "MCP request exceeds 256 KiB")
    request_id = payload.get("id")
    method = payload.get("method")
    try:
        result = _mcp_result(db, principal, method, payload.get("params", {}), request_id)
        body = {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (ValueError, KeyError) as exc:
        db.rollback()
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": str(exc)},
        }
    return JSONResponse(
        body,
        headers={
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            "Mcp-Method": str(method or ""),
            "Mcp-Name": "OpenDataGraph",
            "Cache-Control": f"private, max-age={max(0, settings.remote_mcp_tool_ttl_ms // 1000)}",
        },
    )


def _authzen_search(handler, db: Session, tenant_id: str, req):
    try:
        return handler(db, tenant_id, req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _rollout(db: Session, tenant_id: str, rollout_id: str) -> PolicyRollout | None:
    return db.scalar(
        select(PolicyRollout).where(
            PolicyRollout.tenant_id == tenant_id,
            PolicyRollout.rollout_id == rollout_id,
        )
    )


def _mcp_result(db: Session, principal: Principal, method: str, params: dict, request_id) -> dict:
    if method == "server/discover":
        return {
            "name": "OpenDataGraph",
            "version": settings.version,
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "stateless": True,
            "capabilities": {"tools": {"listChanged": False}},
            "ttl": settings.remote_mcp_tool_ttl_ms,
        }
    if method == "tools/list":
        return {"tools": _mcp_tools()}
    if method != "tools/call":
        raise ValueError("Unsupported MCP method")
    if not isinstance(params, dict) or not isinstance(params.get("arguments", {}), dict):
        raise ValueError("MCP tool arguments must be an object")
    result = _mcp_tool_call(db, principal, params.get("name"), params.get("arguments", {}), request_id)
    return {
        "content": [{"type": "text", "text": json.dumps(result, default=str, separators=(",", ":"))}],
        "structuredContent": result,
        "isError": False,
    }


def _mcp_tools() -> list[dict]:
    return [
        {
            "name": "authorize_runtime_access",
            "description": "Evaluate governed runtime access and return obligations plus a durable receipt.",
            "inputSchema": {
                "type": "object",
                "required": ["resource_type", "resource_id", "action"],
                "properties": {
                    "resource_type": {"type": "string"},
                    "resource_id": {"type": "string"},
                    "action": {"type": "string"},
                    "destination": {"type": "string"},
                    "purpose": {"type": "string"},
                },
            },
        },
        {
            "name": "get_data_asset",
            "description": "Get metadata, classification, ownership, and AI posture for one data asset.",
            "inputSchema": {
                "type": "object",
                "required": ["asset_id"],
                "properties": {"asset_id": {"type": "integer", "minimum": 1}},
            },
        },
        {
            "name": "list_runtime_decision_receipts",
            "description": "List recent tenant-scoped runtime authorization receipts.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            },
        },
    ]


def _mcp_tool_call(db: Session, principal: Principal, name: str, arguments: dict, request_id):
    if name == "authorize_runtime_access":
        agent_key = settings.remote_mcp_default_agent_key
        if not agent_key:
            raise ValueError("ODG_REMOTE_MCP_DEFAULT_AGENT_KEY must be configured")
        evaluation = AuthZENEvaluationRequest.model_validate(
            {
                "subject": {"type": "ai_agent", "id": agent_key},
                "resource": {
                    "type": str(arguments["resource_type"]),
                    "id": str(arguments["resource_id"]),
                },
                "action": {"name": str(arguments["action"])},
                "context": {
                    "destination": str(arguments.get("destination", "internal-rag")),
                    "purpose": str(arguments.get("purpose", "mcp-runtime-access")),
                    "protocol": "mcp",
                },
            }
        )
        result, _receipt, _idempotent = evaluate_access(
            db,
            principal.tenant_id,
            evaluation,
            str(request_id or uuid4())[:160],
            None,
        )
        db.commit()
        return result
    if name == "get_data_asset":
        asset_id = int(arguments["asset_id"])
        asset = db.scalar(
            select(DataAsset).where(DataAsset.tenant_id == principal.tenant_id, DataAsset.id == asset_id)
        )
        if not asset:
            raise ValueError("Data asset not found")
        return {
            "id": asset.id,
            "external_id": asset.external_id,
            "name": asset.name,
            "source": asset.source,
            "owner": asset.owner,
            "business_domain": asset.business_domain,
            "sensitivity": asset.sensitivity,
            "lifecycle_state": asset.lifecycle_state,
            "ai_access": asset.ai_access,
            "ai_access_reason": asset.ai_access_reason,
        }
    if name == "list_runtime_decision_receipts":
        limit = min(max(1, int(arguments.get("limit", 25))), 100)
        rows = db.scalars(
            select(RuntimeDecisionReceipt)
            .where(RuntimeDecisionReceipt.tenant_id == principal.tenant_id)
            .order_by(RuntimeDecisionReceipt.created_at.desc())
            .limit(limit)
        )
        return {"receipts": [receipt_response(row) for row in rows]}
    raise ValueError("Unknown MCP tool")
