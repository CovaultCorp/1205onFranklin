from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessProfile, AuditLog, Company, Suite, UnifiUser, User, UserSuiteAssignment
from app.reconcile import ACTIVE_UNIFI_STATUSES, INACTIVE_UNIFI_STATUSES

COMPANY_FIELDS = ["id", "name", "legal_name", "status", "primary_contact_name", "primary_contact_email", "phone", "notes"]
SUITE_FIELDS = ["id", "suite_number", "floor", "building_area", "description", "status"]
ACCESS_PROFILE_FIELDS = ["id", "name", "description", "active", "unifi_access_policy_ids", "unifi_user_group_ids"]
UNIFI_REFERENCE_FIELDS = ["id", "name"]
BOOTSTRAP_COLUMNS = [
    "unifi_user_id",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "employee_number",
    "unifi_status",
    "current_unifi_access_policy_ids",
    "current_unifi_access_policy_names",
    "current_unifi_user_group_ids",
    "current_unifi_user_group_names",
    "promote",
    "company_id",
    "company_name",
    "suite_id",
    "suite_number",
    "access_profile_id",
    "access_profile_name",
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
    return _normalize_lookup(value)


def _normalize_lookup(value: str | None) -> str:
    return " ".join(_norm(value).casefold().split())


def _is_truthy(value: str | None) -> bool:
    return _norm_lower(value) in {"1", "true", "yes", "y", "promote"}


def _local_status_from_unifi(status: str | None) -> str:
    normalized = _norm_lower(status)
    if normalized in ACTIVE_UNIFI_STATUSES:
        return "active"
    if normalized in INACTIVE_UNIFI_STATUSES:
        return "inactive"
    return "pending"


def _resolve_reference(
    session: Session,
    row: dict[str, str],
    *,
    row_number: int,
    model: type[Company] | type[Suite] | type[AccessProfile],
    label: str,
    id_field: str,
    name_field: str,
    name_attribute: str,
    errors: list[str],
) -> Company | Suite | AccessProfile | None:
    raw_id = _norm(row.get(id_field))
    if raw_id:
        try:
            reference_id = int(raw_id)
        except ValueError:
            errors.append(f"Row {row_number}: {id_field} must be an integer.")
            return None
        found = session.get(model, reference_id)
        if found is None:
            errors.append(f"Row {row_number}: {label} id {reference_id} was not found.")
        return found

    raw_name = _norm(row.get(name_field))
    if not raw_name:
        errors.append(f"Row {row_number}: {label} reference is required; provide {id_field} or {name_field}.")
        return None

    normalized_name = _normalize_lookup(raw_name)
    matches = [
        item
        for item in session.scalars(select(model)).all()
        if _normalize_lookup(getattr(item, name_attribute) or "") == normalized_name
    ]
    if not matches:
        errors.append(f"Row {row_number}: {label} name {raw_name!r} was not found.")
        return None
    if len(matches) > 1:
        errors.append(f"Row {row_number}: {label} name {raw_name!r} is ambiguous.")
        return None
    return matches[0]


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


def build_bootstrap_reference_zip(
    session: Session,
    *,
    unifi_access_policies: list[dict[str, Any]] | None = None,
    unifi_user_groups: list[dict[str, Any]] | None = None,
) -> bytes:
    policies = unifi_access_policies or []
    groups = unifi_user_groups or []
    policy_names_by_id = _names_by_id(policies)
    group_names_by_id = _names_by_id(groups)
    files = {
        "companies.csv": _csv_text(COMPANY_FIELDS, _company_rows(session)),
        "suites.csv": _csv_text(SUITE_FIELDS, _suite_rows(session)),
        "access_profiles.csv": _csv_text(ACCESS_PROFILE_FIELDS, _access_profile_rows(session)),
        "unifi_access_policies.csv": _csv_text(UNIFI_REFERENCE_FIELDS, _unifi_reference_rows(policies)),
        "unifi_user_groups.csv": _csv_text(UNIFI_REFERENCE_FIELDS, _unifi_reference_rows(groups)),
        "unmatched_unifi_users.csv": export_unmatched_unifi_users_csv(
            session,
            policy_names_by_id=policy_names_by_id,
            group_names_by_id=group_names_by_id,
        ),
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            zip_file.writestr(filename, content)
    return archive.getvalue()


def export_unmatched_unifi_users_csv(
    session: Session,
    *,
    policy_names_by_id: dict[str, str] | None = None,
    group_names_by_id: dict[str, str] | None = None,
) -> str:
    policy_names_by_id = policy_names_by_id or {}
    group_names_by_id = group_names_by_id or {}
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=BOOTSTRAP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    snapshots = session.scalars(
        select(UnifiUser).where(UnifiUser.local_user_id.is_(None)).order_by(UnifiUser.email, UnifiUser.unifi_user_id)
    ).all()
    for snapshot in snapshots:
        raw_snapshot = snapshot.raw_snapshot_json or {}
        policy_ids = [str(value) for value in (snapshot.access_policy_ids or _extract_item_ids(raw_snapshot, ("access_policy", "access_policies", "accessPolicy", "accessPolicies")))]
        policy_names = _names_for_ids(policy_ids, policy_names_by_id) or _extract_item_names(
            raw_snapshot, ("access_policy", "access_policies", "accessPolicy", "accessPolicies")
        )
        group_ids = _extract_item_ids(raw_snapshot, ("groups", "user_groups", "userGroups", "department", "departments"))
        group_names = _names_for_ids(group_ids, group_names_by_id) or _extract_item_names(
            raw_snapshot, ("groups", "user_groups", "userGroups", "department", "departments")
        )
        full_name = _norm(raw_snapshot.get("full_name") or raw_snapshot.get("fullName") or raw_snapshot.get("name")) or " ".join(
            part for part in (snapshot.first_name, snapshot.last_name) if part
        )
        writer.writerow(
            {
                "unifi_user_id": snapshot.unifi_user_id,
                "first_name": snapshot.first_name or "",
                "last_name": snapshot.last_name or "",
                "full_name": full_name,
                "email": snapshot.email or "",
                "employee_number": snapshot.employee_number or "",
                "unifi_status": snapshot.status or "",
                "current_unifi_access_policy_ids": _join(policy_ids),
                "current_unifi_access_policy_names": _join(policy_names),
                "current_unifi_user_group_ids": _join(group_ids),
                "current_unifi_user_group_names": _join(group_names),
                "promote": "",
                "company_id": "",
                "company_name": "",
                "suite_id": "",
                "suite_number": "",
                "access_profile_id": "",
                "access_profile_name": "",
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

        row_errors: list[str] = []
        company = _resolve_reference(
            session,
            row,
            row_number=row_number,
            model=Company,
            label="company",
            id_field="company_id",
            name_field="company_name",
            name_attribute="name",
            errors=row_errors,
        )
        suite = _resolve_reference(
            session,
            row,
            row_number=row_number,
            model=Suite,
            label="suite",
            id_field="suite_id",
            name_field="suite_number",
            name_attribute="suite_number",
            errors=row_errors,
        )
        profile = _resolve_reference(
            session,
            row,
            row_number=row_number,
            model=AccessProfile,
            label="access profile",
            id_field="access_profile_id",
            name_field="access_profile_name",
            name_attribute="name",
            errors=row_errors,
        )
        if company is None or suite is None or profile is None:
            summary.errors.extend(row_errors)
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


def _company_rows(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": company.id,
            "name": company.name,
            "legal_name": company.legal_name,
            "status": company.status,
            "primary_contact_name": company.primary_contact_name,
            "primary_contact_email": company.primary_contact_email,
            "phone": company.phone,
            "notes": company.notes,
        }
        for company in session.scalars(select(Company).order_by(Company.name)).all()
    ]


def _suite_rows(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": suite.id,
            "suite_number": suite.suite_number,
            "floor": suite.floor,
            "building_area": suite.building_area,
            "description": suite.description,
            "status": suite.status,
        }
        for suite in session.scalars(select(Suite).order_by(Suite.suite_number)).all()
    ]


def _access_profile_rows(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "active": profile.active,
            "unifi_access_policy_ids": _join(profile.unifi_access_policy_ids),
            "unifi_user_group_ids": _join(profile.unifi_user_group_ids),
        }
        for profile in session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all()
    ]


def _unifi_reference_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": _item_id(item), "name": _item_name(item)} for item in items]


def _csv_text(fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows([{key: "" if value is None else value for key, value in row.items()} for row in rows])
    return output.getvalue()


def _names_by_id(items: list[dict[str, Any]]) -> dict[str, str]:
    return {str(_item_id(item)): _item_name(item) for item in items if _item_id(item)}


def _item_id(item: dict[str, Any]) -> str:
    return _norm(item.get("id") or item.get("policy_id") or item.get("policyId") or item.get("group_id") or item.get("groupId") or item.get("uuid"))


def _item_name(item: dict[str, Any]) -> str:
    return _norm(
        item.get("name")
        or item.get("display_name")
        or item.get("displayName")
        or item.get("policy_name")
        or item.get("policyName")
        or item.get("group_name")
        or item.get("groupName")
    )


def _extract_item_ids(snapshot: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [_item_id(item) for item in _extract_items(snapshot, keys) if _item_id(item)]


def _extract_item_names(snapshot: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [_item_name(item) for item in _extract_items(snapshot, keys) if _item_name(item)]


def _extract_items(snapshot: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = snapshot.get(key)
        if isinstance(value, list):
            return [item if isinstance(item, dict) else {"id": item, "name": item} for item in value]
        if isinstance(value, dict):
            return [value]
        if value not in (None, ""):
            return [{"id": value, "name": value}]
    return []


def _names_for_ids(ids: list[str], names_by_id: dict[str, str]) -> list[str]:
    return [names_by_id[item_id] for item_id in ids if names_by_id.get(item_id)]


def _join(values: list[Any]) -> str:
    return ";".join(str(value) for value in values if value not in (None, ""))
