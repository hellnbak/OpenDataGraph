from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from app.config import settings


def test_initial_migration_creates_v12_schema(tmp_path, monkeypatch):
    database = tmp_path / "migration.db"
    database_url = f"sqlite:///{database}"
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    inspector = inspect(create_engine(database_url))
    assert {"background_jobs", "evidence_records", "alembic_version"} <= set(inspector.get_table_names())
    assert "tenant_id" in {column["name"] for column in inspector.get_columns("data_assets")}


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
