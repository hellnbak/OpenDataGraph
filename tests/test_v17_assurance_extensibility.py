import json
from datetime import timedelta

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.benchmark_baselines import capture_baseline, compare_baseline
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import (
    DataAsset,
    IntegrationDelivery,
    IntegrationEndpoint,
    OwnershipEscalationEvent,
    utc_now,
)
from app.services.evidence_packages import (
    create_evidence_package,
    load_evidence_package,
)
from app.services.evidence_signing import canonical_json, verify_evidence_package
from app.services.export_sinks import store_export_sink, validate_export_sink
from app.services.jobs import claim_next_job, enqueue_job, execute_job
from app.services.ownership import (
    create_campaign,
    create_escalation_policy,
    enqueue_due_ownership_escalations,
    launch_campaign,
    ownership_trends,
)
from app.services.workload_exchange import test_workload_exchange as run_workload_exchange_test
from connectors.conformance import run_connector_conformance
from connectors.registry import (
    connector_policy,
    connector_registration,
    enforce_connector_policy,
    govern_connector,
    set_connector_policy,
)
from connectors.sdk import AssetRecord, ScanBatch


def test_v17_api_routes_are_tenant_scoped(monkeypatch):
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
    monkeypatch.setattr(settings, "workload_exchange_profiles_json", "{}")
    monkeypatch.setattr(settings, "governance_package_signing_profiles_json", "{}")
    monkeypatch.setattr(settings, "governance_package_verification_profiles_json", "{}")
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/ownership/escalation-policies",
            headers={"X-API-Key": "tenant-a-key"},
            json={
                "name": "Due reminders",
                "stages": [
                    {
                        "key": "due-soon",
                        "offset_hours": -24,
                        "recipient": "owner",
                    }
                ],
            },
        )
        assert created.status_code == 201
        assert client.get(
            "/api/v1/ownership/escalation-policies",
            headers={"X-API-Key": "tenant-b-key"},
        ).json() == []
        updated = client.put(
            "/api/v1/connectors/capability-policy",
            headers={"X-API-Key": "tenant-a-key"},
            json={"denied_connectors": ["github"]},
        )
        assert updated.status_code == 200
        capabilities = client.get(
            "/api/v1/connectors/capabilities",
            headers={"X-API-Key": "tenant-a-key"},
        ).json()
        github = next(
            item
            for item in capabilities["connectors"]
            if item["manifest"]["connector_type"] == "github"
        )
        assert github["policy"]["allowed"] is False
        signing = client.get(
            "/api/v1/governance/evidence-signing",
            headers={"X-API-Key": "tenant-a-key"},
        )
        assert signing.status_code == 200
        assert signing.json()["signing_profiles"] == []
        exchange = client.get(
            "/api/v1/workload-identity/exchange-profiles",
            headers={"X-API-Key": "tenant-a-key"},
        )
        assert exchange.status_code == 200
        assert exchange.json()["tokens_persisted"] is False
    finally:
        app.dependency_overrides.clear()


def test_signed_evidence_package_verifies_and_detects_tampering(tmp_path, monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "signing-private.pem"
    public_path = tmp_path / "signing-public.pem"
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
    monkeypatch.setattr(settings, "secret_file_roots", (tmp_path.resolve(),))
    monkeypatch.setattr(settings, "governance_package_backend", "local")
    monkeypatch.setattr(settings, "governance_package_local_directory", tmp_path / "packages")
    monkeypatch.setattr(settings, "governance_package_signing_required", True)
    monkeypatch.setattr(settings, "governance_package_default_signing_profile", "release")
    monkeypatch.setattr(
        settings,
        "governance_package_signing_profiles_json",
        json.dumps(
            {
                "release": {
                    "type": "ed25519",
                    "key_id": "release-2026-07",
                    "private_key_ref": f"file:{private_path}",
                }
            }
        ),
    )
    monkeypatch.setattr(
        settings,
        "governance_package_verification_profiles_json",
        json.dumps(
            {
                "release": {
                    "type": "ed25519",
                    "key_id": "release-2026-07",
                    "public_key_ref": f"file:{public_path}",
                }
            }
        ),
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        record, _job = create_evidence_package(
            db,
            "tenant-a",
            30,
            ["reviews"],
            100,
            "auditor",
            "release",
        )
        execute_job(db, claim_next_job(db))
        db.refresh(record)
        content = load_evidence_package(record)
        result = verify_evidence_package(content, "release")
        assert result["valid"] is True
        assert result["signature_valid"] is True
        assert result["trusted"] is True
        assert record.signature_type == "ed25519"
        document = json.loads(content)
        assert document["manifest"]["version"] == 2
        document["analytics"]["reviews"]["created"] = 999
        tampered = verify_evidence_package(canonical_json(document), "release")
        assert tampered["valid"] is False
        assert "payload-digest-mismatch" in tampered["errors"]


def test_connector_capability_policy_and_conformance():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        record = set_connector_policy(
            db,
            "tenant-a",
            {
                "denied_connectors": ["github"],
                "allowed_content_access": ["metadata-only"],
                "require_opaque_cursor": True,
            },
            "administrator",
        )
        policy, version = connector_policy(db, "tenant-a")
        assert version == record.version == 1
        with pytest.raises(ValueError, match="connector-denied"):
            enforce_connector_policy(
                db,
                "tenant-a",
                connector_registration("github").manifest,
            )
        job = enqueue_job(
            db,
            "tenant-a",
            "connector.scan",
            {"connector_type": "aws-s3", "account": "catalog-bucket"},
            "operator",
        )
        assert job.status == "pending"

    manifest = connector_registration("postgresql").manifest

    class FakeConnector:
        source = "postgresql"
        account = "catalog"

        def scan(self, cursor=None, max_items=500):
            del cursor
            return ScanBatch(
                records=[
                    AssetRecord(
                        source="postgresql",
                        source_account="catalog",
                        external_id="postgresql://catalog/public/assets",
                        name="assets",
                        path="postgresql://catalog/public/assets",
                        metadata={"content_retrieved": False},
                    )
                ][:max_items],
                next_cursor="opaque-state",
                complete=False,
            )

    with sessionmaker(bind=engine)() as db:
        with pytest.raises(ValueError, match="connector-denied"):
            govern_connector(FakeConnector(), "github", db, "tenant-a")

    report = run_connector_conformance(FakeConnector(), manifest, max_items=1)
    assert report["conformant"] is True
    assert policy["allowed_content_access"] == ["metadata-only"]


def test_gcp_workload_exchange_and_gcs_sink(tmp_path, monkeypatch):
    subject_token = tmp_path / "subject-token"
    subject_token.write_text("projected-oidc-token", encoding="utf-8")
    monkeypatch.setattr(settings, "secret_file_roots", (tmp_path.resolve(),))
    monkeypatch.setattr(
        settings,
        "workload_exchange_profiles_json",
        json.dumps(
            {
                "gcp-export": {
                    "provider": "gcp",
                    "subject_token_ref": f"file:{subject_token}",
                    "audience": "//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/odg/providers/k8s",
                    "max_token_seconds": 900,
                }
            }
        ),
    )
    captured = {}

    class TokenResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "temporary-gcp-token", "expires_in": 600}

    def token_post(url, data, headers, timeout, follow_redirects):
        captured.update(
            token_url=url,
            token_data=data,
            token_headers=headers,
            token_timeout=timeout,
            token_redirects=follow_redirects,
        )
        return TokenResponse()

    monkeypatch.setattr(httpx, "post", token_post)
    result = run_workload_exchange_test("gcp-export")
    assert result["provider"] == "gcp"
    assert result["credentials_returned"] is False
    assert captured["token_data"]["subjectToken"] == "projected-oidc-token"
    assert captured["token_redirects"] is False

    monkeypatch.setattr(settings, "graph_export_gcs_allowed_sink_buckets", ("approved-bucket",))
    monkeypatch.setattr(settings, "graph_export_gcs_exchange_profile", "gcp-export")
    monkeypatch.setattr(
        "app.services.workload_exchange.bearer_token",
        lambda profile, provider: "temporary-gcp-token",
    )

    class UploadResponse:
        def raise_for_status(self):
            return None

    def upload_post(url, params, content, headers, timeout, follow_redirects):
        captured.update(
            upload_url=url,
            upload_params=params,
            upload_content=content,
            upload_headers=headers,
            upload_redirects=follow_redirects,
        )
        return UploadResponse()

    monkeypatch.setattr(httpx, "post", upload_post)
    uri = "gs://approved-bucket/exports/graph.json"
    validate_export_sink(uri)
    assert store_export_sink(uri, b"{}", "application/json", "a" * 64) == uri
    assert captured["upload_headers"]["Authorization"] == "Bearer temporary-gcp-token"
    assert captured["upload_redirects"] is False


def test_ownership_escalation_is_idempotent_and_trended():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        endpoint = IntegrationEndpoint(
            tenant_id="tenant-a",
            endpoint_id="endpoint-1",
            name="ownership",
            mode="observe",
            event_format="cloudevents",
            url="https://events.example.test/ownership",
            events_json="[]",
            enabled=True,
            created_by="administrator",
        )
        db.add_all(
            [
                endpoint,
                DataAsset(
                    tenant_id="tenant-a",
                    source="postgresql",
                    source_account="catalog",
                    external_id="asset-1",
                    name="customers",
                    path="postgresql://catalog/public/customers",
                    owner="owner@example.test",
                ),
            ]
        )
        db.commit()
        policy = create_escalation_policy(
            db,
            "tenant-a",
            "Standard reminders",
            "Reminder before due date",
            [
                {
                    "key": "due-soon",
                    "offset_hours": -1,
                    "recipient": "owner",
                    "endpoint_ids": [endpoint.endpoint_id],
                }
            ],
            True,
            "data-owner",
        )
        campaign = create_campaign(
            db,
            "tenant-a",
            "Quarterly ownership",
            "Confirm owners",
            {},
            utc_now() + timedelta(minutes=30),
            "data-owner",
            escalation_policy_id=policy.policy_id,
        )
        launch_campaign(db, campaign, 100)
        assert enqueue_due_ownership_escalations(db) == 1
        assert enqueue_due_ownership_escalations(db) == 0
        event = db.scalar(select(OwnershipEscalationEvent))
        delivery = db.scalar(select(IntegrationDelivery))
        assert event.status == "queued"
        assert event.assignment_count == 1
        assert delivery.idempotency_key.endswith(":due-soon")
        trends = ownership_trends(db, "tenant-a", 1)
        assert trends["series"][0]["campaigns_launched"] == 1
        assert trends["series"][0]["assignments_created"] == 1


def test_performance_baseline_comparison_and_plan_fingerprint():
    report = {
        "application_version": "1.7.0",
        "profile": {"name": "local", "database": "sqlite-memory"},
        "operations": {
            "catalog_filter": {
                "p50_ms": 10.0,
                "p95_ms": 20.0,
                "max_ms": 30.0,
                "operations_per_second": 100.0,
            }
        },
    }
    plans = {
        "database": "postgresql",
        "analyze": False,
        "plans": {
            "catalog-filter": [
                {
                    "Plan": {
                        "Node Type": "Index Scan",
                        "Index Name": "ix_data_assets_source",
                        "Total Cost": 42.0,
                    }
                }
            ]
        },
    }
    baseline = capture_baseline(report, {"name": "local-reference"}, plans)
    passing = json.loads(json.dumps(report))
    passing["operations"]["catalog_filter"]["p95_ms"] = 22.0
    assert compare_baseline(baseline, passing, plans)["passed"] is True
    failing = json.loads(json.dumps(report))
    failing["operations"]["catalog_filter"]["p95_ms"] = 30.0
    result = compare_baseline(baseline, failing, plans)
    assert result["passed"] is False
    assert result["operations"]["catalog_filter"]["metrics"]["p95_ms"]["regression_percent"] == 50.0
