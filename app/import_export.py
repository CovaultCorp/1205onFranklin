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

from app.models import AuditLog, Company, CompanySuite, ImportBatch, ImportBatchRow, Suite, UnifiUser, User, UserSuiteAssignment, utcnow
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
    batch = create_bootstrap_import_batch(
        session,
        csv_text,
        unifi_access_policies=unifi_access_policies,
        unifi_user_groups=unifi_user_groups,
        actor_account_id=actor_account_id,
    )
    if batch.summary_json.get("error_count"):
        summary = BootstrapImportSummary(rows_seen=batch.summary_json.get("total_rows", 0))
        summary.rows_skipped = batch.summary_json.get("skip_count", 0)
        summary.errors = [error for row in batch.rows for error in (row.validation_errors_json or [])]
        return summary
    return commit_import_batch(
        session,
        batch,
        actor_account_id=actor_account_id,
        actor_email=actor_email,
        ip_address=ip_address,
    )


def create_bootstrap_import_batch(
    session: Session,
    csv_text: str,
    *,
    unifi_access_policies: list[dict[str, Any]] | None = None,
    unifi_user_groups: list[dict[str, Any]] | None = None,
    actor_account_id: int | None = None,
    filename: str | None = None,
) -> ImportBatch:
    batch = ImportBatch(
        source="bootstrap_csv",
        status="preview",
        filename=filename,
        created_by_account_id=actor_account_id,
        summary_json={},
    )
    session.add(batch)
    session.flush()

    reader = csv.DictReader(StringIO(csv_text))
    fieldnames = reader.fieldnames or []
    if "id" not in fieldnames and "unifi_user_id" not in fieldnames:
        _add_import_row(
            batch,
            row_number=None,
            action="error",
            validation_errors=["Missing required column: id or unifi_user_id"],
        )
        _refresh_batch_summary(batch)
        return batch

    policy_refs = unifi_access_policies or []
    group_refs = unifi_user_groups or []
    for row_number, row in enumerate(reader, start=2):
        _preview_bootstrap_row(
            session,
            batch,
            row,
            row_number=row_number,
            policy_refs=policy_refs,
            group_refs=group_refs,
        )

    _refresh_batch_summary(batch)
    return batch


def commit_import_batch(
    session: Session,
    batch: ImportBatch,
    *,
    actor_account_id: int | None = None,
    actor_email: str | None = None,
    ip_address: str | None = None,
) -> BootstrapImportSummary:
    summary = BootstrapImportSummary()
    if batch.status == "committed":
        summary.rows_skipped = len(batch.rows)
        return summary
    if batch.status != "preview":
        summary.errors.append(f"Import batch {batch.id} is {batch.status} and cannot be committed.")
        batch.last_error = summary.errors[0]
        return summary
    error_rows = [row for row in batch.rows if row.action == "error" or row.validation_errors_json]
    if error_rows:
        summary.rows_seen = len(batch.rows)
        summary.rows_skipped = len([row for row in batch.rows if row.action == "skip"])
        summary.errors = [error for row in error_rows for error in (row.validation_errors_json or [])]
        batch.last_error = "Resolve validation errors before committing this import batch."
        _refresh_batch_summary(batch)
        return summary

    for row in batch.rows:
        summary.rows_seen += 1
        if row.status == "committed":
            summary.rows_skipped += 1
            continue
        if row.action == "skip":
            row.status = "skipped"
            summary.rows_skipped += 1
            continue
        try:
            changed = _commit_import_batch_row(session, row)
        except ValueError as exc:
            row.status = "error"
            row.validation_errors_json = [str(exc)]
            batch.status = "failed"
            batch.last_error = str(exc)
            summary.errors.append(str(exc))
            continue
        if changed["created"]:
            summary.users_created += 1
        if changed["updated"]:
            summary.users_updated += 1
        if changed["linked"]:
            summary.snapshots_linked += 1
        session.add(
            AuditLog(
                actor_account_id=actor_account_id,
                actor_email=actor_email,
                action=_audit_action_for_row(row),
                target_type="User",
                target_id=row.target_id,
                before_json=row.before_json,
                after_json=row.after_json,
                ip_address=ip_address,
            )
        )
        row.status = "committed"
        row.committed_at = utcnow()
    if summary.errors:
        batch.status = "failed"
    else:
        batch.status = "committed"
        batch.committed_at = utcnow()
        batch.committed_by_account_id = actor_account_id
        batch.last_error = None
    _refresh_batch_summary(batch)
    return summary


def _audit_action_for_row(row: ImportBatchRow) -> str:
    if row.batch and row.batch.source == "bootstrap_csv":
        if row.action == "update":
            return "bootstrap.update_local_registry_user"
        return "bootstrap.promote_unifi_user"
    return f"import_batch.{row.action}_user"


def create_reconciliation_import_batch(
    session: Session,
    snapshots: list[UnifiUser],
    *,
    actor_account_id: int | None = None,
) -> ImportBatch | None:
    batch = ImportBatch(
        source="unifi_reconciliation",
        status="preview",
        created_by_account_id=actor_account_id,
        summary_json={},
    )
    added = 0
    for snapshot in snapshots:
        if snapshot.local_user_id or _norm_lower(snapshot.status) not in ACTIVE_UNIFI_STATUSES:
            continue
        company, suite = _suggest_reconciliation_references(session, snapshot)
        errors: list[str] = []
        if company is None:
            errors.append("Company could not be inferred from the UniFi snapshot; edit a bootstrap CSV row or local reference before committing.")
        if suite is None:
            errors.append("Suite could not be inferred from the UniFi snapshot suite_number.")
        before = None
        after = _after_state_from_values(
            snapshot=snapshot,
            company=company,
            suite=suite,
            desired_policy_ids=snapshot.access_policy_ids or [],
            desired_policy_names=snapshot.access_policy_names or [],
            desired_group_ids=snapshot.group_ids or [],
            desired_group_names=snapshot.group_names or [],
            row_values={},
        )
        _add_import_row(
            batch,
            row_number=None,
            action="error" if errors else "create",
            unifi_user_id=snapshot.unifi_user_id,
            email=snapshot.email,
            employee_number=snapshot.employee_number,
            full_name=snapshot.full_name or _full_name(snapshot.first_name, snapshot.last_name),
            before_json=before,
            after_json=after,
            diff_json=_diff_states(before, after),
            validation_errors=errors,
        )
        added += 1
    if not added:
        return None
    session.add(batch)
    session.flush()
    _refresh_batch_summary(batch)
    return batch


def _preview_bootstrap_row(
    session: Session,
    batch: ImportBatch,
    row: dict[str, str],
    *,
    row_number: int,
    policy_refs: list[dict[str, Any]],
    group_refs: list[dict[str, Any]],
) -> None:
    promote = _is_truthy(row.get("promote"))
    update_existing = _is_truthy(row.get("update_existing"))
    unifi_user_id = _norm(row.get("unifi_user_id")) or _norm(row.get("id"))
    if not promote and not update_existing:
        _add_import_row(
            batch,
            row_number=row_number,
            action="skip",
            unifi_user_id=unifi_user_id or None,
            email=_norm_lower(row.get("email")) or None,
            employee_number=_norm(row.get("employee_number")) or None,
            full_name=_norm(row.get("full_name")) or _full_name(row.get("first_name"), row.get("last_name")),
            validation_errors=[],
        )
        return

    row_errors: list[str] = []
    snapshot = None
    if not unifi_user_id:
        row_errors.append(f"Row {row_number}: id or unifi_user_id is required.")
    else:
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == unifi_user_id))
        if snapshot is None:
            row_errors.append(f"Row {row_number}: UniFi snapshot {unifi_user_id} was not found.")

    linked_user = session.get(User, snapshot.local_user_id) if snapshot and snapshot.local_user_id else None
    if linked_user and not update_existing:
        _add_import_row(
            batch,
            row_number=row_number,
            action="skip",
            target_id=str(linked_user.id),
            unifi_user_id=unifi_user_id,
            email=linked_user.email,
            employee_number=linked_user.employee_number,
            full_name=_full_name(linked_user.first_name, linked_user.last_name),
            before_json=_local_preview_state(session, linked_user, snapshot),
        )
        return
    if snapshot and not linked_user and update_existing and not promote:
        row_errors.append(f"Row {row_number}: UniFi user {unifi_user_id} is not linked; use promote=yes to create or link a local registry user.")

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

    existing_user = linked_user
    if snapshot and existing_user is None:
        existing_user = _find_existing_user(
            session,
            email=_norm_lower(row.get("email")) or (snapshot.email or ""),
            employee_number=_norm(row.get("employee_number")) or snapshot.employee_number,
        )
    if snapshot and existing_user is None and not (_norm_lower(row.get("email")) or snapshot.email):
        row_errors.append(f"Row {row_number}: email is required to create a new local registry user.")

    action = "error"
    if not row_errors:
        if existing_user is None:
            action = "create"
        elif linked_user is None:
            action = "link"
        else:
            action = "update"

    before = _local_preview_state(session, existing_user, snapshot) if existing_user or snapshot else None
    after = None
    if snapshot:
        after = _after_state_from_values(
            snapshot=snapshot,
            company=company,
            suite=suite,
            desired_policy_ids=desired_policy_ids,
            desired_policy_names=desired_policy_names,
            desired_group_ids=desired_group_ids,
            desired_group_names=desired_group_names,
            row_values=row,
            user_id=existing_user.id if existing_user else None,
        )
    _add_import_row(
        batch,
        row_number=row_number,
        action=action,
        target_id=str(existing_user.id) if existing_user else None,
        unifi_user_id=unifi_user_id,
        email=(after or {}).get("email") or _norm_lower(row.get("email")) or (snapshot.email if snapshot else None),
        employee_number=(after or {}).get("employee_number") or _norm(row.get("employee_number")) or (snapshot.employee_number if snapshot else None),
        full_name=(after or {}).get("full_name") or _norm(row.get("full_name")) or _full_name(row.get("first_name"), row.get("last_name")),
        before_json=before,
        after_json=after,
        diff_json=_diff_states(before, after),
        validation_errors=row_errors,
    )


def _add_import_row(
    batch: ImportBatch,
    *,
    row_number: int | None,
    action: str,
    target_type: str = "user",
    target_id: str | None = None,
    unifi_user_id: str | None = None,
    email: str | None = None,
    employee_number: str | None = None,
    full_name: str | None = None,
    before_json: dict[str, Any] | None = None,
    after_json: dict[str, Any] | None = None,
    diff_json: dict[str, Any] | None = None,
    validation_errors: list[str] | None = None,
) -> ImportBatchRow:
    errors = validation_errors or []
    row = ImportBatchRow(
        row_number=row_number,
        action=action,
        target_type=target_type,
        target_id=target_id,
        unifi_user_id=unifi_user_id or None,
        email=email or None,
        employee_number=employee_number or None,
        full_name=full_name or None,
        before_json=before_json,
        after_json=after_json,
        diff_json=diff_json or {},
        validation_errors_json=errors,
        status="error" if action == "error" or errors else ("skipped" if action == "skip" else "pending"),
    )
    batch.rows.append(row)
    return row


def _refresh_batch_summary(batch: ImportBatch) -> None:
    rows = list(batch.rows)
    batch.summary_json = {
        "total_rows": len(rows),
        "create_count": len([row for row in rows if row.action == "create"]),
        "update_count": len([row for row in rows if row.action == "update"]),
        "link_count": len([row for row in rows if row.action == "link"]),
        "skip_count": len([row for row in rows if row.action == "skip"]),
        "error_count": len([row for row in rows if row.action == "error" or row.validation_errors_json]),
    }


def _commit_import_batch_row(session: Session, row: ImportBatchRow) -> dict[str, bool]:
    after = row.after_json or {}
    unifi_user_id = after.get("unifi_user_id") or row.unifi_user_id
    if not unifi_user_id:
        raise ValueError("Import row is missing a UniFi user ID.")
    snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == unifi_user_id))
    if snapshot is None:
        raise ValueError(f"UniFi snapshot {unifi_user_id} was not found.")

    user_id = after.get("user_id")
    user = session.get(User, user_id) if user_id else None
    if user is None and snapshot.local_user_id:
        user = session.get(User, snapshot.local_user_id)
    if user is None:
        user = _find_existing_user(
            session,
            email=_norm_lower(after.get("email") or row.email),
            employee_number=_norm(after.get("employee_number") or row.employee_number),
        )

    created = False
    if user is None:
        if not after.get("email"):
            raise ValueError("Email is required to create a local registry user.")
        user = User(
            first_name=after.get("first_name") or "Unknown",
            last_name=after.get("last_name") or "Unknown",
            email=_norm_lower(after.get("email")),
            employee_number=after.get("employee_number") or None,
            status=after.get("status") or _local_status_from_unifi(snapshot.status),
        )
        session.add(user)
        created = True
        session.flush()

    before_link_id = snapshot.local_user_id
    user.first_name = after.get("first_name") or user.first_name or "Unknown"
    user.last_name = after.get("last_name") or user.last_name or "Unknown"
    user.email = _norm_lower(after.get("email")) or user.email
    user.employee_number = after.get("employee_number") or None
    user.company_id = after.get("company_id")
    user.primary_suite_id = after.get("suite_id")
    user.status = after.get("status") or user.status
    user.notes = after.get("notes") or user.notes
    user.desired_unifi_access_policy_ids = after.get("desired_unifi_access_policy_ids") or []
    user.desired_unifi_access_policy_names = after.get("desired_unifi_access_policy_names") or []
    user.desired_unifi_user_group_ids = after.get("desired_unifi_user_group_ids") or []
    user.desired_unifi_user_group_names = after.get("desired_unifi_user_group_names") or []

    _apply_snapshot_state(snapshot, after.get("snapshot") or {})
    if user.company_id and user.primary_suite_id:
        _ensure_primary_assignment(session, user=user, company_id=user.company_id, suite_id=user.primary_suite_id)
    snapshot.local_user_id = user.id
    session.flush()
    row.target_id = str(user.id)
    return {"created": created, "updated": not created and row.action in {"update", "link"}, "linked": before_link_id != user.id}


def _after_state_from_values(
    *,
    snapshot: UnifiUser,
    company: Company | None,
    suite: Suite | None,
    desired_policy_ids: list[str],
    desired_policy_names: list[str],
    desired_group_ids: list[str],
    desired_group_names: list[str],
    row_values: dict[str, str],
    user_id: int | None = None,
) -> dict[str, Any]:
    first_name = _norm(row_values.get("first_name")) or snapshot.first_name or "Unknown"
    last_name = _norm(row_values.get("last_name")) or snapshot.last_name or "Unknown"
    email = _norm_lower(row_values.get("email")) or snapshot.email
    employee_number = _norm(row_values.get("employee_number")) or snapshot.employee_number
    status = _norm(row_values.get("user_status")) or _local_status_from_unifi(snapshot.status)
    snapshot_state = _snapshot_after_from_row(snapshot, row_values)
    return {
        "user_id": user_id,
        "unifi_user_id": snapshot.unifi_user_id,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": _norm(row_values.get("full_name")) or _full_name(first_name, last_name),
        "email": email,
        "employee_number": employee_number,
        "company_id": company.id if company else None,
        "company_name": company.name if company else "",
        "suite_id": suite.id if suite else None,
        "suite_number": suite.suite_number if suite else "",
        "status": status,
        "desired_unifi_access_policy_ids": desired_policy_ids,
        "desired_unifi_access_policy_names": desired_policy_names,
        "desired_unifi_user_group_ids": desired_group_ids,
        "desired_unifi_user_group_names": desired_group_names,
        "notes": _norm(row_values.get("notes")) or None,
        "current_unifi_access_policy_ids": snapshot_state.get("access_policy_ids") or [],
        "current_unifi_access_policy_names": snapshot_state.get("access_policy_names") or [],
        "current_unifi_user_group_ids": snapshot_state.get("group_ids") or [],
        "current_unifi_user_group_names": snapshot_state.get("group_names") or [],
        "snapshot": snapshot_state,
    }


def _snapshot_after_from_row(snapshot: UnifiUser, row: dict[str, str]) -> dict[str, Any]:
    state = {
        "email": snapshot.email,
        "email_status": snapshot.email_status,
        "employee_number": snapshot.employee_number,
        "suite_number": snapshot.suite_number,
        "first_name": snapshot.first_name,
        "last_name": snapshot.last_name,
        "full_name": snapshot.full_name,
        "phone": snapshot.phone,
        "username": snapshot.username,
        "alias": snapshot.alias,
        "status": snapshot.status,
        "onboard_time": snapshot.onboard_time,
        "access_policy_ids": snapshot.access_policy_ids or [],
        "access_policy_names": snapshot.access_policy_names or [],
        "group_ids": snapshot.group_ids or [],
        "group_names": snapshot.group_names or [],
        "nfc_card_count": snapshot.nfc_card_count,
        "touch_pass_status": snapshot.touch_pass_status,
        "touch_pass_last_activity": snapshot.touch_pass_last_activity,
        "license_plate_count": snapshot.license_plate_count,
        "raw_user_json_file": snapshot.raw_user_json_file,
    }
    for key in ("email_status", "suite_number", "phone", "username", "alias", "onboard_time", "raw_user_json_file"):
        if _norm(row.get(key)):
            state[key] = _norm(row.get(key))
    for key in ("email",):
        if _norm(row.get(key)):
            state[key] = _norm_lower(row.get(key))
    for key in ("employee_number", "first_name", "last_name", "full_name", "touch_pass_status", "touch_pass_last_activity"):
        if _norm(row.get(key)):
            state[key] = _norm(row.get(key))
    if _norm(row.get("status")):
        state["status"] = _norm_lower(row.get("status"))
    for field in ("access_policy_ids", "access_policy_names", "group_ids", "group_names"):
        values = _split_multi_value(row.get(field))
        if values:
            state[field] = values
    for field in ("nfc_card_count", "license_plate_count"):
        value = _norm(row.get(field))
        if value:
            try:
                state[field] = int(value)
            except ValueError:
                pass
    return state


def _apply_snapshot_state(snapshot: UnifiUser, state: dict[str, Any]) -> None:
    for field in (
        "email",
        "email_status",
        "employee_number",
        "suite_number",
        "first_name",
        "last_name",
        "full_name",
        "phone",
        "username",
        "alias",
        "status",
        "onboard_time",
        "nfc_card_count",
        "touch_pass_status",
        "touch_pass_last_activity",
        "license_plate_count",
        "raw_user_json_file",
    ):
        if field in state:
            setattr(snapshot, field, state[field])
    for field in ("access_policy_ids", "access_policy_names", "group_ids", "group_names"):
        if field in state:
            setattr(snapshot, field, state[field] or [])


def _local_preview_state(session: Session, user: User | None, snapshot: UnifiUser | None) -> dict[str, Any] | None:
    if user is None and snapshot is None:
        return None
    company = session.get(Company, user.company_id) if user and user.company_id else None
    suite = session.get(Suite, user.primary_suite_id) if user and user.primary_suite_id else None
    return {
        "user_id": user.id if user else None,
        "unifi_user_id": snapshot.unifi_user_id if snapshot else None,
        "first_name": user.first_name if user else "",
        "last_name": user.last_name if user else "",
        "full_name": _full_name(user.first_name, user.last_name) if user else "",
        "email": user.email if user else "",
        "employee_number": user.employee_number if user else "",
        "company_id": user.company_id if user else None,
        "company_name": company.name if company else "",
        "suite_id": user.primary_suite_id if user else None,
        "suite_number": suite.suite_number if suite else "",
        "status": user.status if user else "",
        "desired_unifi_access_policy_ids": (user.desired_unifi_access_policy_ids or []) if user else [],
        "desired_unifi_access_policy_names": (user.desired_unifi_access_policy_names or []) if user else [],
        "desired_unifi_user_group_ids": (user.desired_unifi_user_group_ids or []) if user else [],
        "desired_unifi_user_group_names": (user.desired_unifi_user_group_names or []) if user else [],
        "notes": user.notes if user else "",
        "current_unifi_access_policy_ids": (snapshot.access_policy_ids or []) if snapshot else [],
        "current_unifi_access_policy_names": (snapshot.access_policy_names or []) if snapshot else [],
        "current_unifi_user_group_ids": (snapshot.group_ids or []) if snapshot else [],
        "current_unifi_user_group_names": (snapshot.group_names or []) if snapshot else [],
    }


def _diff_states(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if after is None:
        return {}
    before = before or {}
    fields = (
        "first_name",
        "last_name",
        "full_name",
        "email",
        "employee_number",
        "company_name",
        "suite_number",
        "status",
        "desired_unifi_access_policy_names",
        "desired_unifi_user_group_names",
        "current_unifi_access_policy_names",
        "current_unifi_user_group_names",
        "notes",
    )
    return {
        field: {"before": before.get(field) or "", "after": after.get(field) or ""}
        for field in fields
        if (before.get(field) or "") != (after.get(field) or "")
    }


def _suggest_reconciliation_references(session: Session, snapshot: UnifiUser) -> tuple[Company | None, Suite | None]:
    suite = None
    if snapshot.suite_number:
        suite = session.scalar(select(Suite).where(Suite.suite_number == snapshot.suite_number))
    company = None
    if suite:
        assignments = session.scalars(
            select(CompanySuite).where(CompanySuite.suite_id == suite.id, CompanySuite.occupancy_status == "active")
        ).all()
        if len(assignments) == 1:
            company = session.get(Company, assignments[0].company_id)
    return company, suite


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


def _full_name(first_name: Any, last_name: Any) -> str:
    return " ".join(part for part in (_norm(first_name), _norm(last_name)) if part)


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
