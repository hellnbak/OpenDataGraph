"""OpenDataGraph v1.5 commercial readiness.

Revision ID: 20260730_0004
Revises: 20260730_0003
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "20260730_0004"
down_revision = "20260730_0003"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "service_accounts",
    "service_account_credentials",
    "credential_rotations",
    "governance_review_tasks",
    "ownership_campaigns",
    "ownership_assignments",
    "graph_exports",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)

    inspector = sa.inspect(bind)
    integration_columns = {
        column["name"] for column in inspector.get_columns("integration_endpoints")
    }
    if "event_format" not in integration_columns:
        with op.batch_alter_table("integration_endpoints") as batch:
            batch.add_column(
                sa.Column(
                    "event_format",
                    sa.String(length=40),
                    nullable=False,
                    server_default="native",
                )
            )

    inspector = sa.inspect(bind)
    indexes = {
        index["name"] for index in inspector.get_indexes("integration_endpoints")
    }
    if "ix_integration_endpoints_event_format" not in indexes:
        op.create_index(
            "ix_integration_endpoints_event_format",
            "integration_endpoints",
            ["event_format"],
        )


def downgrade() -> None:
    raise RuntimeError("v1.5 downgrades are not supported; restore a pre-upgrade backup")
