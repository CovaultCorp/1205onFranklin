"""Add Entry Point Vercel database schema.

Revision ID: 0006_entrypoint_vercel
Revises: 0005_import_batches
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_entrypoint_vercel"
down_revision = "0005_import_batches"
branch_labels = None
depends_on = None


PROPERTY_SLUG = "1205-franklin"


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {item["name"] for item in inspector.get_columns(table)}


def _add_property_column(inspector: sa.Inspector, table: str) -> None:
    if table in set(inspector.get_table_names()) and not _has_column(inspector, table, "property_id"):
        op.add_column(table, sa.Column("property_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_property_id_building_properties", table, "building_properties", ["property_id"], ["id"])


def _create_index_if_missing(inspector: sa.Inspector, table: str, name: str, columns: list[str], *, unique: bool = False) -> None:
    if table not in set(inspector.get_table_names()):
        return
    indexes = {index["name"] for index in inspector.get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "building_properties" not in tables:
        op.create_table(
            "building_properties",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("address_line1", sa.String(length=255), nullable=False),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("state", sa.String(length=64), nullable=True),
            sa.Column("postal_code", sa.String(length=32), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug", name="uq_building_properties_slug"),
        )
        op.create_index("ix_building_properties_slug", "building_properties", ["slug"])

    now = sa.func.now()
    building_properties = sa.table(
        "building_properties",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("address_line1", sa.String),
        sa.column("city", sa.String),
        sa.column("state", sa.String),
        sa.column("postal_code", sa.String),
        sa.column("status", sa.String),
        sa.column("notes", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing_property = bind.execute(sa.text("select id from building_properties where slug = :slug"), {"slug": PROPERTY_SLUG}).first()
    if existing_property is None:
        bind.execute(
            building_properties.insert().values(
                slug=PROPERTY_SLUG,
                name="ENTRY POINT",
                display_name="1205 on Franklin",
                address_line1="1205 Franklin",
                city="Tampa",
                state="FL",
                postal_code=None,
                status="active",
                notes="Seed property for Entry Point at 1205 on Franklin.",
                created_at=now,
                updated_at=now,
            )
        )

    inspector = sa.inspect(bind)
    for table in (
        "companies",
        "suites",
        "company_suites",
        "users",
        "user_suite_assignments",
        "access_profiles",
        "access_requests",
        "unifi_users",
        "sync_jobs",
    ):
        _add_property_column(inspector, table)

    inspector = sa.inspect(bind)
    if "unifi_access_policies" not in set(inspector.get_table_names()):
        op.create_table(
            "unifi_access_policies",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("unifi_policy_id", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=True),
            sa.Column("raw_snapshot_json", sa.JSON(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["building_properties.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("property_id", "unifi_policy_id", name="uq_unifi_access_policy_property_id"),
        )
        op.create_index("ix_unifi_access_policies_unifi_policy_id", "unifi_access_policies", ["unifi_policy_id"])
        op.create_index("ix_unifi_access_policies_name", "unifi_access_policies", ["name"])

    if "unifi_user_groups" not in set(inspector.get_table_names()):
        op.create_table(
            "unifi_user_groups",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("unifi_group_id", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=True),
            sa.Column("raw_snapshot_json", sa.JSON(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["building_properties.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("property_id", "unifi_group_id", name="uq_unifi_user_group_property_id"),
        )
        op.create_index("ix_unifi_user_groups_unifi_group_id", "unifi_user_groups", ["unifi_group_id"])
        op.create_index("ix_unifi_user_groups_name", "unifi_user_groups", ["name"])

    if "unifi_door_groups" not in set(inspector.get_table_names()):
        op.create_table(
            "unifi_door_groups",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("unifi_door_group_id", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("raw_snapshot_json", sa.JSON(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["building_properties.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("property_id", "unifi_door_group_id", name="uq_unifi_door_group_property_id"),
        )
        op.create_index("ix_unifi_door_groups_unifi_door_group_id", "unifi_door_groups", ["unifi_door_group_id"])
        op.create_index("ix_unifi_door_groups_name", "unifi_door_groups", ["name"])

    if "unifi_doors" not in set(inspector.get_table_names()):
        op.create_table(
            "unifi_doors",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("door_group_id", sa.Integer(), nullable=True),
            sa.Column("unifi_door_id", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=True),
            sa.Column("raw_snapshot_json", sa.JSON(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["door_group_id"], ["unifi_door_groups.id"]),
            sa.ForeignKeyConstraint(["property_id"], ["building_properties.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("property_id", "unifi_door_id", name="uq_unifi_door_property_id"),
        )
        op.create_index("ix_unifi_doors_unifi_door_id", "unifi_doors", ["unifi_door_id"])
        op.create_index("ix_unifi_doors_name", "unifi_doors", ["name"])

    if "sync_runs" not in set(inspector.get_table_names()):
        op.create_table(
            "sync_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=120), nullable=False),
            sa.Column("agent_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("summary_json", sa.JSON(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["building_properties.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "sync_snapshots" not in set(inspector.get_table_names()):
        op.create_table(
            "sync_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("sync_run_id", sa.Integer(), nullable=True),
            sa.Column("snapshot_type", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=120), nullable=False),
            sa.Column("external_id", sa.String(length=255), nullable=True),
            sa.Column("normalized_json", sa.JSON(), nullable=True),
            sa.Column("raw_snapshot_json", sa.JSON(), nullable=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["building_properties.id"]),
            sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sync_snapshots_snapshot_type", "sync_snapshots", ["snapshot_type"])
        op.create_index("ix_sync_snapshots_external_id", "sync_snapshots", ["external_id"])

    if "sync_run_logs" not in set(inspector.get_table_names()):
        op.create_table(
            "sync_run_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sync_run_id", sa.Integer(), nullable=False),
            sa.Column("level", sa.String(length=32), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("context_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "staged_access_changes" not in set(inspector.get_table_names()):
        op.create_table(
            "staged_access_changes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=True),
            sa.Column("sync_job_id", sa.Integer(), nullable=True),
            sa.Column("access_request_id", sa.Integer(), nullable=True),
            sa.Column("local_user_id", sa.Integer(), nullable=True),
            sa.Column("unifi_user_id", sa.String(length=255), nullable=True),
            sa.Column("change_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("proposed_before_json", sa.JSON(), nullable=True),
            sa.Column("proposed_after_json", sa.JSON(), nullable=True),
            sa.Column("approved_by_account_id", sa.Integer(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["access_request_id"], ["access_requests.id"]),
            sa.ForeignKeyConstraint(["approved_by_account_id"], ["portal_accounts.id"]),
            sa.ForeignKeyConstraint(["local_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["property_id"], ["building_properties.id"]),
            sa.ForeignKeyConstraint(["sync_job_id"], ["sync_jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_staged_access_changes_unifi_user_id", "staged_access_changes", ["unifi_user_id"])

    property_id = bind.execute(sa.text("select id from building_properties where slug = :slug"), {"slug": PROPERTY_SLUG}).scalar()
    if property_id:
        for table in (
            "companies",
            "suites",
            "company_suites",
            "users",
            "user_suite_assignments",
            "access_profiles",
            "access_requests",
            "unifi_users",
            "sync_jobs",
        ):
            if table in set(sa.inspect(bind).get_table_names()) and _has_column(sa.inspect(bind), table, "property_id"):
                bind.execute(sa.text(f"update {table} set property_id = :property_id where property_id is null"), {"property_id": property_id})


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in ("staged_access_changes", "sync_run_logs", "sync_snapshots", "sync_runs", "unifi_doors", "unifi_door_groups", "unifi_user_groups", "unifi_access_policies"):
        if table in tables:
            op.drop_table(table)
