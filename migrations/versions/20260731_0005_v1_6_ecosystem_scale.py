"""OpenDataGraph v1.6 ecosystem and scale.

Revision ID: 20260731_0005
Revises: 20260730_0004
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "20260731_0005"
down_revision = "20260730_0004"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "ownership_campaign_schedules",
    "governance_evidence_packages",
)

TABLE_ADDITIONS = {
    "ownership_campaigns": (
        (
            "source_schedule_id",
            sa.Column("source_schedule_id", sa.String(length=36), nullable=True),
        ),
        (
            "notification_endpoint_ids_json",
            sa.Column(
                "notification_endpoint_ids_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
        ),
    ),
}

INDEXES = (
    (
        "service_account_credentials",
        "ix_service_account_credentials_tenant_status_expires",
        ("tenant_id", "status", "expires_at"),
    ),
    (
        "governance_review_tasks",
        "ix_governance_review_tasks_tenant_status_due",
        ("tenant_id", "status", "due_at"),
    ),
    (
        "ownership_campaigns",
        "ix_ownership_campaigns_tenant_status_due",
        ("tenant_id", "status", "due_at"),
    ),
    (
        "ownership_assignments",
        "ix_ownership_assignments_tenant_campaign_status",
        ("tenant_id", "campaign_id", "status"),
    ),
    (
        "graph_exports",
        "ix_graph_exports_tenant_status_created",
        ("tenant_id", "status", "created_at"),
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

    inspector = sa.inspect(bind)
    ownership_indexes = {
        index["name"] for index in inspector.get_indexes("ownership_campaigns")
    }
    if "ix_ownership_campaigns_source_schedule_id" not in ownership_indexes:
        op.create_index(
            "ix_ownership_campaigns_source_schedule_id",
            "ownership_campaigns",
            ["source_schedule_id"],
        )

    for table_name, index_name, columns in INDEXES:
        inspector = sa.inspect(bind)
        existing_indexes = {
            index["name"] for index in inspector.get_indexes(table_name)
        }
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, list(columns))


def downgrade() -> None:
    raise RuntimeError("v1.6 downgrades are not supported; restore a pre-upgrade backup")
