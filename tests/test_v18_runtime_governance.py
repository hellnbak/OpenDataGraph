import json
from datetime import timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import AIAgent, DataAsset, RuntimeDecisionReceipt, utc_now
from app.schemas import AuthZENEvaluationRequest
from app.services.policy import invalidate_policy_cache
from app.services.runtime_authorization import (
    evaluate_access,
    process_pending_receipts,
    purge_expired_receipts,
    verify_receipt,
)


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed(db, tenant_id="default"):
    agent = AIAgent(
        tenant_id=tenant_id,
        key="runtime-agent",
        name="Runtime Agent",
        owner="security@example.test",
        business_purpose="Governed runtime access",
        framework="mcp",
        models="private-model",
        allowed_domains="Finance",
        max_sensitivity="Restricted",
        allowed_destinations="internal-rag,private-model",
        approval_status="Approved",
        risk_level="Medium",
    )
    asset = DataAsset(
        tenant_id=tenant_id,
        source="postgresql",
        source_account="catalog",
        external_id="dataset://finance/customers",
        name="customers",
        path="postgresql://catalog/finance/customers",
        business_domain="Finance",
        sensitivity="Restricted",
        classification_confidence=0.99,
    )
    db.add_all([agent, asset])
    db.commit()
    db.refresh(asset)
    return agent, asset


def test_authzen_evaluation_receipts_and_batch_semantics(monkeypatch):
    session_factory = _session_factory()
    with session_factory() as db:
        _agent, asset = _seed(db)

    def override_db():
        with session_factory() as db:
            yield db

    monkeypatch.setattr(settings, "auth_disabled", True)
    monkeypatch.setattr(settings, "runtime_authorization_mode", "enforce")
    monkeypatch.setattr(settings, "runtime_receipt_signing_profile", "")
    monkeypatch.setattr(settings, "runtime_authorization_batch_max", 10)
    monkeypatch.setattr(settings, "policy_cache_seconds", 0)
    invalidate_policy_cache()
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    payload = {
        "subject": {
            "type": "ai_agent",
            "id": "runtime-agent",
            "properties": {"session": "metadata-only"},
        },
        "resource": {
            "type": "data_asset",
            "id": str(asset.id),
            "properties": {"sensitivity": "Restricted"},
        },
        "action": {"name": "send"},
        "context": {
            "destination": "public-ai",
            "purpose": "summarization",
        },
    }
    try:
        metadata = client.get("/.well-known/authzen-configuration")
        assert metadata.status_code == 200
        assert metadata.json()["access_evaluation_endpoint"].endswith(
            "/access/v1/evaluation"
        )

        first = client.post(
            "/access/v1/evaluation",
            headers={"X-Request-ID": "request-1", "Idempotency-Key": "decision-1"},
            json=payload,
        )
        assert first.status_code == 200
        assert first.json()["decision"] is False
        assert first.json()["context"]["policy_decision"] == "deny"
        receipt_id = first.json()["context"]["receipt"]["id"]

        repeated = client.post(
            "/access/v1/evaluation",
            headers={"X-Request-ID": "request-1", "Idempotency-Key": "decision-1"},
            json=payload,
        )
        assert repeated.status_code == 200
        assert repeated.json()["context"]["receipt"]["id"] == receipt_id

        changed = json.loads(json.dumps(payload))
        changed["context"]["destination"] = "internal-rag"
        assert (
            client.post(
                "/access/v1/evaluation",
                headers={"Idempotency-Key": "decision-1"},
                json=changed,
            ).status_code
            == 409
        )

        receipt = client.get(
            f"/api/v1/runtime/decision-receipts/{receipt_id}"
        ).json()
        assert receipt["manifest"]["subject"]["properties_sha256"]
        assert "session" not in receipt["manifest"]["subject"]
        assert receipt["signing_status"] == "unsigned"
        verified = client.post(
            f"/api/v1/runtime/decision-receipts/{receipt_id}/verify",
            json={},
        ).json()
        assert verified["valid"] is True
        assert verified["stored_digest_valid"] is True

        batch = client.post(
            "/access/v1/evaluations",
            headers={"Idempotency-Key": "batch-1"},
            json={
                "subject": payload["subject"],
                "resource": payload["resource"],
                "action": payload["action"],
                "options": {"evaluations_semantic": "deny_on_first_deny"},
                "evaluations": [
                    {
                        "context": {
                            "destination": "internal-rag",
                            "purpose": "summarization",
                        }
                    },
                    {"context": payload["context"]},
                    {
                        "context": {
                            "destination": "private-model",
                            "purpose": "summarization",
                        }
                    },
                ],
            },
        )
        assert batch.status_code == 200
        assert [item["decision"] for item in batch.json()["evaluations"]] == [
            True,
            False,
        ]
        with session_factory() as db:
            assert db.scalar(select(func.count(RuntimeDecisionReceipt.id))) == 3
        analytics = client.get("/api/v1/governance/analytics?days=30").json()
        assert analytics["runtime_authorization"]["decisions"] == {
            "false": 2,
            "true": 1,
        }
    finally:
        app.dependency_overrides.clear()
        invalidate_policy_cache()


def test_warn_mode_preserves_policy_denial_in_permitted_receipt(monkeypatch):
    session_factory = _session_factory()
    monkeypatch.setattr(settings, "runtime_authorization_mode", "warn")
    monkeypatch.setattr(settings, "runtime_receipt_signing_profile", "")
    monkeypatch.setattr(settings, "policy_cache_seconds", 0)
    invalidate_policy_cache()
    with session_factory() as db:
        _agent, asset = _seed(db, "tenant-a")
        request = AuthZENEvaluationRequest.model_validate(
            {
                "subject": {"type": "ai_agent", "id": "runtime-agent"},
                "resource": {"type": "data_asset", "id": str(asset.id)},
                "action": {"name": "send"},
                "context": {
                    "destination": "public-ai",
                    "purpose": "summarization",
                },
            }
        )
        response, receipt, _idempotent = evaluate_access(
            db,
            "tenant-a",
            request,
        )
        db.commit()
        assert response["decision"] is True
        assert receipt.policy_decision == "deny"
        assert receipt.enforcement_mode == "warn"
    invalidate_policy_cache()


def test_runtime_receipt_signing_is_deferred_and_verifiable(tmp_path, monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "runtime-private.pem"
    public_path = tmp_path / "runtime-public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    profiles = {
        "runtime": {
            "type": "ed25519",
            "key_id": "runtime-2026-07",
            "private_key_ref": f"file:{private_path}",
        }
    }
    trust = {
        "runtime": {
            "type": "ed25519",
            "key_id": "runtime-2026-07",
            "public_key_ref": f"file:{public_path}",
        }
    }
    monkeypatch.setattr(settings, "secret_file_roots", (tmp_path.resolve(),))
    monkeypatch.setattr(
        settings,
        "governance_package_signing_profiles_json",
        json.dumps(profiles),
    )
    monkeypatch.setattr(
        settings,
        "governance_package_verification_profiles_json",
        json.dumps(trust),
    )
    monkeypatch.setattr(settings, "runtime_receipt_signing_profile", "runtime")
    monkeypatch.setattr(settings, "runtime_authorization_mode", "enforce")
    monkeypatch.setattr(settings, "policy_cache_seconds", 0)
    invalidate_policy_cache()
    session_factory = _session_factory()
    with session_factory() as db:
        _agent, asset = _seed(db, "tenant-a")
        request = AuthZENEvaluationRequest.model_validate(
            {
                "subject": {"type": "ai_agent", "id": "runtime-agent"},
                "resource": {"type": "data_asset", "id": str(asset.id)},
                "action": {"name": "send"},
                "context": {"destination": "internal-rag"},
            }
        )
        _response, receipt, _idempotent = evaluate_access(
            db,
            "tenant-a",
            request,
        )
        db.commit()
        assert receipt.signing_status == "pending"
        assert process_pending_receipts(db)["signed"] == 1
        db.refresh(receipt)
        verified = verify_receipt(receipt, "runtime")
        assert receipt.signing_status == "signed"
        assert verified["signature_valid"] is True
        assert verified["trusted"] is True
        receipt.retention_until = utc_now() - timedelta(seconds=1)
        db.commit()
        assert purge_expired_receipts(db) == 1
    invalidate_policy_cache()


def test_ai_resource_lineage_detects_unexpected_runtime_paths(monkeypatch):
    session_factory = _session_factory()
    with session_factory() as db:
        _agent, asset = _seed(db)

    def override_db():
        with session_factory() as db:
            yield db

    monkeypatch.setattr(settings, "auth_disabled", True)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        for resource in (
            {
                "resource_key": "support-model",
                "resource_type": "model",
                "name": "Support Model",
                "owner": "ai@example.test",
            },
            {
                "resource_key": "customer-index",
                "resource_type": "vector-index",
                "name": "Customer Index",
                "owner": "data@example.test",
            },
            {
                "resource_key": "external-endpoint",
                "resource_type": "endpoint",
                "name": "External Endpoint",
                "owner": "ai@example.test",
            },
        ):
            assert client.post("/api/v1/ai/resources", json=resource).status_code == 201

        declared = client.post(
            "/api/v1/ai/lineage/relationships",
            json={
                "source": {"type": "model", "id": "support-model"},
                "relationship": "retrieves_from",
                "target": {"type": "vector-index", "id": "customer-index"},
                "expected": True,
                "metadata": {"environment": "production"},
            },
        )
        assert declared.status_code == 200

        observed = client.post(
            "/api/v1/ai/lineage/observations",
            json={
                "event_id": "lineage-1",
                "source": {"type": "model", "id": "support-model"},
                "relationship": "retrieves_from",
                "target": {"type": "vector-index", "id": "customer-index"},
                "observed_at": "2026-07-31T12:00:00Z",
            },
        )
        assert observed.status_code == 200
        assert observed.json()["observation"]["drift_detected"] is False

        drift = client.post(
            "/api/v1/ai/lineage/observations",
            json={
                "event_id": "lineage-2",
                "source": {"type": "model", "id": "support-model"},
                "relationship": "calls",
                "target": {"type": "endpoint", "id": "external-endpoint"},
                "observed_at": "2026-07-31T12:01:00Z",
                "metadata": {"transport": "https"},
            },
        )
        assert drift.status_code == 200
        assert drift.json()["observation"]["drift_detected"] is True
        repeated = client.post(
            "/api/v1/ai/lineage/observations",
            json={
                "event_id": "lineage-2",
                "source": {"type": "model", "id": "support-model"},
                "relationship": "calls",
                "target": {"type": "endpoint", "id": "external-endpoint"},
                "observed_at": "2026-07-31T12:01:00Z",
            },
        )
        assert repeated.json()["idempotent"] is True
        assert [item["event_id"] for item in client.get("/api/v1/ai/lineage/drift").json()] == [
            "lineage-2"
        ]
        analytics = client.get("/api/v1/governance/analytics?days=30").json()
        assert analytics["runtime_authorization"]["lineage_drift_events"] == 1
    finally:
        app.dependency_overrides.clear()


def test_v18_receipts_and_ai_resources_are_tenant_scoped(monkeypatch):
    session_factory = _session_factory()
    with session_factory() as db:
        _agent, asset = _seed(db, "tenant-a")

    def override_db():
        with session_factory() as db:
            yield db

    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(
        settings,
        "api_keys_json",
        json.dumps(
            {
                "tenant-a-key": {
                    "subject": "admin-a",
                    "tenant_id": "tenant-a",
                    "role": "administrator",
                },
                "tenant-b-key": {
                    "subject": "admin-b",
                    "tenant_id": "tenant-b",
                    "role": "administrator",
                },
            }
        ),
    )
    monkeypatch.setattr(settings, "runtime_authorization_mode", "enforce")
    monkeypatch.setattr(settings, "runtime_receipt_signing_profile", "")
    monkeypatch.setattr(settings, "policy_cache_seconds", 0)
    invalidate_policy_cache()
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    tenant_a = {"X-API-Key": "tenant-a-key"}
    tenant_b = {"X-API-Key": "tenant-b-key"}
    try:
        created = client.post(
            "/api/v1/ai/resources",
            headers=tenant_a,
            json={
                "resource_key": "tenant-a-model",
                "resource_type": "model",
                "name": "Tenant A Model",
                "owner": "owner-a@example.test",
            },
        )
        assert created.status_code == 201
        assert client.get("/api/v1/ai/resources", headers=tenant_b).json() == []

        decision = client.post(
            "/access/v1/evaluation",
            headers=tenant_a,
            json={
                "subject": {"type": "ai_agent", "id": "runtime-agent"},
                "resource": {"type": "data_asset", "id": str(asset.id)},
                "action": {"name": "send"},
                "context": {"destination": "internal-rag"},
            },
        )
        assert decision.status_code == 200
        receipt_id = decision.json()["context"]["receipt"]["id"]
        assert (
            client.get(
                f"/api/v1/runtime/decision-receipts/{receipt_id}",
                headers=tenant_b,
            ).status_code
            == 404
        )
        assert client.get(
            "/api/v1/runtime/decision-receipts",
            headers=tenant_b,
        ).json() == []
    finally:
        app.dependency_overrides.clear()
        invalidate_policy_cache()
