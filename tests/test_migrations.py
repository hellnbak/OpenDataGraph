from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from app.config import settings


def test_initial_migration_creates_v13_schema(tmp_path, monkeypatch):
    database = tmp_path / "migration.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    inspector = inspect(create_engine(database_url))
    assert {
        "background_jobs",
        "connector_schedules",
        "evidence_records",
        "integration_endpoints",
        "lineage_events",
        "policy_bundles",
        "provider_rate_limits",
        "scim_resources",
        "alembic_version",
    } <= set(inspector.get_table_names())
    assert "tenant_id" in {column["name"] for column in inspector.get_columns("data_assets")}
    assert {
        "retention_until",
        "legal_hold",
        "deleted_at",
        "deleted_by",
        "deletion_reason",
    } <= {column["name"] for column in inspector.get_columns("evidence_records")}


def test_migration_upgrades_v11_global_uniqueness(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url)
    legacy = MetaData()
    Table(
        "data_assets",
        legacy,
        Column("id", Integer, primary_key=True),
        Column("external_id", String(1024), unique=True, nullable=False),
    )
    Table(
        "ai_agents",
        legacy,
        Column("id", Integer, primary_key=True),
        Column("key", String(120), unique=True, nullable=False),
    )
    Table(
        "ai_usage_events",
        legacy,
        Column("id", Integer, primary_key=True),
        Column("event_id", String(240), unique=True, nullable=False),
    )
    legacy.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO data_assets (external_id) VALUES ('asset-1')"))
        connection.execute(text("INSERT INTO ai_agents (key) VALUES ('agent-1')"))
        connection.execute(text("INSERT INTO ai_usage_events (event_id) VALUES ('event-1')"))

    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    inspector = inspect(engine)
    for table_name in ("data_assets", "ai_agents", "ai_usage_events"):
        assert "tenant_id" in {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO data_assets (tenant_id, external_id) "
                "VALUES ('tenant-b', 'asset-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO ai_agents (tenant_id, key) "
                "VALUES ('tenant-b', 'agent-1')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO ai_usage_events (tenant_id, event_id) "
                "VALUES ('tenant-b', 'event-1')"
            )
        )


def test_v13_migration_adds_evidence_governance_to_v12_database(tmp_path, monkeypatch):
    database = tmp_path / "v12.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url)
    legacy = MetaData()
    Table(
        "evidence_records",
        legacy,
        Column("id", Integer, primary_key=True),
        Column("evidence_id", String(36), nullable=False),
    )
    Table(
        "alembic_version",
        legacy,
        Column("version_num", String(32), primary_key=True),
    )
    legacy.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260730_0001')")
        )

    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert {"retention_until", "legal_hold", "deleted_at"} <= {
        column["name"] for column in inspector.get_columns("evidence_records")
    }
    assert "connector_schedules" in inspector.get_table_names()
