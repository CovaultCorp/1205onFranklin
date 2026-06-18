from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PortalAccount(TimestampMixin, Base):
    __tablename__ = "portal_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="requester")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class BuildingProperty(TimestampMixin, Base):
    __tablename__ = "building_properties"
    __table_args__ = (UniqueConstraint("slug", name="uq_building_properties_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    address_line1: Mapped[str] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(64))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active")
    notes: Mapped[str | None] = mapped_column(Text)


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    primary_contact_name: Mapped[str | None] = mapped_column(String(255))
    primary_contact_email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)

    property: Mapped[BuildingProperty | None] = relationship()


class Suite(TimestampMixin, Base):
    __tablename__ = "suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    suite_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    floor: Mapped[str | None] = mapped_column(String(64))
    building_area: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")

    property: Mapped[BuildingProperty | None] = relationship()


class CompanySuite(TimestampMixin, Base):
    __tablename__ = "company_suites"
    __table_args__ = (UniqueConstraint("company_id", "suite_id", name="uq_company_suite"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id"))
    occupancy_status: Mapped[str] = mapped_column(String(32), default="active")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship()
    suite: Mapped[Suite] = relationship()
    property: Mapped[BuildingProperty | None] = relationship()


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    employee_number: Mapped[str | None] = mapped_column(String(120), unique=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    primary_suite_id: Mapped[int | None] = mapped_column(ForeignKey("suites.id"))
    access_profile_id: Mapped[int | None] = mapped_column(ForeignKey("access_profiles.id"))
    desired_unifi_access_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    desired_unifi_access_policy_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    desired_unifi_user_group_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    desired_unifi_user_group_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    title: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    department: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    notes: Mapped[str | None] = mapped_column(Text)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_by: Mapped[str | None] = mapped_column(String(255))

    company: Mapped[Company | None] = relationship()
    primary_suite: Mapped[Suite | None] = relationship()
    access_profile: Mapped[AccessProfile | None] = relationship()
    property: Mapped[BuildingProperty | None] = relationship()


class UserSuiteAssignment(TimestampMixin, Base):
    __tablename__ = "user_suite_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    assignment_type: Mapped[str] = mapped_column(String(32), default="primary")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship()
    suite: Mapped[Suite] = relationship()
    company: Mapped[Company | None] = relationship()
    property: Mapped[BuildingProperty | None] = relationship()


class AccessProfile(TimestampMixin, Base):
    __tablename__ = "access_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    default_for_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    default_for_suite_id: Mapped[int | None] = mapped_column(ForeignKey("suites.id"))
    unifi_access_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    unifi_user_group_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    property: Mapped[BuildingProperty | None] = relationship()


class UnifiAccessPolicy(TimestampMixin, Base):
    __tablename__ = "unifi_access_policies"
    __table_args__ = (UniqueConstraint("property_id", "unifi_policy_id", name="uq_unifi_access_policy_property_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    unifi_policy_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(64))
    raw_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[BuildingProperty | None] = relationship()


class UnifiUserGroup(TimestampMixin, Base):
    __tablename__ = "unifi_user_groups"
    __table_args__ = (UniqueConstraint("property_id", "unifi_group_id", name="uq_unifi_user_group_property_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    unifi_group_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(64))
    raw_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[BuildingProperty | None] = relationship()


class UnifiDoorGroup(TimestampMixin, Base):
    __tablename__ = "unifi_door_groups"
    __table_args__ = (UniqueConstraint("property_id", "unifi_door_group_id", name="uq_unifi_door_group_property_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    unifi_door_group_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    raw_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[BuildingProperty | None] = relationship()


class UnifiDoor(TimestampMixin, Base):
    __tablename__ = "unifi_doors"
    __table_args__ = (UniqueConstraint("property_id", "unifi_door_id", name="uq_unifi_door_property_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    door_group_id: Mapped[int | None] = mapped_column(ForeignKey("unifi_door_groups.id"))
    unifi_door_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(255), index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(64))
    raw_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[BuildingProperty | None] = relationship()
    door_group: Mapped[UnifiDoorGroup | None] = relationship()


class AccessRequest(TimestampMixin, Base):
    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    request_type: Mapped[str] = mapped_column(String(64))
    requested_for_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    requested_for_first_name: Mapped[str] = mapped_column(String(120))
    requested_for_last_name: Mapped[str] = mapped_column(String(120))
    requested_for_email: Mapped[str] = mapped_column(String(255))
    requested_for_employee_number: Mapped[str | None] = mapped_column(String(120))
    requested_for_company_text: Mapped[str | None] = mapped_column(String(255))
    requested_for_suite_text: Mapped[str | None] = mapped_column(String(255))
    requested_for_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    requested_for_suite_id: Mapped[int | None] = mapped_column(ForeignKey("suites.id"))
    requested_for_department: Mapped[str | None] = mapped_column(String(255))
    requested_access_profile_id: Mapped[int | None] = mapped_column(ForeignKey("access_profiles.id"))
    requested_start_date: Mapped[date | None] = mapped_column(Date)
    requested_end_date: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default="submitted")
    requester_name: Mapped[str] = mapped_column(String(255))
    requester_email: Mapped[str] = mapped_column(String(255))
    admin_notes: Mapped[str | None] = mapped_column(Text)
    denial_reason: Mapped[str | None] = mapped_column(Text)
    approved_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denied_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company | None] = relationship(foreign_keys=[requested_for_company_id])
    suite: Mapped[Suite | None] = relationship(foreign_keys=[requested_for_suite_id])
    access_profile: Mapped[AccessProfile | None] = relationship()
    property: Mapped[BuildingProperty | None] = relationship()


class UnifiUser(TimestampMixin, Base):
    __tablename__ = "unifi_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    local_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    unifi_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    email_status: Mapped[str | None] = mapped_column(String(64))
    employee_number: Mapped[str | None] = mapped_column(String(120), index=True)
    suite_number: Mapped[str | None] = mapped_column(String(64), index=True)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    full_name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(64))
    onboard_time: Mapped[str | None] = mapped_column(String(255))
    access_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    access_policy_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    group_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    group_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    nfc_card_count: Mapped[int | None] = mapped_column(Integer)
    touch_pass_status: Mapped[str | None] = mapped_column(String(64))
    touch_pass_last_activity: Mapped[str | None] = mapped_column(String(255))
    license_plate_count: Mapped[int | None] = mapped_column(Integer)
    raw_user_json_file: Mapped[str | None] = mapped_column(String(500))
    raw_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[BuildingProperty | None] = relationship()


class SyncJob(TimestampMixin, Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    access_request_id: Mapped[int | None] = mapped_column(ForeignKey("access_requests.id"))
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), default="pending")
    proposed_actions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[BuildingProperty | None] = relationship()


class SyncRun(TimestampMixin, Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    source: Mapped[str] = mapped_column(String(120), default="local_lan_agent")
    agent_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), default="received")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text)

    property: Mapped[BuildingProperty | None] = relationship()


class SyncSnapshot(TimestampMixin, Base):
    __tablename__ = "sync_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("sync_runs.id"))
    snapshot_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(120), default="unifi_access")
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    normalized_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[BuildingProperty | None] = relationship()
    sync_run: Mapped[SyncRun | None] = relationship()


class SyncRunLog(Base):
    __tablename__ = "sync_run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("sync_runs.id"))
    level: Mapped[str] = mapped_column(String(32), default="info")
    message: Mapped[str] = mapped_column(Text)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sync_run: Mapped[SyncRun] = relationship()


class StagedAccessChange(TimestampMixin, Base):
    __tablename__ = "staged_access_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("building_properties.id"))
    sync_job_id: Mapped[int | None] = mapped_column(ForeignKey("sync_jobs.id"))
    access_request_id: Mapped[int | None] = mapped_column(ForeignKey("access_requests.id"))
    local_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    unifi_user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    change_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), default="staged")
    proposed_before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    proposed_after_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    property: Mapped[BuildingProperty | None] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    actor_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(255))
    target_type: Mapped[str] = mapped_column(String(120))
    target_id: Mapped[str | None] = mapped_column(String(120))
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="preview", index=True)
    filename: Mapped[str | None] = mapped_column(String(500))
    created_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    last_error: Mapped[str | None] = mapped_column(Text)

    rows: Mapped[list[ImportBatchRow]] = relationship(
        "ImportBatchRow",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ImportBatchRow.id",
    )


class ImportBatchRow(Base):
    __tablename__ = "import_batch_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    row_number: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(32), index=True)
    target_type: Mapped[str] = mapped_column(String(120), default="user")
    target_id: Mapped[str | None] = mapped_column(String(120))
    unifi_user_id: Mapped[str | None] = mapped_column(String(255), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    employee_number: Mapped[str | None] = mapped_column(String(120), index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    diff_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validation_errors_json: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    batch: Mapped[ImportBatch] = relationship("ImportBatch", back_populates="rows")


class Conflict(TimestampMixin, Base):
    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    unifi_user_id: Mapped[int | None] = mapped_column(ForeignKey("unifi_users.id"))
    conflict_type: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    local_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    unifi_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64), default="open")
    resolved_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportRun(TimestampMixin, Base):
    __tablename__ = "report_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_type: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(64), default="pending")
    requested_by_account_id: Mapped[int | None] = mapped_column(ForeignKey("portal_accounts.id"))
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    filters_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_csv_path: Mapped[str | None] = mapped_column(String(500))
    output_html_path: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class VerificationRequest(TimestampMixin, Base):
    __tablename__ = "verification_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_run_id: Mapped[int | None] = mapped_column(ForeignKey("report_runs.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    suite_id: Mapped[int | None] = mapped_column(ForeignKey("suites.id"))
    recipient_email: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(64), default="pending")
    verification_token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_name: Mapped[str | None] = mapped_column(String(255))
    verified_by_email: Mapped[str | None] = mapped_column(String(255))
    comments: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
