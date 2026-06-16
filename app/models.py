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


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    primary_contact_name: Mapped[str | None] = mapped_column(String(255))
    primary_contact_email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)


class Suite(TimestampMixin, Base):
    __tablename__ = "suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suite_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    floor: Mapped[str | None] = mapped_column(String(64))
    building_area: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")


class CompanySuite(TimestampMixin, Base):
    __tablename__ = "company_suites"
    __table_args__ = (UniqueConstraint("company_id", "suite_id", name="uq_company_suite"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id"))
    occupancy_status: Mapped[str] = mapped_column(String(32), default="active")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship()
    suite: Mapped[Suite] = relationship()


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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


class UserSuiteAssignment(TimestampMixin, Base):
    __tablename__ = "user_suite_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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


class AccessProfile(TimestampMixin, Base):
    __tablename__ = "access_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    default_for_company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    default_for_suite_id: Mapped[int | None] = mapped_column(ForeignKey("suites.id"))
    unifi_access_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    unifi_user_group_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AccessRequest(TimestampMixin, Base):
    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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


class UnifiUser(TimestampMixin, Base):
    __tablename__ = "unifi_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    unifi_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    employee_number: Mapped[str | None] = mapped_column(String(120), index=True)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str | None] = mapped_column(String(64))
    access_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncJob(TimestampMixin, Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    access_request_id: Mapped[int | None] = mapped_column(ForeignKey("access_requests.id"))
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), default="pending")
    proposed_actions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
