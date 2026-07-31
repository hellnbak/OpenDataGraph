import json

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_principal
from app.config import settings
from app.database import Base, get_db
from app.main import app


def test_oidc_provider_validates_and_maps_claims(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(
        settings,
        "oidc_providers_json",
        json.dumps(
            {
                "entra": {
                    "issuer": "https://login.example.test/tenant/v2.0",
                    "audience": "opendatagraph",
                    "jwks_url": "https://login.example.test/keys",
                    "tenant_claim": "tid",
                    "role_claim": "roles",
                    "role_mapping": {"ODG.Admin": "administrator"},
                }
            }
        ),
    )

    calls = iter(
        [
            {"iss": "https://login.example.test/tenant/v2.0"},
            {
                "iss": "https://login.example.test/tenant/v2.0",
                "sub": "user-1",
                "tid": "tenant-a",
                "roles": ["ODG.Admin"],
                "iat": 1,
                "exp": 9999999999,
            },
        ]
    )
    monkeypatch.setattr(jwt, "decode", lambda *_args, **_kwargs: next(calls))

    class SigningKey:
        key = object()

    class JWKClient:
        def __init__(self, url):
            assert url == "https://login.example.test/keys"

        def get_signing_key_from_jwt(self, token):
            assert token == "signed-token"
            return SigningKey()

    monkeypatch.setattr(jwt, "PyJWKClient", JWKClient)
    principal = current_principal(None, "Bearer signed-token")
    assert principal.subject == "user-1"
    assert principal.tenant_id == "tenant-a"
    assert principal.role == "administrator"


def test_scim_users_are_tenant_scoped(monkeypatch):
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

    monkeypatch.setattr(settings, "scim_bearer_token", "")
    monkeypatch.setattr(
        settings,
        "scim_tokens_json",
        json.dumps(
            {
                "tenant-a-token": {"tenant_id": "tenant-a"},
                "tenant-b-token": {"tenant_id": "tenant-b"},
            }
        ),
    )
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    headers = {
        "Authorization": "Bearer tenant-a-token",
    }
    try:
        created = client.post(
            "/scim/v2/Users",
            headers=headers,
            json={
                "userName": "analyst@example.test",
                "displayName": "Synthetic Analyst",
                "active": True,
            },
        )
        assert created.status_code == 201
        resource_id = created.json()["id"]
        listed = client.get("/scim/v2/Users", headers=headers)
        assert listed.json()["totalResults"] == 1
        other_tenant = client.get(
            "/scim/v2/Users",
            headers={"Authorization": "Bearer tenant-b-token"},
        )
        assert other_tenant.json()["totalResults"] == 0
        patched = client.patch(
            f"/scim/v2/Users/{resource_id}",
            headers=headers,
            json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
        )
        assert patched.status_code == 200
        assert patched.json()["active"] is False
    finally:
        app.dependency_overrides.clear()
