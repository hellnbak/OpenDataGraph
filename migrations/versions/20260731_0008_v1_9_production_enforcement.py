"""OpenDataGraph v1.9 production enforcement and fleet governance.

Revision ID: 20260731_0008
Revises: 20260731_0007
Create Date: 2026-07-31
"""

import sqlalchemy as sa

from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "20260731_0008"
down_revision = "20260731_0007"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "enforcement_events",
    "policy_rollouts",
    "policy_replays",
    "genai_telemetry_events",
    "governance_outbox_events",
)

RECEIPT_COLUMNS = (
    sa.Column("replay_context_json", sa.Text(), nullable=False, server_default="{}"),
    sa.Column("replayable", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("rollout_id", sa.String(length=36), nullable=True),
    sa.Column("rollout_stage", sa.String(length=40), nullable=True),
    sa.Column("baseline_policy_decision", sa.String(length=40), nullable=True),
    sa.Column("candidate_policy_decision", sa.String(length=40), nullable=True),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"]
        for column in inspector.get_columns("runtime_decision_receipts")
    }
    for column in RECEIPT_COLUMNS:
        if column.name not in existing_columns:
            op.add_column("runtime_decision_receipts", column)
    inspector = sa.inspect(bind)
    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes("runtime_decision_receipts")
    }
    index_name = "ix_runtime_receipts_tenant_rollout_created"
    if index_name not in existing_indexes:
        op.create_index(
            index_name,
            "runtime_decision_receipts",
            ["tenant_id", "rollout_id", "created_at"],
        )
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("v1.9 downgrades are not supported; restore a pre-upgrade backup")
