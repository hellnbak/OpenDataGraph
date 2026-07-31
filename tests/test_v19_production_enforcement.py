import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import (
    AIAgent,
    AILineageObservation,
    AIResource,
    DataAsset,
    EnforcementEvent,
    GenAITelemetryEvent,
    GovernanceOutboxEvent,
    PolicyBundle,
)
from app.services.policy import invalidate_policy_cache
from app.services.outbox import queue_outbox_event
from sdks.python.opendatagraph_enforcement import EnforcementDenied, OpenDataGraphPEP


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed(db):
    agent = AIAgent(
        tenant_id="default",
        key="fleet-agent",
        name="Fleet Agent",
        owner="security@example.test",
        business_purpose="Synthetic governed runtime tests",
        framework="mcp",
        models="private-model",
        allowed_domains="Finance",
        max_sensitivity="Restricted",
        allowed_destinations="internal-rag,private-model",
        approval_status="Approved",
        risk_level="Medium",
    )
    asset = DataAsset(
        tenant_id="default",
        source="postgresql",
        source_account="catalog",
        external_id="dataset://finance/accounts",
        name="accounts",
        path="postgresql://catalog/finance/accounts",
        owner="finance@example.test",
        business_domain="Finance",
        sensitivity="Restricted",
        classification_confidence=0.99,
    )
    db.add_all([agent, asset])
    db.commit()
    db.refresh(asset)
    return asset


@pytest.fixture()
def v19_client(monkeypatch):
    session_factory = _session_factory()
    with session_factory() as db:
        asset = _seed(db)

    def override_db():
        with session_factory() as db:
            yield db

    monkeypatch.setattr(settings, "auth_disabled", True)
    monkeypatch.setattr(settings, "runtime_authorization_mode", "enforce")
    monkeypatch.setattr(settings, "runtime_receipt_signing_profile", "")
    monkeypatch.setattr(settings, "policy_cache_seconds", 0)
    monkeypatch.setattr(settings, "policy_rollout_cache_seconds", 0)
    monkeypatch.setattr(settings, "authzen_search_max", 100)
    monkeypatch.setattr(settings, "remote_mcp_enabled", True)
    monkeypatch.setattr(settings, "remote_mcp_default_agent_key", "fleet-agent")
    invalidate_policy_cache()
    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app), session_factory, asset
    finally:
        app.dependency_overrides.clear()
        invalidate_policy_cache()


def _evaluation(asset_id: int) -> dict:
    return {
        "subject": {"type": "ai_agent", "id": "fleet-agent"},
        "resource": {"type": "data_asset", "id": str(asset_id)},
        "action": {"name": "send"},
        "context": {"destination": "internal-rag", "purpose": "fraud-review"},
    }


def test_authzen_search_and_enforcement_evidence(v19_client):
    client, session_factory, asset = v19_client
    search = client.post(
        "/access/v1/search/resource",
        json={
            "subject": {"type": "ai_agent", "id": "fleet-agent"},
            "action": {"name": "send"},
            "resource": {"type": "data_asset"},
            "context": {"destination": "internal-rag", "purpose": "fraud-review"},
            "page": {"limit": 10},
        },
    )
    assert search.status_code == 200
    assert search.json()["results"] == [
        {"type": "data_asset", "id": "dataset://finance/accounts"}
    ]

    decision = client.post("/access/v1/evaluation", json=_evaluation(asset.id))
    assert decision.status_code == 200
    assert decision.json()["decision"] is True
    context = decision.json()["context"]
    receipt = client.get(
        f"/api/v1/runtime/decision-receipts/{context['receipt']['id']}"
    )
    assert receipt.json()["manifest"]["version"] == 2
    event = {
        "event_id": "enforcement-1",
        "receipt_id": context["receipt"]["id"],
        "pep_id": "payments-api",
        "outcome": "applied",
        "satisfied_obligations": [item["id"] for item in context["obligations"]],
        "metadata": {"deployment": "synthetic-test"},
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    created = client.post("/api/v1/runtime/enforcement-events", json=event)
    assert created.status_code == 201
    assert created.json()["idempotent"] is False
    repeated = client.post("/api/v1/runtime/enforcement-events", json=event)
    assert repeated.status_code == 201
    assert repeated.json()["idempotent"] is True
    forbidden = client.post(
        "/api/v1/runtime/enforcement-events",
        json={**event, "event_id": "enforcement-2", "metadata": {"prompt": "not-allowed"}},
    )
    assert forbidden.status_code == 400
    with session_factory() as db:
        assert db.scalar(select(func.count(EnforcementEvent.id))) == 1
        assert db.scalar(select(func.count(GovernanceOutboxEvent.id))) == 2


def test_policy_rollout_replay_shadow_and_promotion(v19_client):
    client, session_factory, asset = v19_client
    baseline = client.post("/access/v1/evaluation", json=_evaluation(asset.id))
    assert baseline.status_code == 200
    assert baseline.json()["context"]["policy_decision"] != "deny"
    with session_factory() as db:
        db.add(
            PolicyBundle(
                tenant_id="default",
                bundle_id="candidate-bundle",
                name="fleet-policy",
                version=2,
                status="approved",
                definition_json=json.dumps(
                    [
                        {
                            "id": "deny-send",
                            "version": "2",
                            "match": {"action": "send"},
                            "decision": "deny",
                            "risk_score": 99,
                            "reason": "Synthetic rollout denial",
                            "controls": ["block-request"],
                        }
                    ]
                ),
                created_by="administrator",
                approved_by="administrator",
            )
        )
        db.commit()

    rollout = client.post(
        "/api/v1/policy/rollouts",
        json={"bundle_id": "candidate-bundle", "stage": "shadow", "replay_limit": 10},
    )
    assert rollout.status_code == 201
    rollout_id = rollout.json()["rollout_id"]
    replay = client.post(f"/api/v1/policy/rollouts/{rollout_id}/replays", json={})
    assert replay.status_code == 201
    assert replay.json()["evaluated"] == 1
    assert replay.json()["newly_denied"] == 1

    shadow = client.post("/access/v1/evaluation", json=_evaluation(asset.id))
    assert shadow.status_code == 200
    assert shadow.json()["decision"] is True
    assert shadow.json()["context"]["rollout"]["candidate_policy_decision"] == "deny"
    canary = client.post(
        f"/api/v1/policy/rollouts/{rollout_id}/advance",
        json={"stage": "canary", "traffic_percentage": 25},
    )
    assert canary.status_code == 200
    assert canary.json()["traffic_percentage"] == 25
    enforced = client.post(
        f"/api/v1/policy/rollouts/{rollout_id}/advance",
        json={"stage": "enforce"},
    )
    assert enforced.status_code == 200
    assert enforced.json()["status"] == "completed"


def test_metadata_only_otel_discovery_mcp_and_framework(v19_client):
    client, session_factory, asset = v19_client
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "synthetic-api"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "a" * 32,
                                "spanId": "b" * 16,
                                "name": "chat synthetic-model",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000000125000000",
                                "attributes": [
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                                    {"key": "gen_ai.provider.name", "value": {"stringValue": "synthetic"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "synthetic-model"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "12"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "5"}},
                                    {"key": "opendatagraph.agent.key", "value": {"stringValue": "fleet-agent"}},
                                    {"key": "gen_ai.input.messages", "value": {"stringValue": "must-not-persist"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    ingested = client.post("/v1/traces", json=payload)
    assert ingested.status_code == 200
    assert ingested.json() == {
        "accepted": True,
        "imported": 1,
        "duplicates": 0,
        "ignored": 0,
        "models_discovered": 1,
        "relationships_observed": 1,
        "content_discarded": 1,
    }
    duplicate = client.post("/v1/traces", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicates"] == 1
    with session_factory() as db:
        event = db.scalar(select(GenAITelemetryEvent))
        assert event.content_discarded is True
        resource = db.scalar(select(AIResource).where(AIResource.name == "synthetic-model"))
        assert resource.status == "review"
        assert "must-not-persist" not in resource.metadata_json
        assert db.scalar(select(func.count(AILineageObservation.id))) == 1

    protocol_headers = {"MCP-Protocol-Version": "2026-07-28"}
    discovery = client.post(
        "/mcp",
        headers=protocol_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}},
    )
    assert discovery.status_code == 200
    assert discovery.json()["result"]["stateless"] is True
    asset_result = client.post(
        "/mcp",
        headers=protocol_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_data_asset", "arguments": {"asset_id": asset.id}},
        },
    )
    assert asset_result.json()["result"]["structuredContent"]["sensitivity"] == "Restricted"

    coverage = client.post(
        "/api/v1/governance/frameworks/nist-ai-rmf-1.0/coverage",
        json={"days": 30},
    )
    assert coverage.status_code == 200
    assert coverage.json()["summary"]["controls"] == 6
    assert "do not certify compliance" in coverage.json()["disclaimer"]


def test_outbox_dispatch_and_python_sdk_fail_closed(v19_client):
    client, session_factory, asset = v19_client
    assert client.post("/access/v1/evaluation", json=_evaluation(asset.id)).status_code == 200
    with session_factory() as db:
        queue_outbox_event(
            db,
            "other-tenant",
            "synthetic",
            "other-1",
            "synthetic.other",
            {"value": "metadata-only"},
        )
        db.commit()
    dispatched = client.post("/api/v1/integrations/outbox/dispatch?limit=10")
    assert dispatched.status_code == 200
    assert dispatched.json()["dispatched"] >= 1
    with session_factory() as db:
        other = db.scalar(
            select(GovernanceOutboxEvent).where(
                GovernanceOutboxEvent.tenant_id == "other-tenant"
            )
        )
        assert other.status == "pending"

    pep = OpenDataGraphPEP("https://governance.example.test", "synthetic-pep")
    reports = []
    pep._request = lambda path, payload, headers=None: reports.append((path, payload)) or {}
    decision = {
        "decision": True,
        "context": {
            "receipt": {"id": "receipt-1"},
            "obligations": [{"id": "audit-log", "required": True}],
        },
    }
    with pytest.raises(EnforcementDenied):
        pep.enforce(decision, lambda: "must-not-run")
    assert reports[-1][1]["outcome"] == "failed"
    pep.register_obligation("audit-log", lambda _parameters, _decision: None)
    assert pep.enforce(decision, lambda: "ok") == "ok"
    assert reports[-1][1]["outcome"] == "applied"
