"""OpenDataGraph v1.2 enterprise foundation.

Revision ID: 20260730_0001
Revises:
Create Date: 2026-07-30
"""

import os
import re

import sqlalchemy as sa
from alembic import op

from app.database import Base
from app import models  # noqa: F401


revision = "20260730_0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "data_assets",
    "ai_agents",
    "decision_audits",
    "connector_runs",
    "classification_reviews",
    "ai_usage_events",
    "graph_edges",
)

TENANT_UNIQUES = {
    "data_assets": ("external_id", "uq_asset_tenant_external_id"),
    "ai_agents": ("key", "uq_agent_tenant_key"),
    "ai_usage_events": ("event_id", "uq_usage_event_tenant_event_id"),
}


def _replace_global_unique(
    bind,
    table_name: str,
    value_column: str,
    constraint_name: str,
) -> None:
    inspector = sa.inspect(bind)
    unique_constraints = inspector.get_unique_constraints(table_name)
    if any(constraint["column_names"] == ["tenant_id", value_column] for constraint in unique_constraints):
        return

    old_constraint = next(
        (
            constraint
            for constraint in unique_constraints
            if constraint["column_names"] == [value_column]
        ),
        None,
    )
    naming_convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table(
        table_name,
        naming_convention=naming_convention,
        recreate="always" if bind.dialect.name == "sqlite" else "auto",
    ) as batch:
        if old_constraint:
            reflected_name = old_constraint["name"] or f"uq_{table_name}_{value_column}"
            batch.drop_constraint(reflected_name, type_="unique")
        batch.create_unique_constraint(constraint_name, ["tenant_id", value_column])


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    Base.metadata.create_all(bind=bind)
    inspector = sa.inspect(bind)
    default_tenant = os.getenv("ODG_DEFAULT_TENANT", "default")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", default_tenant):
        default_tenant = "default"
    for table_name in TENANT_TABLES:
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "tenant_id" not in columns:
            op.add_column(
                table_name,
                sa.Column(
                    "tenant_id",
                    sa.String(length=120),
                    nullable=False,
                    server_default=default_tenant,
                ),
            )
            op.create_index(f"ix_{table_name}_tenant_id", table_name, ["tenant_id"])
        if table_name in existing_tables and table_name in TENANT_UNIQUES:
            value_column, constraint_name = TENANT_UNIQUES[table_name]
            _replace_global_unique(bind, table_name, value_column, constraint_name)


def downgrade() -> None:
    raise RuntimeError("v1.2 downgrades are not supported; restore a pre-upgrade backup")
