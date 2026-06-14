"""Add per-user access profile.

Revision ID: 0002_user_access_profile
Revises: 0001_phase1_schema
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_user_access_profile"
down_revision = "0001_phase1_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if any(column["name"] == "access_profile_id" for column in inspector.get_columns("users")):
        return
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("access_profile_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_users_access_profile_id", "access_profiles", ["access_profile_id"], ["id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not any(column["name"] == "access_profile_id" for column in inspector.get_columns("users")):
        return
    with op.batch_alter_table("users") as batch_op:
        if any(fk.get("name") == "fk_users_access_profile_id" for fk in inspector.get_foreign_keys("users")):
            batch_op.drop_constraint("fk_users_access_profile_id", type_="foreignkey")
        batch_op.drop_column("access_profile_id")
