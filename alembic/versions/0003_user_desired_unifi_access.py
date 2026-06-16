"""Add desired UniFi access fields to users.

Revision ID: 0003_user_desired_unifi_access
Revises: 0002_user_access_profile
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_user_desired_unifi_access"
down_revision = "0002_user_access_profile"
branch_labels = None
depends_on = None

FIELDS = (
    "desired_unifi_access_policy_ids",
    "desired_unifi_access_policy_names",
    "desired_unifi_user_group_ids",
    "desired_unifi_user_group_names",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch_op:
        for field in FIELDS:
            if field not in existing_columns:
                batch_op.add_column(sa.Column(field, sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    with op.batch_alter_table("users") as batch_op:
        for field in reversed(FIELDS):
            if field in existing_columns:
                batch_op.drop_column(field)
