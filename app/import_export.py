from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Company, Suite, UnifiUser, User, UserSuiteAssignment
from app.reconcile import ACTIVE_UNIFI_STATUSES, INACTIVE_UNIFI_STATUSES

COMPANY_FIELDS = ["id", "name", "legal_name", "status", "primary_contact_name", "primary_contact_email", "phone", "notes"]
SUITE_FIELDS = ["id", "suite_number", "floor", "building_area", "description", "status"]
UNIFI_REFERENCE_FIELDS = ["id", "name", "description", "status"]
BOOTSTRAP_COLUMNS = [
    "id",
    "unifi_user_id",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "email_status",
    "employee_number",
    "suite_number",
    "phone",
    "username",
    "alias",
    "status",
    "onboard_time",
    "access_policy_ids",
    "access_policy_names",
    "group_ids",
    "group_names",
    "nfc_card_count",
    "touch_pass_status",
    "touch_pass_last_activity",
    "license_plate_count",
    "raw_user_json_file",
    "linked_local_user_id",
    "is_linked",
    "promote",
    "update_existing",
    "company_id",
    "company_name",
    "local_suite_id",
    "local_suite_number",
    "desired_unifi_access_policy_ids",
    "desired_unifi_access_policy_names",
    "desired_unifi_user_group_ids",
    "desired_unifi_user_group_names",
    "user_status",
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


def build_bootstrap_reference_zip(
    session: Session,
    *,
    unifi_access_policies: list[dict[str, Any]] | None = None,
    unifi_user_groups: list[dict[str, Any]] | None = None,
) -> bytes:
    policies = unifi_access_policies or []
    groups = unifi_user_groups or []
    files = {
        "all_unifi_users.csv": export_all_unifi_users_csv(
            session,
            unifi_access_policies=policies,
            unifi_user_groups=groups,
        ),
        "companies.csv": _csv_text(COMPANY_FIELDS, _company_rows(session)),
        "suites.csv": _csv_text(SUITE_FIELDS, _suite_rows(session)),
        "unifi_access_policies.csv": _csv_text(UNIFI_REFERENCE_FIELDS, _unifi_reference_rows(policies)),
        "unifi_user_groups.csv": _csv_text(UNIFI_REFERENCE_FIELDS, _unifi_reference_rows(groups)),
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files.items():
            zip_file.writestr(filename, content)
    return archive.getvalue()


def export_all_unifi_users_csv(
    session: Session,
    *,
    unifi_access_policies: list[dict[str, Any]] | None = None,
    unifi_user_groups: list[dict[str, Any]] | None = None,
) -> str:
    policy_names_by_id = _names_by_id(unifi_access_policies or [])
    group_names_by_id = _names_by_id(unifi_user_groups or [])
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=BOOTSTRAP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    snapshots = session.scalars(select(UnifiUser).order_by(UnifiUser.email, UnifiUser.unifi_user_id)).all()
    for snapshot in snapshots:
        writer.writerow(_unifi_user_export_row(session, snapshot, policy_names_by_id, group_names_by_id))
    return output.getvalue()


def export_unmatched_unifi_users_csv(session: Session, **kwargs: Any) -> str:
    return export_all_unifi_users_csv(session, **kwargs)


def import_bootstrap_users_csv(
    session: Session,
    csv_text: str,
    *,
    unifi_access_policies: list[dict[str, Any]] | None = None,
    unifi_user_groups: list[dict[str, Any]] | None = None,
    actor_account_id: int | None = None,
    actor_email: str | None = None,
    ip_address: str | None = None,
) -> BootstrapImportSummary:
    summary = BootstrapImportSummary()
    reader = csv.DictReader(StringIO(csv_text))
    fieldnames = reader.fieldnames or []
    if "id" not in fieldnames and "unifi_user_id" not in fieldnames:
        summary.errors.append("Missing required column: id or unifi_user_id")
        return summary

    policy_refs = unifi_access_policies or []
    group_refs = unifi_user_groups or []

    for row_number, row in enumerate(reader, start=2):
        summary.rows_seen += 1
        promote = _is_truthy(row.get("promote"))
        update_existing = _is_truthy(row.get("update_existing"))
        if not promote and not update_existing:
            summary.rows_skipped += 1
            continue

        unifi_user_id = _norm(row.get("unifi_user_id")) or _norm(row.get("id"))
        if not unifi_user_id:
            summary.errors.append(f"Row {row_number}: id or unifi_user_id is required.")
            continue
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == unifi_user_id))
        if snapshot is None:
            summary.errors.append(f"Row {row_number}: UniFi snapshot {unifi_user_id} was not found.")
            continue
        _apply_snapshot_current_fields(snapshot, row, policy_refs=policy_refs, group_refs=group_refs)

        linked_user = session.get(User, snapshot.local_user_id) if snapshot.local_user_id else None
        if linked_user and not update_existing:
            summary.rows_skipped += 1
            continue
        if not linked_user and update_existing and not promote:
            summary.errors.append(f"Row {row_number}: UniFi user {unifi_user_id} is not linked; use promote=yes to create or link a local registry user.")
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
            required=promote or _has_any(row, "company_id", "company_name"),
            errors=row_errors,
        )
        suite_lookup_row = dict(row)
        suite_lookup_row["local_suite_id"] = _norm(row.get("local_suite_id")) or _norm(row.get("suite_id"))
        suite_lookup_row["local_suite_number"] = _norm(row.get("local_suite_number")) or _norm(row.get("suite_number"))
        suite = _resolve_reference(
            session,
            suite_lookup_row,
            row_number=row_number,
            model=Suite,
            label="suite",
            id_field="local_suite_id",
            name_field="local_suite_number",
            name_attribute="suite_number",
            required=promote or _has_any(suite_lookup_row, "local_suite_id", "local_suite_number"),
            errors=row_errors,
        )
        desired_policy_ids, desired_policy_names = _resolve_unifi_selection(
            row,
            row_number=row_number,
            label="UniFi Access Policy",
            id_field="desired_unifi_access_policy_ids",
            name_field="desired_unifi_access_policy_names",
            references=policy_refs,
            errors=row_errors,
        )
        desired_group_ids, desired_group_names = _resolve_unifi_selection(
            row,
            row_number=row_number,
            label="UniFi User Group",
            id_field="desired_unifi_user_group_ids",
            name_field="desired_unifi_user_group_names",
            references=group_refs,
            errors=row_errors,
        )
        if row_errors:
            summary.errors.extend(row_errors)
            continue

        user = linked_user
        if user is None:
            user = _find_existing_user(
                session,
                email=_norm_lower(row.get("email")),
                employee_number=_norm(row.get("employee_number")) or snapshot.employee_number,
            )
        before = _local_before(user)
        if user is None:
            if not (_norm_lower(row.get("email")) or snapshot.email):
                summary.errors.append(f"Row {row_number}: email is required to create a new local registry user.")
                continue
            user = _new_user_from_row(row, snapshot)
            session.add(user)
            summary.users_created += 1
        elif user is not linked_user:
            summary.users_updated += 1
        elif update_existing:
            summary.users_updated += 1

        _apply_registry_fields(
            user,
            row,
            snapshot=snapshot,
            company=company,
            suite=suite,
            desired_policy_ids=desired_policy_ids,
            desired_policy_names=desired_policy_names,
            desired_group_ids=desired_group_ids,
            desired_group_names=desired_group_names,
            update_existing=update_existing,
        )
        session.flush()

        if company and suite:
            _ensure_primary_assignment(session, user=user, company_id=company.id, suite_id=suite.id)
        if snapshot.local_user_id != user.id:
            snapshot.local_user_id = user.id
            summary.snapshots_linked += 1

        session.add(
            AuditLog(
                actor_account_id=actor_account_id,
                actor_email=actor_email,
                action="bootstrap.update_local_registry_user" if update_existing and linked_user else "bootstrap.promote_unifi_user",
                target_type="User",
                target_id=str(user.id),
                before_json=before,
                after_json={
                    "unifi_user_id": snapshot.unifi_user_id,
                    "company_id": user.company_id,
                    "suite_id": user.primary_suite_id,
                    "desired_unifi_access_policy_ids": user.desired_unifi_access_policy_ids or [],
                    "desired_unifi_user_group_ids": user.desired_unifi_user_group_ids or [],
                },
                ip_address=ip_address,
            )
        )
    return summary


def _unifi_user_export_row(
    session: Session,
    snapshot: UnifiUser,
    policy_names_by_id: dict[str, str],
    group_names_by_id: dict[str, str],
) -> dict[str, Any]:
    raw_snapshot = snapshot.raw_snapshot_json or {}
    linked_user = session.get(User, snapshot.local_user_id) if snapshot.local_user_id else None
    company = linked_user.company if linked_user else None
    suite = linked_user.primary_suite if linked_user else None
    policy_ids = [str(value) for value in (snapshot.access_policy_ids or [])]
    policy_names = snapshot.access_policy_names or _names_for_ids(policy_ids, policy_names_by_id) or _extract_item_names(
        raw_snapshot, ("access_policy", "access_policies", "accessPolicy", "accessPolicies")
    )
    group_ids = [str(value) for value in (snapshot.group_ids or [])]
    group_names = snapshot.group_names or _names_for_ids(group_ids, group_names_by_id) or _extract_item_names(
        raw_snapshot, ("groups", "user_groups", "userGroups", "department", "departments")
    )
    full_name = snapshot.full_name or _norm(_first_present(raw_snapshot, ("full_name", "fullName", "name", "display_name", "displayName"))) or " ".join(
        part for part in (snapshot.first_name, snapshot.last_name) if part
    )
    return {
        "id": snapshot.unifi_user_id,
        "unifi_user_id": snapshot.unifi_user_id,
        "first_name": snapshot.first_name or "",
        "last_name": snapshot.last_name or "",
        "full_name": full_name,
        "email": snapshot.email or "",
        "email_status": snapshot.email_status or "",
        "employee_number": snapshot.employee_number or "",
        "suite_number": snapshot.suite_number or "",
        "phone": snapshot.phone or "",
        "username": snapshot.username or "",
        "alias": snapshot.alias or "",
        "status": snapshot.status or "",
        "onboard_time": snapshot.onboard_time or "",
        "access_policy_ids": _join(policy_ids),
        "access_policy_names": _join(policy_names),
        "group_ids": _join(group_ids),
        "group_names": _join(group_names),
        "nfc_card_count": snapshot.nfc_card_count if snapshot.nfc_card_count is not None else "",
        "touch_pass_status": snapshot.touch_pass_status or "",
        "touch_pass_last_activity": snapshot.touch_pass_last_activity or "",
        "license_plate_count": snapshot.license_plate_count if snapshot.license_plate_count is not None else "",
        "raw_user_json_file": snapshot.raw_user_json_file or f"unifi_users:{snapshot.id}",
        "linked_local_user_id": linked_user.id if linked_user else "",
        "is_linked": "yes" if linked_user else "no",
        "promote": "",
        "update_existing": "",
        "company_id": linked_user.company_id if linked_user and linked_user.company_id else "",
        "company_name": company.name if company else "",
        "local_suite_id": linked_user.primary_suite_id if linked_user and linked_user.primary_suite_id else "",
        "local_suite_number": suite.suite_number if suite else "",
        "desired_unifi_access_policy_ids": _join(linked_user.desired_unifi_access_policy_ids or []) if linked_user else "",
        "desired_unifi_access_policy_names": _join(linked_user.desired_unifi_access_policy_names or []) if linked_user else "",
        "desired_unifi_user_group_ids": _join(linked_user.desired_unifi_user_group_ids or []) if linked_user else "",
        "desired_unifi_user_group_names": _join(linked_user.desired_unifi_user_group_names or []) if linked_user else "",
        "user_status": linked_user.status if linked_user else "",
        "notes": linked_user.notes if linked_user and linked_user.notes else "",
    }


def _new_user_from_row(row: dict[str, str], snapshot: UnifiUser) -> User:
    first_name = _norm(row.get("first_name")) or snapshot.first_name or "Unknown"
    last_name = _norm(row.get("last_name")) or snapshot.last_name or "Unknown"
    email = _norm_lower(row.get("email")) or snapshot.email
    if not email:
        raise ValueError("Bootstrap import requires an email for new local users.")
    return User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        employee_number=_norm(row.get("employee_number")) or snapshot.employee_number,
        status=_norm(row.get("user_status")) or _local_status_from_unifi(snapshot.status),
    )


def _apply_registry_fields(
    user: User,
    row: dict[str, str],
    *,
    snapshot: UnifiUser,
    company: Company | None,
    suite: Suite | None,
    desired_policy_ids: list[str],
    desired_policy_names: list[str],
    desired_group_ids: list[str],
    desired_group_names: list[str],
    update_existing: bool,
) -> None:
    user.first_name = _norm(row.get("first_name")) or user.first_name or snapshot.first_name or "Unknown"
    user.last_name = _norm(row.get("last_name")) or user.last_name or snapshot.last_name or "Unknown"
    user.email = _norm_lower(row.get("email")) or user.email or snapshot.email
    user.employee_number = _norm(row.get("employee_number")) or user.employee_number or snapshot.employee_number
    if company:
        user.company_id = company.id
    if suite:
        user.primary_suite_id = suite.id
    if desired_policy_ids or desired_policy_names or not update_existing:
        user.desired_unifi_access_policy_ids = desired_policy_ids
        user.desired_unifi_access_policy_names = desired_policy_names
    if desired_group_ids or desired_group_names or not update_existing:
        user.desired_unifi_user_group_ids = desired_group_ids
        user.desired_unifi_user_group_names = desired_group_names
    user.status = _norm(row.get("user_status")) or user.status or _local_status_from_unifi(snapshot.status)
    user.notes = _norm(row.get("notes")) or user.notes


def _apply_snapshot_current_fields(
    snapshot: UnifiUser,
    row: dict[str, str],
    *,
    policy_refs: list[dict[str, Any]],
    group_refs: list[dict[str, Any]],
) -> None:
    policy_ids = _split_multi_value(row.get("access_policy_ids"))
    policy_names = _split_multi_value(row.get("access_policy_names"))
    group_ids = _split_multi_value(row.get("group_ids"))
    group_names = _split_multi_value(row.get("group_names"))
    policy_names_by_id = _names_by_id(policy_refs)
    group_names_by_id = _names_by_id(group_refs)

    if policy_ids:
        snapshot.access_policy_ids = policy_ids
    if policy_names or policy_ids:
        snapshot.access_policy_names = policy_names or _names_for_ids(policy_ids, policy_names_by_id)
    if group_ids:
        snapshot.group_ids = group_ids
    if group_names or group_ids:
        snapshot.group_names = group_names or _names_for_ids(group_ids, group_names_by_id)

    for field in (
        "email_status",
        "suite_number",
        "phone",
        "username",
        "alias",
        "onboard_time",
        "raw_user_json_file",
    ):
        value = _norm(row.get(field))
        if value:
            setattr(snapshot, field, value)
    if _norm(row.get("status")):
        snapshot.status = _norm_lower(row.get("status"))
    if _norm(row.get("email")):
        snapshot.email = _norm_lower(row.get("email"))
    if _norm(row.get("employee_number")):
        snapshot.employee_number = _norm(row.get("employee_number"))
    if _norm(row.get("first_name")):
        snapshot.first_name = _norm(row.get("first_name"))
    if _norm(row.get("last_name")):
        snapshot.last_name = _norm(row.get("last_name"))
    if _norm(row.get("full_name")):
        snapshot.full_name = _norm(row.get("full_name"))
    for field in ("nfc_card_count", "license_plate_count"):
        value = _norm(row.get(field))
        if value:
            try:
                setattr(snapshot, field, int(value))
            except ValueError:
                pass
    if _norm(row.get("touch_pass_status")):
        snapshot.touch_pass_status = _norm(row.get("touch_pass_status"))
    if _norm(row.get("touch_pass_last_activity")):
        snapshot.touch_pass_last_activity = _norm(row.get("touch_pass_last_activity"))


def _resolve_reference(
    session: Session,
    row: dict[str, str],
    *,
    row_number: int,
    model: type[Company] | type[Suite],
    label: str,
    id_field: str,
    name_field: str,
    name_attribute: str,
    required: bool,
    errors: list[str],
) -> Company | Suite | None:
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
        if required:
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


def _resolve_unifi_selection(
    row: dict[str, str],
    *,
    row_number: int,
    label: str,
    id_field: str,
    name_field: str,
    references: list[dict[str, Any]],
    errors: list[str],
) -> tuple[list[str], list[str]]:
    ids = _split_multi_value(row.get(id_field))
    names = _split_multi_value(row.get(name_field))
    names_by_id = _names_by_id(references)
    if ids:
        return ids, names or _names_for_ids(ids, names_by_id)
    if not names:
        return [], []

    resolved_ids: list[str] = []
    resolved_names: list[str] = []
    for name in names:
        matches = [item for item in references if _normalize_lookup(_item_name(item)) == _normalize_lookup(name)]
        if not matches:
            errors.append(f"Row {row_number}: {label} name {name!r} was not found.")
            continue
        if len(matches) > 1:
            errors.append(f"Row {row_number}: {label} name {name!r} is ambiguous.")
            continue
        resolved_ids.append(_item_id(matches[0]))
        resolved_names.append(_item_name(matches[0]))
    return resolved_ids, resolved_names


def _find_existing_user(session: Session, *, email: str, employee_number: str | None) -> User | None:
    if employee_number:
        user = session.scalar(select(User).where(User.employee_number == employee_number))
        if user:
            return user
    if email:
        return session.scalar(select(User).where(User.email == email))
    return None


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


def _unifi_reference_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": _item_id(item),
            "name": _item_name(item),
            "description": _norm(_first_present(item, ("description", "desc"))),
            "status": _norm(_first_present(item, ("status", "state"))),
        }
        for item in items
    ]


def _csv_text(fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows([{key: "" if value is None else value for key, value in row.items()} for row in rows])
    return output.getvalue()


def _local_before(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "company_id": user.company_id,
        "primary_suite_id": user.primary_suite_id,
        "desired_unifi_access_policy_ids": user.desired_unifi_access_policy_ids or [],
        "desired_unifi_user_group_ids": user.desired_unifi_user_group_ids or [],
        "status": user.status,
    }


def _first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    if not isinstance(source, dict):
        return None
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _touch_pass_value(snapshot: dict[str, Any], keys: tuple[str, ...]) -> str:
    touch_pass = _first_present(snapshot, ("touch_pass", "touchPass", "mobile_credential", "mobileCredential"))
    if not isinstance(touch_pass, dict):
        return ""
    return _norm(_first_present(touch_pass, keys))


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


def _names_for_ids(ids: list[str], names_by_id: dict[str, str]) -> list[str]:
    return [names_by_id[item_id] for item_id in ids if names_by_id.get(item_id)]


def _split_multi_value(value: str | None) -> list[str]:
    return [part.strip() for part in re.split(r"[;,\n]", value or "") if part.strip()]


def _join(values: list[Any]) -> str:
    return ";".join(str(value) for value in values if value not in (None, ""))


def _has_any(row: dict[str, str], *keys: str) -> bool:
    return any(_norm(row.get(key)) for key in keys)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _normalize_lookup(value)


def _normalize_lookup(value: Any) -> str:
    return " ".join(_norm(value).casefold().split())


def _is_truthy(value: Any) -> bool:
    return _norm_lower(value) in {"1", "true", "yes", "y", "on", "promote", "update"}


def _local_status_from_unifi(status: str | None) -> str:
    normalized = _norm_lower(status)
    if normalized in ACTIVE_UNIFI_STATUSES:
        return "active"
    if normalized in INACTIVE_UNIFI_STATUSES:
        return "inactive"
    return "pending"
