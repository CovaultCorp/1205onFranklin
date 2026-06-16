"""Add UniFi exporter compatibility snapshot fields.

Revision ID: 0004_unifi_user_exporter_compat_fields
Revises: 0003_user_desired_unifi_access
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_unifi_user_exporter_compat_fields"
down_revision = "0003_user_desired_unifi_access"
branch_labels = None
depends_on = None

COLUMNS = (
    sa.Column("email_status", sa.String(length=64), nullable=True),
    sa.Column("suite_number", sa.String(length=64), nullable=True),
    sa.Column("full_name", sa.String(length=255), nullable=True),
    sa.Column("phone", sa.String(length=64), nullable=True),
    sa.Column("username", sa.String(length=255), nullable=True),
    sa.Column("alias", sa.String(length=255), nullable=True),
    sa.Column("onboard_time", sa.String(length=255), nullable=True),
    sa.Column("access_policy_names", sa.JSON(), nullable=True),
    sa.Column("group_ids", sa.JSON(), nullable=True),
    sa.Column("group_names", sa.JSON(), nullable=True),
    sa.Column("nfc_card_count", sa.Integer(), nullable=True),
    sa.Column("touch_pass_status", sa.String(length=64), nullable=True),
    sa.Column("touch_pass_last_activity", sa.String(length=255), nullable=True),
    sa.Column("license_plate_count", sa.Integer(), nullable=True),
    sa.Column("raw_user_json_file", sa.String(length=500), nullable=True),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("unifi_users")}
    with op.batch_alter_table("unifi_users") as batch_op:
        for column in COLUMNS:
            if column.name not in existing_columns:
                batch_op.add_column(column.copy())
    indexes = {index["name"] for index in inspector.get_indexes("unifi_users")}
    if "ix_unifi_users_suite_number" not in indexes:
        op.create_index("ix_unifi_users_suite_number", "unifi_users", ["suite_number"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("unifi_users")}
    if "ix_unifi_users_suite_number" in indexes:
        op.drop_index("ix_unifi_users_suite_number", table_name="unifi_users")
    existing_columns = {column["name"] for column in inspector.get_columns("unifi_users")}
    with op.batch_alter_table("unifi_users") as batch_op:
        for column in reversed(COLUMNS):
            if column.name in existing_columns:
                batch_op.drop_column(column.name)
