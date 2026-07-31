"""OpenDataGraph v1.3 operational hardening.

Revision ID: 20260730_0002
Revises: 20260730_0001
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "20260730_0002"
down_revision = "20260730_0001"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "connector_schedules",
    "provider_rate_limits",
    "scim_resources",
    "policy_bundles",
    "policy_exceptions",
    "integration_endpoints",
    "integration_deliveries",
    "lineage_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)

    inspector = sa.inspect(bind)
    evidence_columns = {column["name"] for column in inspector.get_columns("evidence_records")}
    additions = [
        ("retention_until", sa.Column("retention_until", sa.DateTime(), nullable=True)),
        (
            "legal_hold",
            sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        ),
        ("deleted_at", sa.Column("deleted_at", sa.DateTime(), nullable=True)),
        ("deleted_by", sa.Column("deleted_by", sa.String(length=320), nullable=True)),
        ("deletion_reason", sa.Column("deletion_reason", sa.Text(), nullable=True)),
    ]
    missing = [(name, column) for name, column in additions if name not in evidence_columns]
    if missing:
        with op.batch_alter_table("evidence_records") as batch:
            for _, column in missing:
                batch.add_column(column)

    inspector = sa.inspect(bind)
    evidence_indexes = {index["name"] for index in inspector.get_indexes("evidence_records")}
    for column_name in ("retention_until", "legal_hold", "deleted_at"):
        index_name = f"ix_evidence_records_{column_name}"
        if index_name not in evidence_indexes:
            op.create_index(index_name, "evidence_records", [column_name])


def downgrade() -> None:
    raise RuntimeError("v1.3 downgrades are not supported; restore a pre-upgrade backup")
