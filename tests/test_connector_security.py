import asyncio

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ConnectorRun
from app.services.connectors import ingest_connector, safe_connector_error
from connectors.github import GitHubConnector
from connectors.sharepoint import SharePointConnector


def test_connector_api_url_requires_https_and_allowed_host():
    with pytest.raises(ValueError, match="HTTPS"):
        GitHubConnector(
            "example",
            "token",
            "http://api.github.com",
            allowed_hosts=("api.github.com",),
        )
    with pytest.raises(ValueError, match="allowlist"):
        GitHubConnector(
            "example",
            "token",
            "https://unapproved.example.invalid",
            allowed_hosts=("api.github.com",),
        )


def test_sharepoint_rejects_unapproved_cursor_before_request():
    connector = SharePointConnector(
        "site",
        "drive",
        "token",
        allowed_hosts=("graph.microsoft.com",),
    )
    with pytest.raises(ValueError, match="allowlist"):
        connector.scan(cursor="https://unapproved.example.invalid/delta")


def test_connector_errors_redact_common_credentials():
    message = safe_connector_error(
        "request token=supersecret failed with Authorization: Bearer bearer-secret",
        ("supersecret", "bearer-secret"),
    )
    assert "supersecret" not in message
    assert "bearer-secret" not in message
    assert "<redacted>" in message


def test_failed_connector_run_persists_only_sanitized_error():
    class BrokenConnector:
        source = "test"
        account = "example"
        token = "supersecret"

        def scan(self, cursor=None, max_items=500):
            del cursor, max_items
            raise RuntimeError("provider rejected token=supersecret")

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        with pytest.raises(RuntimeError) as error:
            asyncio.run(ingest_connector(db, BrokenConnector(), tenant_id="tenant-a"))
        assert "supersecret" not in str(error.value)
        run = db.scalar(select(ConnectorRun))
        assert run is not None
        assert run.status == "failed"
        assert "supersecret" not in (run.error or "")
