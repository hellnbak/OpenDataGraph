"""OpenDataGraph v1.8 runtime governance and scale.

Revision ID: 20260731_0007
Revises: 20260731_0006
Create Date: 2026-07-31
"""

import sqlalchemy as sa

from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "20260731_0007"
down_revision = "20260731_0006"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "runtime_decision_receipts",
    "ai_resources",
    "ai_resource_relationships",
    "ai_lineage_observations",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)
    inspector = sa.inspect(bind)
    index_name = "ix_policy_exceptions_tenant_active_expires"
    existing = {
        index["name"] for index in inspector.get_indexes("policy_exceptions")
    }
    if index_name not in existing:
        op.create_index(
            index_name,
            "policy_exceptions",
            ["tenant_id", "active", "expires_at"],
        )


def downgrade() -> None:
    raise RuntimeError("v1.8 downgrades are not supported; restore a pre-upgrade backup")
