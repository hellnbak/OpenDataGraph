import json

import pytest
from fastapi import HTTPException

from app.auth import current_principal
from app.config import settings


def test_api_key_principal_requires_valid_tenant_and_subject(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(
        settings,
        "api_keys_json",
        json.dumps(
            {
                "invalid-tenant": {
                    "subject": "reader",
                    "role": "read-only",
                    "tenant_id": "../tenant",
                },
                "invalid-subject": {
                    "subject": "",
                    "role": "read-only",
                    "tenant_id": "tenant-a",
                },
            }
        ),
    )
    with pytest.raises(HTTPException) as invalid_tenant:
        current_principal("invalid-tenant")
    assert invalid_tenant.value.status_code == 403
    with pytest.raises(HTTPException) as invalid_subject:
        current_principal("invalid-subject")
    assert invalid_subject.value.status_code == 403


def test_api_key_configuration_requires_object_entries(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "api_keys_json", json.dumps({"key": "read-only"}))
    with pytest.raises(HTTPException) as error:
        current_principal("key")
    assert error.value.status_code == 500
