import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import DataAsset


def test_asset_queries_are_scoped_to_api_key_tenant(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with session_factory() as db:
        db.add_all(
            [
                DataAsset(
                    tenant_id="tenant-a",
                    source="test",
                    external_id="test://tenant-a",
                    name="Tenant A asset",
                    path="/tenant-a",
                ),
                DataAsset(
                    tenant_id="tenant-b",
                    source="test",
                    external_id="test://tenant-b",
                    name="Tenant B asset",
                    path="/tenant-b",
                ),
            ]
        )
        db.commit()
        tenant_b_id = db.query(DataAsset).filter_by(tenant_id="tenant-b").one().id

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
                    "subject": "reader-a",
                    "role": "read-only",
                    "tenant_id": "tenant-a",
                }
            }
        ),
    )
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        response = client.get("/api/v1/assets", headers={"X-API-Key": "tenant-a-key"})
        assert response.status_code == 200
        assert [asset["tenant_id"] for asset in response.json()] == ["tenant-a"]
        forbidden = client.get(f"/api/v1/assets/{tenant_b_id}", headers={"X-API-Key": "tenant-a-key"})
        assert forbidden.status_code == 404
    finally:
        app.dependency_overrides.clear()
