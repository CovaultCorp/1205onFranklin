from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessProfile, AuditLog, Company, Suite, UnifiUser, User, UserSuiteAssignment
from app.reconcile import ACTIVE_UNIFI_STATUSES, INACTIVE_UNIFI_STATUSES

BOOTSTRAP_COLUMNS = [
    "promote",
    "unifi_user_id",
    "email",
    "employee_number",
    "first_name",
    "last_name",
    "unifi_status",
    "local_status",
    "company_id",
    "company_name",
    "suite_id",
    "suite_number",
    "access_profile_id",
    "access_profile_name",
    "title",
    "department",
    "phone",
    "notes",
]


@dataclass
class BootstrapImportSummary:
    rows_seen: int = 0
    rows_skipped: int = 0
    users_created: int = 0
    users_updated: int = 0
    snapshots_linked: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "rows_seen": self.rows_seen,
            "rows_skipped": self.rows_skipped,
            "users_created": self.users_created,
            "users_updated": self.users_updated,
            "snapshots_linked": self.snapshots_linked,
            "errors": self.errors,
        }


def _norm(value: str | None) -> str:
    return (value or "").strip()


def _norm_lower(value: str | None) -> str:
    return _norm(value).lower()


def _is_truthy(value: str | None) -> bool:
    return _norm_lower(value) in {"1", "true", "yes", "y", "promote"}


def _int_or_none(value: str | None) -> int | None:
    text = _norm(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _local_status_from_unifi(status: str | None) -> str:
    normalized = _norm_lower(status)
    if normalized in ACTIVE_UNIFI_STATUSES:
        return "active"
    if normalized in INACTIVE_UNIFI_STATUSES:
        return "inactive"
    return "pending"


def _find_company(session: Session, row: dict[str, str]) -> Company | None:
    company_id = _int_or_none(row.get("company_id"))
    if company_id:
        return session.get(Company, company_id)
    company_name = _norm_lower(row.get("company_name"))
    if not company_name:
        return None
    return next(
        (company for company in session.scalars(select(Company)).all() if company.name.lower() == company_name),
        None,
    )


def _find_suite(session: Session, row: dict[str, str]) -> Suite | None:
    suite_id = _int_or_none(row.get("suite_id"))
    if suite_id:
        return session.get(Suite, suite_id)
    suite_number = _norm_lower(row.get("suite_number"))
    if not suite_number:
        return None
    return next(
        (suite for suite in session.scalars(select(Suite)).all() if suite.suite_number.lower() == suite_number),
        None,
    )


def _find_access_profile(session: Session, row: dict[str, str]) -> AccessProfile | None:
    profile_id = _int_or_none(row.get("access_profile_id"))
    if profile_id:
        return session.get(AccessProfile, profile_id)
    profile_name = _norm_lower(row.get("access_profile_name"))
    if not profile_name:
        return None
    return next(
        (profile for profile in session.scalars(select(AccessProfile)).all() if profile.name.lower() == profile_name),
        None,
    )


def _find_existing_user(session: Session, *, email: str, employee_number: str | None) -> User | None:
    if employee_number:
        user = session.scalar(select(User).where(User.employee_number == employee_number))
        if user:
            return user
    return session.scalar(select(User).where(User.email == email))


def _ensure_primary_assignment(session: Session, *, user: User, company_id: int, suite_id: int) -> None:
    existing = session.scalar(
        select(UserSuiteAssignment).where(
            UserSuiteAssignment.user_id == user.id,
            UserSuiteAssignment.suite_id == suite_id,
            UserSuiteAssignment.assignment_type == "primary",
            UserSuiteAssignment.active.is_(True),
        )
    )
    if existing:
        existing.company_id = company_id
        return
    session.add(
        UserSuiteAssignment(
            user_id=user.id,
            company_id=company_id,
            suite_id=suite_id,
            assignment_type="primary",
            active=True,
        )
    )


def export_unmatched_unifi_users_csv(session: Session) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=BOOTSTRAP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    snapshots = session.scalars(
        select(UnifiUser).where(UnifiUser.local_user_id.is_(None)).order_by(UnifiUser.email, UnifiUser.unifi_user_id)
    ).all()
    for snapshot in snapshots:
        writer.writerow(
            {
                "promote": "",
                "unifi_user_id": snapshot.unifi_user_id,
                "email": snapshot.email or "",
                "employee_number": snapshot.employee_number or "",
                "first_name": snapshot.first_name or "",
                "last_name": snapshot.last_name or "",
                "unifi_status": snapshot.status or "",
                "local_status": _local_status_from_unifi(snapshot.status),
                "company_id": "",
                "company_name": "",
                "suite_id": "",
                "suite_number": "",
                "access_profile_id": "",
                "access_profile_name": "",
                "title": "",
                "department": "",
                "phone": "",
                "notes": "",
            }
        )
    return output.getvalue()


def import_bootstrap_users_csv(
    session: Session,
    csv_text: str,
    *,
    actor_account_id: int | None = None,
    actor_email: str | None = None,
    ip_address: str | None = None,
) -> BootstrapImportSummary:
    summary = BootstrapImportSummary()
    reader = csv.DictReader(StringIO(csv_text))
    missing_columns = [column for column in BOOTSTRAP_COLUMNS if column not in (reader.fieldnames or [])]
    if missing_columns:
        summary.errors.append(f"Missing required columns: {', '.join(missing_columns)}")
        return summary

    for row_number, row in enumerate(reader, start=2):
        summary.rows_seen += 1
        if not _is_truthy(row.get("promote")):
            summary.rows_skipped += 1
            continue

        unifi_user_id = _norm(row.get("unifi_user_id"))
        email = _norm_lower(row.get("email"))
        employee_number = _norm(row.get("employee_number")) or None
        first_name = _norm(row.get("first_name"))
        last_name = _norm(row.get("last_name"))
        if not unifi_user_id or not email or not first_name or not last_name:
            summary.errors.append(f"Row {row_number}: unifi_user_id, email, first_name, and last_name are required.")
            continue

        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == unifi_user_id))
        if snapshot is None:
            summary.errors.append(f"Row {row_number}: UniFi snapshot {unifi_user_id} was not found.")
            continue
        if snapshot.local_user_id is not None:
            summary.rows_skipped += 1
            continue

        company = _find_company(session, row)
        suite = _find_suite(session, row)
        profile = _find_access_profile(session, row)
        if company is None or suite is None or profile is None:
            summary.errors.append(f"Row {row_number}: company, suite, and access profile must resolve to existing records.")
            continue

        user = _find_existing_user(session, email=email, employee_number=employee_number)
        before = None
        if user is None:
            user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                employee_number=employee_number,
                status=_norm(row.get("local_status")) or _local_status_from_unifi(snapshot.status),
            )
            session.add(user)
            summary.users_created += 1
        else:
            before = {
                "company_id": user.company_id,
                "primary_suite_id": user.primary_suite_id,
                "access_profile_id": user.access_profile_id,
                "status": user.status,
            }
            summary.users_updated += 1

        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.employee_number = employee_number
        user.company_id = company.id
        user.primary_suite_id = suite.id
        user.access_profile_id = profile.id
        user.title = _norm(row.get("title")) or user.title
        user.department = _norm(row.get("department")) or user.department
        user.phone = _norm(row.get("phone")) or user.phone
        user.notes = _norm(row.get("notes")) or user.notes
        user.status = _norm(row.get("local_status")) or _local_status_from_unifi(snapshot.status)
        session.flush()

        _ensure_primary_assignment(session, user=user, company_id=company.id, suite_id=suite.id)
        snapshot.local_user_id = user.id
        summary.snapshots_linked += 1
        session.add(
            AuditLog(
                actor_account_id=actor_account_id,
                actor_email=actor_email,
                action="bootstrap.promote_unifi_user",
                target_type="User",
                target_id=str(user.id),
                before_json=before,
                after_json={
                    "unifi_user_id": snapshot.unifi_user_id,
                    "company_id": company.id,
                    "suite_id": suite.id,
                    "access_profile_id": profile.id,
                },
                ip_address=ip_address,
            )
        )
    return summary
