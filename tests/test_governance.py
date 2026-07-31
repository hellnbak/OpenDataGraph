import json
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import AIAgent, DataAsset, EvidenceRecord, PolicyException, utc_now
from app.services.evidence import purge_expired_evidence, store_evidence
from app.services.policy import evaluate


def test_evidence_retention_respects_legal_hold(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "evidence_backend", "local")
    monkeypatch.setattr(settings, "evidence_local_directory", tmp_path)
    with session_factory() as db:
        for evidence_id, legal_hold in (("delete-me", False), ("hold-me", True)):
            storage_uri, digest = store_evidence("tenant-a", evidence_id, evidence_id.encode())
            db.add(
                EvidenceRecord(
                    tenant_id="tenant-a",
                    evidence_id=evidence_id,
                    category="audit",
                    subject_type="asset",
                    subject_id="1",
                    filename=f"{evidence_id}.txt",
                    content_type="text/plain",
                    storage_uri=storage_uri,
                    sha256=digest,
                    size_bytes=len(evidence_id),
                    legal_hold=legal_hold,
                    retention_until=utc_now() - timedelta(days=1),
                    created_by="test",
                )
            )
        db.commit()
        result = purge_expired_evidence(db, "tenant-a")
        assert result == {"deleted": 1, "failed": 0, "examined": 1}
        deleted = db.query(EvidenceRecord).filter_by(evidence_id="delete-me").one()
        held = db.query(EvidenceRecord).filter_by(evidence_id="hold-me").one()
        assert deleted.deleted_at is not None
        assert held.deleted_at is None
        assert (tmp_path / "evidence" / "tenant-a" / "hold-me").exists()


def test_policy_lifecycle_and_scoped_exception(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    def override_db():
        with session_factory() as db:
            yield db

    monkeypatch.setattr(settings, "auth_disabled", True)
    monkeypatch.setattr(settings, "default_tenant", "default")
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    policy = {
        "id": "deny-training",
        "version": "1",
        "match": {"action": "train"},
        "decision": "deny",
        "risk_score": 90,
        "reason": "Training is blocked",
        "controls": ["data-owner-approval"],
    }
    try:
        created = client.post(
            "/api/v1/policy/bundles",
            json={"name": "enterprise", "version": 1, "policies": [policy]},
        )
        assert created.status_code == 201
        bundle_id = created.json()["bundle_id"]
        assert client.post(f"/api/v1/policy/bundles/{bundle_id}/submit").status_code == 200
        assert client.post(f"/api/v1/policy/bundles/{bundle_id}/approve").status_code == 200
        assert client.post(f"/api/v1/policy/bundles/{bundle_id}/activate").json()["status"] == "active"
        second = client.post(
            "/api/v1/policy/bundles",
            json={"name": "enterprise", "version": 2, "policies": [policy]},
        )
        second_id = second.json()["bundle_id"]
        client.post(f"/api/v1/policy/bundles/{second_id}/submit")
        client.post(f"/api/v1/policy/bundles/{second_id}/approve")
        assert client.post(f"/api/v1/policy/bundles/{second_id}/activate").json()["status"] == "active"
        assert client.post(f"/api/v1/policy/bundles/{bundle_id}/rollback").json()["status"] == "active"

        with session_factory() as db:
            agent = AIAgent(
                tenant_id="default",
                key="agent",
                name="Agent",
                owner="Security",
                business_purpose="testing",
                allowed_domains="Finance",
                max_sensitivity="Restricted",
                allowed_destinations="private-model",
            )
            asset = DataAsset(
                tenant_id="default",
                source="test",
                external_id="asset",
                name="asset",
                path="/asset",
                business_domain="Finance",
                sensitivity="Internal",
                classification_confidence=0.9,
            )
            db.add_all([agent, asset])
            db.commit()
            denied = evaluate(agent, asset, "private-model", "train", "testing", db, "default")
            assert denied["decision"] == "deny"
            db.add(
                PolicyException(
                    tenant_id="default",
                    exception_id="exception-1",
                    policy_id="deny-training",
                    agent_key="agent",
                    override_decision="conditional",
                    reason="Approved synthetic evaluation",
                    controls_json=json.dumps(["sandbox-only"]),
                    expires_at=utc_now() + timedelta(days=1),
                    created_by="admin",
                    approved_by="admin",
                )
            )
            db.commit()
            excepted = evaluate(agent, asset, "private-model", "train", "testing", db, "default")
            assert excepted["decision"] == "conditional"
            assert "sandbox-only" in excepted["controls"]
    finally:
        app.dependency_overrides.clear()
