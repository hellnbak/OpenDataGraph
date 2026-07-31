import json
from datetime import datetime, timedelta

import httpx
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, clear_oidc_discovery_cache, current_principal
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import (
    EvidenceDisposition,
    EvidenceRecord,
    PolicyBundle,
    PolicyException,
    SCIMResource,
    utc_now,
)
from app.services.evidence import (
    approve_disposition,
    execute_disposition,
    purge_expired_evidence,
    store_evidence,
    verify_object_lock,
)
from app.services.graph import (
    explain_paths,
    export_graph_edges,
    ingest_openlineage_event,
)
from app.services.integrations import (
    create_endpoint,
    delivery_dashboard,
    queue_integration_event,
    replay_delivery,
)
from app.services.jobs import claim_next_job, execute_job
from app.services.policy_governance import (
    approve_exception_renewal,
    can_approve_bundle,
    compare_policy_bundles,
    create_delegation,
    request_exception_renewal,
)
from app.services.schedules import create_schedule, next_cron_run


def test_cron_schedule_uses_timezone_and_maintenance_windows():
    after = datetime(2026, 7, 31, 15, 55)
    next_run = next_cron_run(
        "*/15 * * * *",
        "America/Los_Angeles",
        after,
        [{"days": [4], "start": "09:00", "end": "10:00"}],
    )
    assert next_run == datetime(2026, 7, 31, 17, 0)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        schedule = create_schedule(
            db,
            "tenant-a",
            "github",
            "example",
            3600,
            {"secret_ref": "env:ODG_GITHUB_TOKEN"},
            "operator",
            schedule_type="cron",
            cron_expression="0 9 * * 1-5",
            timezone_name="America/Los_Angeles",
        )
        assert schedule.schedule_type == "cron"
        assert schedule.cron_expression == "0 9 * * 1-5"
        assert schedule.next_run_at > utc_now()


def test_oidc_discovery_is_cached(monkeypatch):
    clear_oidc_discovery_cache()
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(
        settings,
        "oidc_providers_json",
        json.dumps(
            {
                "provider": {
                    "issuer": "https://id.example.test",
                    "audience": "opendatagraph",
                }
            }
        ),
    )
    discovery_calls = []

    class DiscoveryResponse:
        content = b'{"issuer":"https://id.example.test","jwks_uri":"https://id.example.test/keys"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "issuer": "https://id.example.test",
                "jwks_uri": "https://id.example.test/keys",
            }

    def get(url, timeout):
        discovery_calls.append((url, timeout))
        return DiscoveryResponse()

    monkeypatch.setattr(httpx, "get", get)

    class SigningKey:
        key = object()

    class JWKClient:
        def __init__(self, url):
            assert url == "https://id.example.test/keys"

        def get_signing_key_from_jwt(self, token):
            return SigningKey()

    monkeypatch.setattr(jwt, "PyJWKClient", JWKClient)

    def decode(token, *_args, **kwargs):
        if kwargs["options"].get("verify_signature") is False:
            return {"iss": "https://id.example.test"}
        return {
            "iss": "https://id.example.test",
            "sub": token,
            "tenant_id": "tenant-a",
            "role": "auditor",
            "iat": 1,
            "exp": 9999999999,
        }

    monkeypatch.setattr(jwt, "decode", decode)
    assert current_principal(None, "Bearer user-1").subject == "user-1"
    assert current_principal(None, "Bearer user-2").subject == "user-2"
    assert len(discovery_calls) == 1


def test_scim_bulk_deprovisions_user_and_removes_group_membership(monkeypatch):
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

    monkeypatch.setattr(
        settings,
        "scim_tokens_json",
        json.dumps({"tenant-token": {"tenant_id": "tenant-a"}}),
    )
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {"Authorization": "Bearer tenant-token"}
    try:
        created = client.post(
            "/scim/v2/Bulk",
            headers=headers,
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
                "Operations": [
                    {
                        "method": "POST",
                        "path": "/Users",
                        "bulkId": "user-1",
                        "data": {
                            "userName": "user@example.test",
                            "displayName": "Synthetic User",
                        },
                    },
                    {
                        "method": "POST",
                        "path": "/Groups",
                        "data": {
                            "displayName": "Analysts",
                            "members": [{"value": "bulkId:user-1"}],
                        },
                    },
                ],
            },
        )
        assert created.status_code == 200
        user_id = created.json()["Operations"][0]["response"]["id"]
        deleted = client.post(
            "/scim/v2/Bulk",
            headers=headers,
            json={"Operations": [{"method": "DELETE", "path": f"/Users/{user_id}"}]},
        )
        assert deleted.json()["Operations"][0]["status"] == "204"
        with session_factory() as db:
            job = claim_next_job(db)
            assert job.job_type == "identity.deprovision"
            execute_job(db, job)
            user = db.scalar(
                select(SCIMResource).where(SCIMResource.resource_id == user_id)
            )
            group = db.scalar(
                select(SCIMResource).where(SCIMResource.resource_type == "Group")
            )
            assert user.active is False
            assert user.deprovisioned_at is not None
            assert json.loads(group.data_json)["members"] == []
    finally:
        app.dependency_overrides.clear()


def test_integration_dead_letter_dashboard_and_replay(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "integration_allowed_hosts", ("alerts.example.test",))

    def failing_post(*_args, **_kwargs):
        raise httpx.ConnectError("synthetic failure")

    monkeypatch.setattr(httpx, "post", failing_post)
    with session_factory() as db:
        create_endpoint(
            db,
            "tenant-a",
            "alerts",
            "observe",
            "https://alerts.example.test/events",
            None,
            ["policy.decision"],
            True,
            "admin",
        )
        delivery = queue_integration_event(
            db,
            "tenant-a",
            "policy.decision",
            {"decision": "deny"},
            "policy-engine",
        )[0]
        for _ in range(5):
            job = claim_next_job(db)
            execute_job(db, job)
            db.refresh(job)
            if job.status == "pending":
                job.available_at = utc_now()
                db.commit()
        db.refresh(delivery)
        assert delivery.status == "dead-letter"
        assert delivery_dashboard(db, "tenant-a")["statuses"]["dead-letter"] == 1
        replay = replay_delivery(
            db,
            "tenant-a",
            delivery.delivery_id,
            "admin",
            "Endpoint recovered",
        )
        assert replay.replayed_from == delivery.delivery_id
        assert replay.status == "pending"


def test_policy_diff_delegation_and_exception_renewal():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        first = PolicyBundle(
            tenant_id="tenant-a",
            bundle_id="bundle-1",
            name="enterprise",
            version=1,
            definition_json=json.dumps(
                [
                    {
                        "id": "policy-1",
                        "version": "1",
                        "decision": "allow",
                        "match": {},
                        "risk_score": 10,
                        "reason": "Initial",
                        "controls": [],
                    }
                ]
            ),
            created_by="owner",
        )
        second = PolicyBundle(
            tenant_id="tenant-a",
            bundle_id="bundle-2",
            name="enterprise",
            version=2,
            definition_json=json.dumps(
                [
                    {
                        "id": "policy-1",
                        "version": "2",
                        "decision": "conditional",
                        "match": {},
                        "risk_score": 50,
                        "reason": "Hardened",
                        "controls": ["review"],
                    },
                    {
                        "id": "policy-2",
                        "version": "1",
                        "decision": "deny",
                        "match": {"action": "train"},
                        "risk_score": 90,
                        "reason": "No training",
                        "controls": [],
                    },
                ]
            ),
            created_by="owner",
        )
        db.add_all([first, second])
        db.commit()
        diff = compare_policy_bundles(second, first)
        assert diff["summary"] == {"added": 1, "removed": 0, "changed": 1}
        create_delegation(
            db,
            "tenant-a",
            "delegate",
            "enterprise",
            True,
            True,
            utc_now() + timedelta(days=30),
            "admin",
        )
        principal = Principal("delegate", "data-owner", "tenant-a")
        assert can_approve_bundle(db, principal, second) is True
        exception = PolicyException(
            tenant_id="tenant-a",
            exception_id="exception-1",
            override_decision="conditional",
            reason="Temporary",
            expires_at=utc_now() + timedelta(days=1),
            created_by="owner",
            approved_by="admin",
        )
        db.add(exception)
        db.commit()
        old_expiry = exception.expires_at
        request_exception_renewal(
            db,
            exception,
            utc_now() + timedelta(days=10),
            "Still required",
            "owner",
        )
        approve_exception_renewal(db, exception, "delegate")
        assert exception.expires_at > old_expiry
        assert exception.renewal_status == "approved"


def test_evidence_object_lock_disposition_and_retention_queue(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "evidence_backend", "local")
    monkeypatch.setattr(settings, "evidence_local_directory", tmp_path)
    with session_factory() as db:
        storage_uri, digest = store_evidence("tenant-a", "evidence-1", b"synthetic")
        record = EvidenceRecord(
            tenant_id="tenant-a",
            evidence_id="evidence-1",
            category="audit",
            subject_type="asset",
            subject_id="1",
            filename="evidence.txt",
            content_type="text/plain",
            storage_uri=storage_uri,
            sha256=digest,
            size_bytes=9,
            retention_until=utc_now() - timedelta(days=1),
            created_by="owner",
        )
        db.add(record)
        db.commit()
        assert verify_object_lock(db, record)["status"] == "not-applicable"
        monkeypatch.setattr(settings, "evidence_disposition_approval_required", True)
        assert purge_expired_evidence(db, "tenant-a") == {"requested": 1, "examined": 1}
        disposition = db.scalar(select(EvidenceDisposition))
        approve_disposition(db, disposition, "admin")
        execute_disposition(db, "tenant-a", disposition.disposition_id, "worker")
        db.refresh(record)
        assert record.deleted_at is not None
        assert not (tmp_path / "evidence" / "tenant-a" / "evidence-1").exists()


def test_graph_path_explanations_and_bounded_export():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    event = {
        "eventType": "COMPLETE",
        "eventTime": "2026-07-30T20:00:00Z",
        "run": {"runId": "run-1"},
        "job": {"namespace": "analytics", "name": "rollup"},
        "inputs": [{"namespace": "warehouse", "name": "source"}],
        "outputs": [{"namespace": "warehouse", "name": "target"}],
    }
    with sessionmaker(bind=engine)() as db:
        ingest_openlineage_event(db, "tenant-a", event)
        paths = explain_paths(
            db,
            "tenant-a",
            "dataset",
            "warehouse/source",
            "dataset",
            "warehouse/target",
            3,
        )
        assert paths["found"] is True
        assert "transforms_into" in paths["paths"][0]["explanation"]
        exported = export_graph_edges(db, "tenant-a", set(), 2)
        assert exported["count"] == 2
        assert exported["truncated"] is True
