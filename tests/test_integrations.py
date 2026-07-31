import json

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import IntegrationDelivery
from app.services.integrations import create_endpoint, queue_integration_event
from app.services.jobs import claim_next_job, execute_job


def test_signed_integration_delivery_uses_allowlist_and_worker(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "integration_allowed_hosts", ("alerts.example.test",))
    monkeypatch.setenv("ODG_WEBHOOK_SECRET", "synthetic-secret")
    captured = {}

    class Response:
        status_code = 202

        def raise_for_status(self):
            return None

    def post(url, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    with session_factory() as db:
        endpoint = create_endpoint(
            db,
            "tenant-a",
            "security-alerts",
            "enforce",
            "https://alerts.example.test/decisions",
            "env:ODG_WEBHOOK_SECRET",
            ["policy.decision"],
            True,
            "administrator",
        )
        deliveries = queue_integration_event(
            db,
            "tenant-a",
            "policy.decision",
            {"decision": "deny", "asset_id": 1},
            "policy-engine",
        )
        assert len(deliveries) == 1
        job = claim_next_job(db)
        execute_job(db, job)
        delivery = db.scalar(select(IntegrationDelivery))
        assert delivery.status == "delivered"
        assert captured["url"] == endpoint.url
        assert captured["headers"]["X-OpenDataGraph-Mode"] == "enforce"
        assert captured["headers"]["X-OpenDataGraph-Signature"].startswith("sha256=")
        assert json.loads(captured["content"])["decision"] == "deny"


def test_kafka_rest_delivery_wraps_tenant_keyed_cloudevent(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(settings, "integration_allowed_hosts", ("kafka.example.test",))
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

    def post(url, content, headers, timeout):
        captured.update(url=url, content=content, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    with session_factory() as db:
        create_endpoint(
            db,
            "tenant-a",
            "governance-kafka",
            "observe",
            "https://kafka.example.test/topics/governance",
            None,
            ["runtime.enforcement"],
            True,
            "administrator",
            "kafka-rest",
        )
        queue_integration_event(
            db,
            "tenant-a",
            "runtime.enforcement",
            {"outcome": "applied", "receipt_id": "synthetic-receipt"},
            "governance-outbox",
        )
        execute_job(db, claim_next_job(db))
    body = json.loads(captured["content"])
    assert captured["headers"]["Content-Type"] == "application/vnd.kafka.json.v2+json"
    assert body["records"][0]["key"] == "tenant-a"
    event = body["records"][0]["value"]
    assert event["specversion"] == "1.0"
    assert event["type"] == "com.opendatagraph.runtime.enforcement"
    assert event["data"]["outcome"] == "applied"
