import json
from datetime import timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.benchmark import run_benchmark
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import DataAsset, GraphEdge, IntegrationDelivery, IntegrationEndpoint, utc_now
from app.services.governance import (
    create_review_task,
    governance_sla_metrics,
    notify_overdue_reviews,
)
from app.services.graph_exports import create_graph_export, load_graph_export
from app.services.integrations import (
    _format_delivery,
    create_endpoint,
    deliver_integration,
)
from app.services.jobs import claim_next_job, execute_job
from app.services.ownership import (
    attest_assignment,
    campaign_counts,
    create_campaign,
    launch_campaign,
    resolve_remediation,
)
from app.services.service_accounts import (
    authenticate_service_account,
    complete_rotation,
    create_service_account,
    lifecycle_report,
    rotate_service_account,
)
from app.soak import _report, _validate_options


def test_service_account_authentication_rotation_and_lifecycle():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        account, credential, old_key = create_service_account(
            db,
            "tenant-a",
            "automation",
            "Synthetic automation identity",
            "platform@example.test",
            "auditor",
            "admin",
            30,
        )
        assert authenticate_service_account(db, old_key)["tenant_id"] == "tenant-a"
        rotation, _new_credential, new_key = rotate_service_account(
            db,
            account,
            "admin",
            grace_hours=24,
            credential_days=60,
        )
        assert authenticate_service_account(db, old_key)["credential_id"] == credential.credential_id
        assert authenticate_service_account(db, new_key)["tenant_id"] == "tenant-a"
        complete_rotation(db, rotation)
        assert authenticate_service_account(db, old_key) is None
        assert authenticate_service_account(db, new_key)["role"] == "auditor"
        report = lifecycle_report(db, "tenant-a")
        assert report["active_accounts"] == 1
        assert report["active_credentials"] == 1
        assert report["active_rotations"] == 0


def test_service_account_header_authenticates_tenant(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        _account, _credential, key = create_service_account(
            db,
            "tenant-a",
            "api-automation",
            "Synthetic API identity",
            "platform@example.test",
            "read-only",
            "admin",
            30,
        )

    def override_db():
        with session_factory() as db:
            yield db

    monkeypatch.setattr(settings, "auth_disabled", False)
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get(
            "/api/v1/summary",
            headers={"X-Service-Account-Key": key},
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] == "tenant-a"
    finally:
        app.dependency_overrides.clear()


def test_governance_sla_notification_queues_allowlisted_event(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "integration_allowed_hosts", ("alerts.example.test",))
    with sessionmaker(bind=engine)() as db:
        create_endpoint(
            db,
            "tenant-a",
            "governance-alerts",
            "observe",
            "https://alerts.example.test/events",
            None,
            ["governance.review.overdue"],
            True,
            "admin",
            "cloudevents",
        )
        task = create_review_task(
            db,
            "tenant-a",
            "policy-approval",
            "bundle-1",
            "Review policy bundle",
            "owner",
        )
        task.due_at = utc_now() - timedelta(hours=1)
        db.commit()
        assert governance_sla_metrics(db, "tenant-a")["overdue"] == 1
        assert notify_overdue_reviews(db, "tenant-a") == {"examined": 1, "notified": 1}
        db.refresh(task)
        assert task.sla_notified_at is not None
        delivery = db.scalar(select(IntegrationDelivery))
        assert delivery.event_type == "governance.review.overdue"


def test_security_event_formats_and_splunk_auth(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "integration_allowed_hosts", ("events.example.test",))
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

    def post(url, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setenv("ODG_SPLUNK_TOKEN", "synthetic-token")
    with sessionmaker(bind=engine)() as db:
        for event_format in ("native", "cloudevents", "cef", "splunk-hec"):
            endpoint = IntegrationEndpoint(
                tenant_id="tenant-a",
                endpoint_id=f"endpoint-{event_format}",
                name=event_format,
                mode="observe",
                event_format=event_format,
                url="https://events.example.test/intake",
                events_json='["security.finding"]',
                created_by="admin",
            )
            delivery = IntegrationDelivery(
                tenant_id="tenant-a",
                delivery_id=f"delivery-{event_format}",
                endpoint_id=endpoint.endpoint_id,
                event_type="security.finding",
                payload_json='{"severity":"high"}',
            )
            db.add_all([endpoint, delivery])
            db.commit()
            _format, content_type, body = _format_delivery(endpoint, delivery)
            assert body
            assert content_type
        splunk = db.scalar(
            select(IntegrationEndpoint).where(
                IntegrationEndpoint.event_format == "splunk-hec"
            )
        )
        splunk.secret_ref = "env:ODG_SPLUNK_TOKEN"
        db.commit()
        result = deliver_integration(db, "tenant-a", "delivery-splunk-hec")
        assert result["event_format"] == "splunk-hec"
        assert captured["headers"]["Authorization"] == "Splunk synthetic-token"
        assert json.loads(captured["content"])["event"]["severity"] == "high"


def test_ownership_campaign_attestation_and_remediation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all(
            [
                DataAsset(
                    tenant_id="tenant-a",
                    source="aws-s3",
                    external_id=f"asset-{index}",
                    name=f"Asset {index}",
                    path=f"/asset/{index}",
                    owner="unknown",
                    sensitivity="Restricted",
                )
                for index in range(2)
            ]
        )
        db.commit()
        campaign = create_campaign(
            db,
            "tenant-a",
            "Restricted ownership",
            "Confirm ownership",
            {"sensitivity": "Restricted"},
            utc_now() + timedelta(days=7),
            "owner",
        )
        campaign, count = launch_campaign(db, campaign, 100)
        assert count == 2
        assignments = list(db.scalars(select_assignment(campaign.campaign_id)).all())
        first = attest_assignment(
            db,
            assignments[0],
            True,
            "owner",
            owner="data-owner@example.test",
        )
        assert first.status == "attested"
        second = attest_assignment(
            db,
            assignments[1],
            False,
            "owner",
            remediation_action="Identify accountable owner",
            remediation_due_at=utc_now() + timedelta(days=2),
        )
        assert campaign_counts(db, "tenant-a", campaign.campaign_id) == {
            "attested": 1,
            "remediation-required": 1,
        }
        resolve_remediation(db, second, "owner")
        db.refresh(campaign)
        assert campaign.status == "completed"


def test_async_graph_export_and_qualification_helpers(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "graph_export_backend", "local")
    monkeypatch.setattr(settings, "graph_export_local_directory", tmp_path)
    with sessionmaker(bind=engine)() as db:
        db.add_all(
            [
                GraphEdge(
                    tenant_id="tenant-a",
                    source_type="asset",
                    source_id=str(index),
                    relationship="derived_from",
                    target_type="asset",
                    target_id=str(index + 1),
                )
                for index in range(2)
            ]
        )
        db.commit()
        record, _job = create_graph_export(
            db,
            "tenant-a",
            "json",
            ["derived_from"],
            None,
            1,
            "auditor",
        )
        job = claim_next_job(db)
        execute_job(db, job)
        db.refresh(record)
        assert record.status == "completed"
        assert record.edge_count == 1
        assert record.truncated is True
        assert json.loads(load_graph_export(record))["edges"][0]["relationship"] == "derived_from"

    benchmark = run_benchmark(100, 100, 5)
    assert benchmark["operations"]["catalog_filter"]["p50_ms"] >= 0
    _validate_options("https://odg.example.test", 10, 2, 5)
    report = _report(
        "https://odg.example.test",
        10,
        2,
        5,
        [("/health", 200, 1.0), ("/ready", 503, 2.0)],
    )
    assert report["success_rate"] == 0.5


def select_assignment(campaign_id: str):
    from app.models import OwnershipAssignment

    return (
        select(OwnershipAssignment)
        .where(OwnershipAssignment.campaign_id == campaign_id)
        .order_by(OwnershipAssignment.asset_id)
    )
