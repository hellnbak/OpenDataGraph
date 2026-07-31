from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import EvidenceRecord
from app.services.evidence import load_evidence, store_evidence
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_local_evidence_storage_is_bounded_and_integrity_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "evidence_backend", "local")
    monkeypatch.setattr(settings, "evidence_local_directory", tmp_path)
    monkeypatch.setattr(settings, "evidence_max_bytes", 1024)
    content = b"synthetic audit evidence"
    storage_uri, digest = store_evidence("tenant-a", "evidence-1", content)
    assert storage_uri == "local://evidence/tenant-a/evidence-1"
    assert len(digest) == 64
    assert load_evidence(storage_uri) == content


def test_evidence_download_rejects_checksum_mismatch(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_disabled", True)
    monkeypatch.setattr(settings, "default_tenant", "default")
    monkeypatch.setattr(settings, "evidence_backend", "local")
    monkeypatch.setattr(settings, "evidence_local_directory", tmp_path)
    storage_uri, _ = store_evidence("default", "evidence-1", b"tampered")
    with session_factory() as db:
        db.add(
            EvidenceRecord(
                tenant_id="default",
                evidence_id="evidence-1",
                category="audit",
                subject_type="asset",
                subject_id="1",
                filename="evidence.txt",
                content_type="text/plain",
                storage_uri=storage_uri,
                sha256="0" * 64,
                size_bytes=8,
                created_by="test",
            )
        )
        db.commit()

    def override_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/v1/evidence/evidence-1/download")
        assert response.status_code == 503
        assert response.json()["detail"] == "Evidence integrity verification failed"
    finally:
        app.dependency_overrides.clear()
