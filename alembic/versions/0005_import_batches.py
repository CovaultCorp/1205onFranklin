"""Add import batch preview tables.

Revision ID: 0005_import_batches
Revises: 0004_unifi_compat
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_import_batches"
down_revision = "0004_unifi_compat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "import_batches" not in tables:
        op.create_table(
            "import_batches",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("filename", sa.String(length=500), nullable=True),
            sa.Column("created_by_account_id", sa.Integer(), nullable=True),
            sa.Column("summary_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("committed_by_account_id", sa.Integer(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["committed_by_account_id"], ["portal_accounts.id"]),
            sa.ForeignKeyConstraint(["created_by_account_id"], ["portal_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if "import_batch_rows" not in tables:
        op.create_table(
            "import_batch_rows",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("import_batch_id", sa.Integer(), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("target_type", sa.String(length=120), nullable=False),
            sa.Column("target_id", sa.String(length=120), nullable=True),
            sa.Column("unifi_user_id", sa.String(length=255), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("employee_number", sa.String(length=120), nullable=True),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("before_json", sa.JSON(), nullable=True),
            sa.Column("after_json", sa.JSON(), nullable=True),
            sa.Column("diff_json", sa.JSON(), nullable=True),
            sa.Column("validation_errors_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    inspector = sa.inspect(op.get_bind())
    indexes = {
        index["name"]
        for table in ("import_batches", "import_batch_rows")
        if table in set(inspector.get_table_names())
        for index in inspector.get_indexes(table)
    }
    if "ix_import_batches_source" not in indexes:
        op.create_index("ix_import_batches_source", "import_batches", ["source"])
    if "ix_import_batches_status" not in indexes:
        op.create_index("ix_import_batches_status", "import_batches", ["status"])
    if "ix_import_batch_rows_import_batch_id" not in indexes:
        op.create_index("ix_import_batch_rows_import_batch_id", "import_batch_rows", ["import_batch_id"])
    if "ix_import_batch_rows_action" not in indexes:
        op.create_index("ix_import_batch_rows_action", "import_batch_rows", ["action"])
    if "ix_import_batch_rows_status" not in indexes:
        op.create_index("ix_import_batch_rows_status", "import_batch_rows", ["status"])
    if "ix_import_batch_rows_unifi_user_id" not in indexes:
        op.create_index("ix_import_batch_rows_unifi_user_id", "import_batch_rows", ["unifi_user_id"])
    if "ix_import_batch_rows_email" not in indexes:
        op.create_index("ix_import_batch_rows_email", "import_batch_rows", ["email"])
    if "ix_import_batch_rows_employee_number" not in indexes:
        op.create_index("ix_import_batch_rows_employee_number", "import_batch_rows", ["employee_number"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "import_batch_rows" in tables:
        op.drop_table("import_batch_rows")
    if "import_batches" in tables:
        op.drop_table("import_batches")
