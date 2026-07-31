import json
from datetime import timedelta

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_principal
from app.benchmark import BENCHMARK_PROFILES, run_benchmark
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import (
    DataAsset,
    GovernanceReviewTask,
    GraphEdge,
    IntegrationDelivery,
    IntegrationEndpoint,
    OwnershipAssignment,
    OwnershipCampaign,
    utc_now,
)
from app.query_plans import capture_query_plans
from app.services.evidence_packages import (
    create_evidence_package,
    governance_analytics,
    load_evidence_package,
)
from app.services.graph_exports import create_graph_export, graph_export_response
from app.services.jobs import claim_next_job, execute_job
from app.services.ownership import (
    create_campaign_schedule,
    enqueue_due_ownership_campaigns,
    execute_scheduled_campaign,
)
from connectors.postgresql import PostgreSQLConnector, _decode_cursor


def test_short_lived_workload_identity_uses_fixed_tenant_and_role(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(
        settings,
        "workload_identity_providers_json",
        json.dumps(
            {
                "ci": {
                    "issuer": "https://identity.example.test",
                    "audience": "opendatagraph",
                    "jwks_url": "https://identity.example.test/keys",
                    "tenant_id": "tenant-a",
                    "role": "connector-operator",
                    "max_token_seconds": 900,
                }
            }
        ),
    )
    calls = iter(
        [
            {"iss": "https://identity.example.test"},
            {
                "iss": "https://identity.example.test",
                "sub": "deployment-42",
                "tenant_id": "attacker-tenant",
                "role": "administrator",
                "iat": 1000,
                "exp": 1600,
            },
        ]
    )
    monkeypatch.setattr(jwt, "decode", lambda *_args, **_kwargs: next(calls))

    class SigningKey:
        key = object()

    class JWKClient:
        def __init__(self, url):
            assert url == "https://identity.example.test/keys"

        def get_signing_key_from_jwt(self, token):
            assert token == "workload-token"
            return SigningKey()

    monkeypatch.setattr(jwt, "PyJWKClient", JWKClient)
    principal = current_principal(None, None, None, "workload-token")
    assert principal.subject == "workload:deployment-42"
    assert principal.tenant_id == "tenant-a"
    assert principal.role == "connector-operator"


def test_v16_api_routes_preserve_tenant_isolation(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

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
                    "subject": "owner-a",
                    "tenant_id": "tenant-a",
                    "role": "data-owner",
                },
                "tenant-b-key": {
                    "subject": "owner-b",
                    "tenant_id": "tenant-b",
                    "role": "data-owner",
                },
            }
        ),
    )
    monkeypatch.setattr(settings, "governance_package_backend", "local")
    monkeypatch.setattr(settings, "governance_package_local_directory", tmp_path)
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        created_schedule = client.post(
            "/api/v1/ownership/schedules",
            headers={"X-API-Key": "tenant-a-key"},
            json={
                "name": "Quarterly ownership",
                "scope": {"sensitivity": "Restricted"},
                "schedule_type": "cron",
                "cron_expression": "0 9 1 */3 *",
                "timezone": "UTC",
            },
        )
        assert created_schedule.status_code == 201
        assert client.get(
            "/api/v1/ownership/schedules",
            headers={"X-API-Key": "tenant-b-key"},
        ).json() == []
        created_package = client.post(
            "/api/v1/governance/evidence-packages",
            headers={"X-API-Key": "tenant-a-key"},
            json={"days": 30, "categories": ["reviews"], "max_records": 100},
        )
        assert created_package.status_code == 202
        package_id = created_package.json()["package"]["package_id"]
        cross_tenant = client.get(
            f"/api/v1/governance/evidence-packages/{package_id}",
            headers={"X-API-Key": "tenant-b-key"},
        )
        assert cross_tenant.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_ownership_schedule_enqueues_idempotent_campaign_and_notification():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add(
            DataAsset(
                tenant_id="tenant-a",
                source="postgresql",
                external_id="asset-1",
                name="customers",
                path="postgresql://catalog/public/customers",
                owner="unknown",
                sensitivity="Restricted",
            )
        )
        endpoint = IntegrationEndpoint(
            tenant_id="tenant-a",
            endpoint_id="endpoint-1",
            name="ownership-alerts",
            mode="observe",
            event_format="cloudevents",
            url="https://events.example.test/ownership",
            events_json="[]",
            enabled=True,
            created_by="admin",
        )
        db.add(endpoint)
        db.commit()
        schedule = create_campaign_schedule(
            db,
            "tenant-a",
            "Restricted ownership",
            "Confirm accountable owners",
            {"sensitivity": "Restricted"},
            14,
            100,
            "interval",
            3600,
            None,
            "UTC",
            [],
            [endpoint.endpoint_id],
            True,
            "owner",
        )
        assert enqueue_due_ownership_campaigns(db) == 1
        job = claim_next_job(db)
        payload = json.loads(job.payload_json)
        execute_job(db, job)
        campaign = db.scalar(select(OwnershipCampaign))
        assert campaign.source_schedule_id == schedule.schedule_id
        assert campaign.status == "active"
        assert db.scalar(select(OwnershipAssignment)).status == "pending"
        delivery = db.scalar(select(IntegrationDelivery))
        assert delivery.event_type == "ownership.campaign.launched"
        result = execute_scheduled_campaign(
            db,
            "tenant-a",
            schedule.schedule_id,
            payload["scheduled_for"],
        )
        assert result["idempotent"] is True
        assert len(list(db.scalars(select(OwnershipCampaign)).all())) == 1


def test_governance_analytics_and_metadata_only_evidence_package(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "governance_package_backend", "local")
    monkeypatch.setattr(settings, "governance_package_local_directory", tmp_path)
    with sessionmaker(bind=engine)() as db:
        db.add_all(
            [
                GovernanceReviewTask(
                    tenant_id="tenant-a",
                    task_id="review-a",
                    task_type="policy-approval",
                    subject_id="bundle-a",
                    title="Review synthetic policy metadata",
                    due_at=utc_now() + timedelta(days=1),
                    created_by="owner",
                ),
                GovernanceReviewTask(
                    tenant_id="tenant-b",
                    task_id="review-b",
                    task_type="policy-approval",
                    subject_id="bundle-b",
                    title="Other tenant review",
                    due_at=utc_now() + timedelta(days=1),
                    created_by="owner",
                ),
            ]
        )
        db.commit()
        analytics = governance_analytics(db, "tenant-a", 30)
        assert analytics["reviews"]["created"] == 1
        record, _job = create_evidence_package(
            db,
            "tenant-a",
            30,
            ["reviews"],
            100,
            "auditor",
        )
        execute_job(db, claim_next_job(db))
        db.refresh(record)
        document = json.loads(load_evidence_package(record))
        assert document["manifest"]["content_policy"] == "metadata-only"
        assert document["manifest"]["record_count"] == 1
        assert document["records"]["reviews"][0]["task_id"] == "review-a"
        assert "details" not in document["records"]["reviews"][0]


def test_https_export_sink_uses_mounted_workload_token(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    token_file = tmp_path / "identity-token"
    token_file.write_text("short-lived-token", encoding="utf-8")
    monkeypatch.setattr(settings, "graph_export_https_allowed_hosts", ("sink.example.test",))
    monkeypatch.setattr(
        settings,
        "graph_export_https_identity_token_file",
        str(token_file),
    )
    monkeypatch.setattr(settings, "secret_file_roots", (tmp_path.resolve(),))
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

    def put(url, content, headers, timeout, follow_redirects):
        captured.update(
            url=url,
            content=content,
            headers=headers,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )
        return Response()

    monkeypatch.setattr(httpx, "put", put)
    with sessionmaker(bind=engine)() as db:
        db.add(
            GraphEdge(
                tenant_id="tenant-a",
                source_type="asset",
                source_id="1",
                relationship="derived_from",
                target_type="asset",
                target_id="2",
            )
        )
        db.commit()
        record, _job = create_graph_export(
            db,
            "tenant-a",
            "json",
            [],
            "https://sink.example.test/exports/graph.json",
            10,
            "auditor",
        )
        execute_job(db, claim_next_job(db))
        db.refresh(record)
        assert captured["headers"]["Authorization"] == "Bearer short-lived-token"
        assert captured["follow_redirects"] is False
        assert graph_export_response(record)["retrievable"] is False
        assert "short-lived-token" not in record.storage_uri


def test_postgresql_connector_metadata_pagination_without_content(monkeypatch):
    rows = [
        {
            "table_schema": "analytics",
            "table_name": "customers",
            "table_type": "BASE TABLE",
            "estimated_rows": 1200,
            "owner": "catalog_reader",
            "column_count": 12,
        },
        {
            "table_schema": "analytics",
            "table_name": "orders",
            "table_type": "BASE TABLE",
            "estimated_rows": 3400,
            "owner": "catalog_reader",
            "column_count": 15,
        },
    ]
    captured = {}

    class Result:
        def mappings(self):
            return rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement, parameters):
            captured.update(statement=statement, parameters=parameters)
            return Result()

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            captured["disposed"] = True

    monkeypatch.setattr("connectors.postgresql.create_engine", lambda *_args, **_kwargs: Engine())
    connector = PostgreSQLConnector(
        "analytics-catalog",
        "postgresql+psycopg://reader:secret@db.example.test/catalog",
        schemas=["analytics"],
    )
    batch = connector.scan(max_items=1)
    assert batch.complete is False
    assert _decode_cursor(batch.next_cursor) == ("analytics", "customers")
    assert batch.records[0].metadata["content_retrieved"] is False
    assert batch.records[0].modified_at is None
    assert captured["parameters"]["limit"] == 2
    assert captured["disposed"] is True


def test_benchmark_profiles_and_read_only_query_plan_capture(monkeypatch):
    assert BENCHMARK_PROFILES["postgres-large"]["edges"] == 1_500_000
    with pytest.raises(ValueError, match="allow_fixture_writes"):
        run_benchmark(100, 100, 5, "postgresql://db/catalog")

    class Result:
        def scalar_one(self):
            return [{"Plan": {"Node Type": "Index Scan"}}]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement, parameters):
            assert str(statement).lstrip().startswith("EXPLAIN (FORMAT JSON)")
            assert parameters["tenant_id"] == "tenant-a"
            return Result()

    class Engine:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()

        def connect(self):
            return Connection()

        def dispose(self):
            return None

    monkeypatch.setattr("app.query_plans.create_engine", lambda *_args, **_kwargs: Engine())
    report = capture_query_plans("postgresql://db/catalog", "tenant-a")
    assert report["analyze"] is False
    assert set(report["plans"]) == {
        "catalog-filter",
        "graph-outbound",
        "governance-overdue",
        "ownership-remediation",
    }
