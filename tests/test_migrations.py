from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from app.config import settings


def test_initial_migration_creates_v16_schema(tmp_path, monkeypatch):
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
        "evidence_dispositions",
        "evidence_records",
        "identity_deprovision_workflows",
        "integration_endpoints",
        "lineage_events",
        "governance_review_tasks",
        "graph_exports",
        "governance_evidence_packages",
        "ownership_assignments",
        "ownership_campaigns",
        "ownership_campaign_schedules",
        "policy_approver_delegations",
        "policy_bundles",
        "provider_rate_limits",
        "scim_resources",
        "service_account_credentials",
        "service_accounts",
        "credential_rotations",
        "alembic_version",
    } <= set(inspector.get_table_names())
    assert "tenant_id" in {column["name"] for column in inspector.get_columns("data_assets")}
    assert {
        "retention_until",
        "legal_hold",
        "deleted_at",
        "deleted_by",
        "deletion_reason",
        "object_lock_status",
        "object_lock_verified_at",
    } <= {column["name"] for column in inspector.get_columns("evidence_records")}
    assert {
        "schedule_type",
        "cron_expression",
        "timezone",
        "maintenance_windows_json",
    } <= {column["name"] for column in inspector.get_columns("connector_schedules")}
    assert {
        "ix_graph_edges_tenant_source",
        "ix_graph_edges_tenant_target",
        "ix_graph_edges_tenant_relationship",
    } <= {index["name"] for index in inspector.get_indexes("graph_edges")}
    assert "event_format" in {
        column["name"] for column in inspector.get_columns("integration_endpoints")
    }
    assert "ix_integration_endpoints_event_format" in {
        index["name"] for index in inspector.get_indexes("integration_endpoints")
    }
    assert "uq_service_credential_id" in {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "service_account_credentials"
        )
    }
    assert {
        "source_schedule_id",
        "notification_endpoint_ids_json",
    } <= {
        column["name"] for column in inspector.get_columns("ownership_campaigns")
    }
    assert "ix_governance_review_tasks_tenant_status_due" in {
        index["name"] for index in inspector.get_indexes("governance_review_tasks")
    }


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


def test_v15_migration_preserves_native_integration_format(tmp_path, monkeypatch):
    database = tmp_path / "v14.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url)
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260730_0003")
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_integration_endpoints_event_format"))
        connection.execute(
            text("ALTER TABLE integration_endpoints DROP COLUMN event_format")
        )
        for table_name in (
            "service_accounts",
            "service_account_credentials",
            "credential_rotations",
            "governance_review_tasks",
            "ownership_campaigns",
            "ownership_assignments",
            "graph_exports",
        ):
            connection.execute(text(f"DROP TABLE {table_name}"))
        connection.execute(
            text(
                "INSERT INTO integration_endpoints "
                "(tenant_id, endpoint_id, name, endpoint_type, mode, url, "
                "events_json, enabled, created_by, created_at, updated_at) "
                "VALUES ('tenant-a', 'endpoint-1', 'existing', 'webhook', "
                "'observe', 'https://alerts.example.test/events', '[]', 1, "
                "'admin', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert {
        "service_accounts",
        "governance_review_tasks",
        "ownership_campaigns",
        "graph_exports",
    } <= set(inspector.get_table_names())
    with engine.connect() as connection:
        event_format = connection.scalar(
            text(
                "SELECT event_format FROM integration_endpoints "
                "WHERE endpoint_id = 'endpoint-1'"
            )
        )
    assert event_format == "native"


def test_v16_migration_upgrades_v15_schema(tmp_path, monkeypatch):
    database = tmp_path / "v15.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url)
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260730_0004")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE ownership_campaign_schedules"))
        connection.execute(text("DROP TABLE governance_evidence_packages"))
        connection.execute(text("DROP INDEX ix_ownership_campaigns_source_schedule_id"))
        connection.execute(text("ALTER TABLE ownership_campaigns DROP COLUMN source_schedule_id"))
        connection.execute(
            text(
                "ALTER TABLE ownership_campaigns "
                "DROP COLUMN notification_endpoint_ids_json"
            )
        )
        for index_name in (
            "ix_service_account_credentials_tenant_status_expires",
            "ix_governance_review_tasks_tenant_status_due",
            "ix_ownership_campaigns_tenant_status_due",
            "ix_ownership_assignments_tenant_campaign_status",
            "ix_graph_exports_tenant_status_created",
        ):
            connection.execute(text(f"DROP INDEX {index_name}"))

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert {
        "ownership_campaign_schedules",
        "governance_evidence_packages",
    } <= set(inspector.get_table_names())
    assert {
        "source_schedule_id",
        "notification_endpoint_ids_json",
    } <= {
        column["name"] for column in inspector.get_columns("ownership_campaigns")
    }
    assert "ix_graph_exports_tenant_status_created" in {
        index["name"] for index in inspector.get_indexes("graph_exports")
    }
