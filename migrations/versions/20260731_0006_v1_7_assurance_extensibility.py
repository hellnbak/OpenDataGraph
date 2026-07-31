"""OpenDataGraph v1.7 assurance and extensibility.

Revision ID: 20260731_0006
Revises: 20260731_0005
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "20260731_0006"
down_revision = "20260731_0005"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "connector_capability_policies",
    "ownership_escalation_policies",
    "ownership_escalation_events",
)

TABLE_ADDITIONS = {
    "connector_runs": (
        sa.Column("connector_version", sa.String(length=40), nullable=True),
        sa.Column("capability_digest", sa.String(length=64), nullable=True),
        sa.Column("capability_policy_version", sa.Integer(), nullable=True),
    ),
    "governance_evidence_packages": (
        sa.Column("signing_profile", sa.String(length=120), nullable=True),
        sa.Column("signature_type", sa.String(length=40), nullable=True),
        sa.Column("signature_key_id", sa.String(length=512), nullable=True),
    ),
    "ownership_campaigns": (
        sa.Column("escalation_policy_id", sa.String(length=36), nullable=True),
    ),
    "ownership_campaign_schedules": (
        sa.Column("escalation_policy_id", sa.String(length=36), nullable=True),
    ),
    "integration_deliveries": (
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
    ),
}

INDEXES = (
    (
        "governance_evidence_packages",
        "ix_governance_evidence_packages_signing_profile",
        ("signing_profile",),
        False,
    ),
    (
        "ownership_campaigns",
        "ix_ownership_campaigns_escalation_policy_id",
        ("escalation_policy_id",),
        False,
    ),
    (
        "ownership_campaign_schedules",
        "ix_ownership_campaign_schedules_escalation_policy_id",
        ("escalation_policy_id",),
        False,
    ),
    (
        "integration_deliveries",
        "ix_integration_deliveries_idempotency_key",
        ("idempotency_key",),
        False,
    ),
    (
        "integration_deliveries",
        "uq_delivery_tenant_endpoint_idempotency",
        ("tenant_id", "endpoint_id", "idempotency_key"),
        True,
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in NEW_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)
    for table_name, additions in TABLE_ADDITIONS.items():
        inspector = sa.inspect(bind)
        if not inspector.has_table(table_name):
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing = [column for column in additions if column.name not in columns]
        if missing:
            with op.batch_alter_table(table_name) as batch:
                for column in missing:
                    batch.add_column(column)
    for table_name, index_name, columns, unique in INDEXES:
        inspector = sa.inspect(bind)
        if not inspector.has_table(table_name):
            continue
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        existing.update(
            constraint["name"]
            for constraint in inspector.get_unique_constraints(table_name)
            if constraint.get("name")
        )
        if index_name not in existing:
            op.create_index(
                index_name,
                table_name,
                list(columns),
                unique=unique,
            )


def downgrade() -> None:
    raise RuntimeError("v1.7 downgrades are not supported; restore a pre-upgrade backup")
