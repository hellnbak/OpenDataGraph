"""OpenDataGraph v1.4 product hardening.

Revision ID: 20260730_0003
Revises: 20260730_0002
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "20260730_0003"
down_revision = "20260730_0002"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "identity_deprovision_workflows",
    "policy_approver_delegations",
    "evidence_dispositions",
)

TABLE_ADDITIONS = {
    "connector_schedules": (
        (
            "schedule_type",
            sa.Column(
                "schedule_type",
                sa.String(length=40),
                nullable=False,
                server_default="interval",
            ),
        ),
        ("cron_expression", sa.Column("cron_expression", sa.String(length=120), nullable=True)),
        (
            "timezone",
            sa.Column("timezone", sa.String(length=120), nullable=False, server_default="UTC"),
        ),
        (
            "maintenance_windows_json",
            sa.Column(
                "maintenance_windows_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
        ),
    ),
    "scim_resources": (
        ("deprovisioned_at", sa.Column("deprovisioned_at", sa.DateTime(), nullable=True)),
        (
            "deprovisioned_by",
            sa.Column("deprovisioned_by", sa.String(length=320), nullable=True),
        ),
    ),
    "policy_exceptions": (
        ("renewal_status", sa.Column("renewal_status", sa.String(length=40), nullable=True)),
        (
            "renewal_requested_until",
            sa.Column("renewal_requested_until", sa.DateTime(), nullable=True),
        ),
        (
            "renewal_requested_by",
            sa.Column("renewal_requested_by", sa.String(length=320), nullable=True),
        ),
        (
            "renewal_requested_at",
            sa.Column("renewal_requested_at", sa.DateTime(), nullable=True),
        ),
        ("renewal_reason", sa.Column("renewal_reason", sa.Text(), nullable=True)),
        ("renewed_by", sa.Column("renewed_by", sa.String(length=320), nullable=True)),
        ("renewed_at", sa.Column("renewed_at", sa.DateTime(), nullable=True)),
    ),
    "integration_deliveries": (
        (
            "replayed_from",
            sa.Column("replayed_from", sa.String(length=36), nullable=True),
        ),
        ("last_attempted_at", sa.Column("last_attempted_at", sa.DateTime(), nullable=True)),
        ("dead_lettered_at", sa.Column("dead_lettered_at", sa.DateTime(), nullable=True)),
    ),
    "evidence_records": (
        (
            "object_lock_status",
            sa.Column(
                "object_lock_status",
                sa.String(length=40),
                nullable=False,
                server_default="unverified",
            ),
        ),
        (
            "object_lock_mode",
            sa.Column("object_lock_mode", sa.String(length=40), nullable=True),
        ),
        (
            "object_lock_retain_until",
            sa.Column("object_lock_retain_until", sa.DateTime(), nullable=True),
        ),
        (
            "object_lock_legal_hold",
            sa.Column("object_lock_legal_hold", sa.Boolean(), nullable=True),
        ),
        (
            "object_lock_verified_at",
            sa.Column("object_lock_verified_at", sa.DateTime(), nullable=True),
        ),
    ),
}

INDEXES = (
    ("connector_schedules", "ix_connector_schedules_schedule_type", ("schedule_type",)),
    ("scim_resources", "ix_scim_resources_deprovisioned_at", ("deprovisioned_at",)),
    ("policy_exceptions", "ix_policy_exceptions_renewal_status", ("renewal_status",)),
    ("integration_deliveries", "ix_integration_deliveries_replayed_from", ("replayed_from",)),
    (
        "integration_deliveries",
        "ix_integration_deliveries_dead_lettered_at",
        ("dead_lettered_at",),
    ),
    ("evidence_records", "ix_evidence_records_object_lock_status", ("object_lock_status",)),
    (
        "graph_edges",
        "ix_graph_edges_tenant_source",
        ("tenant_id", "source_type", "source_id"),
    ),
    (
        "graph_edges",
        "ix_graph_edges_tenant_target",
        ("tenant_id", "target_type", "target_id"),
    ),
    (
        "graph_edges",
        "ix_graph_edges_tenant_relationship",
        ("tenant_id", "relationship"),
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)

    for table_name, additions in TABLE_ADDITIONS.items():
        inspector = sa.inspect(bind)
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing = [column for name, column in additions if name not in columns]
        if missing:
            with op.batch_alter_table(table_name) as batch:
                for column in missing:
                    batch.add_column(column)

    for table_name, index_name, columns in INDEXES:
        inspector = sa.inspect(bind)
        if table_name not in inspector.get_table_names():
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, list(columns))


def downgrade() -> None:
    raise RuntimeError("v1.4 downgrades are not supported; restore a pre-upgrade backup")
