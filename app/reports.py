from __future__ import annotations

import csv
from html import escape
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.mailer import send_email
from app.models import Company, ReportRun, Suite, UnifiUser, User, utcnow
from app.verification import create_verification_request

REPORT_COLUMNS = [
    "Full name",
    "Email",
    "Employee number",
    "Company",
    "Suite",
    "Status",
    "Access profile",
    "UniFi status",
    "Current UniFi Access Policies",
    "Desired UniFi Access Policies",
    "Current UniFi User Groups",
    "Desired UniFi User Groups",
    "Last verified date",
    "Notes",
]


def _report_dir() -> Path:
    path = get_settings().export_dir / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _user_rows(session: Session, *, company_id: int | None = None, suite_id: int | None = None) -> list[dict[str, Any]]:
    statement = select(User, Company, Suite, UnifiUser).join(Company, User.company_id == Company.id, isouter=True).join(
        Suite, User.primary_suite_id == Suite.id, isouter=True
    ).join(
        UnifiUser, UnifiUser.local_user_id == User.id, isouter=True
    )
    statement = statement.where(User.status == "active")
    if company_id:
        statement = statement.where(User.company_id == company_id)
    if suite_id:
        statement = statement.where(User.primary_suite_id == suite_id)
    statement = statement.order_by(Suite.suite_number, Company.name, User.last_name, User.first_name)
    rows = []
    for user, company, suite, unifi_user in session.execute(statement):
        rows.append(
            {
                "Full name": f"{user.first_name} {user.last_name}",
                "Email": user.email,
                "Employee number": user.employee_number or "",
                "Company": company.name if company else "",
                "Suite": suite.suite_number if suite else "",
                "Status": user.status,
                "Access profile": user.access_profile.name if user.access_profile else "",
                "UniFi status": unifi_user.status if unifi_user else "",
                "Current UniFi Access Policies": _current_policy_names(unifi_user),
                "Desired UniFi Access Policies": _join_values(
                    user.desired_unifi_access_policy_names or user.desired_unifi_access_policy_ids or []
                ),
                "Current UniFi User Groups": _current_group_names(unifi_user),
                "Desired UniFi User Groups": _join_values(user.desired_unifi_user_group_names or user.desired_unifi_user_group_ids or []),
                "Last verified date": user.last_verified_at.date().isoformat() if user.last_verified_at else "",
                "Notes": user.notes or "",
            }
        )
    return rows


def _current_policy_names(unifi_user: UnifiUser | None) -> str:
    if unifi_user is None:
        return ""
    names = _extract_item_names(
        unifi_user.raw_snapshot_json or {},
        ("access_policy", "access_policies", "accessPolicy", "accessPolicies"),
    )
    return _join_values(names or unifi_user.access_policy_ids or [])


def _current_group_names(unifi_user: UnifiUser | None) -> str:
    if unifi_user is None:
        return ""
    names = _extract_item_names(
        unifi_user.raw_snapshot_json or {},
        ("groups", "user_groups", "userGroups", "department", "departments"),
    )
    return _join_values(names)


def _extract_item_names(snapshot: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    for key in keys:
        value = snapshot.get(key)
        if isinstance(value, list):
            return [_item_name(item) for item in value if _item_name(item)]
        if isinstance(value, dict):
            name = _item_name(value)
            return [name] if name else []
        if value not in (None, ""):
            return [str(value)]
    return []


def _item_name(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    return str(
        item.get("name")
        or item.get("display_name")
        or item.get("displayName")
        or item.get("policy_name")
        or item.get("policyName")
        or item.get("group_name")
        or item.get("groupName")
        or ""
    ).strip()


def _join_values(values: list[Any]) -> str:
    return "; ".join(str(value) for value in values if value not in (None, ""))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_html(path: Path, title: str, rows: list[dict[str, Any]]) -> None:
    table_rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(row[column]))}</td>" for column in REPORT_COLUMNS) + "</tr>" for row in rows
    )
    headers = "".join(f"<th>{escape(column)}</th>" for column in REPORT_COLUMNS)
    path.write_text(
        f"<h1>{escape(title)}</h1><table><thead><tr>{headers}</tr></thead><tbody>{table_rows}</tbody></table>",
        encoding="utf-8",
    )


def generate_report(
    session: Session,
    *,
    report_type: str,
    requested_by_account_id: int | None = None,
    company_id: int | None = None,
    suite_id: int | None = None,
    recipient_email: str | None = None,
) -> ReportRun:
    title = report_type.replace("_", " ").title()
    rows = _user_rows(session, company_id=company_id, suite_id=suite_id)
    run = ReportRun(
        report_type=report_type,
        status="running",
        requested_by_account_id=requested_by_account_id,
        recipient_email=recipient_email,
        subject=title,
        filters_json={"company_id": company_id, "suite_id": suite_id},
    )
    session.add(run)
    session.flush()

    base = _report_dir() / f"{report_type}_{run.id}"
    csv_path = base.with_suffix(".csv")
    html_path = base.with_suffix(".html")
    _write_csv(csv_path, rows)
    _write_html(html_path, title, rows)

    run.output_csv_path = str(csv_path)
    run.output_html_path = str(html_path)
    run.body = f"{title}\n\nRows: {len(rows)}"
    run.status = "sent" if recipient_email else "pending"
    return run


def send_report(session: Session, run: ReportRun, recipient_email: str) -> None:
    run.recipient_email = recipient_email
    run.status = "running"
    try:
        preview_path = send_email(
            recipient=recipient_email,
            subject=run.subject or run.report_type,
            body=run.body or "",
            attachments=[Path(run.output_csv_path)] if run.output_csv_path else [],
        )
        if run.report_type in {"company_users", "suite_users", "full_building_access", "verification"}:
            filters = run.filters_json or {}
            verification, token = create_verification_request(
                session,
                recipient_email=recipient_email,
                report_run_id=run.id,
                company_id=filters.get("company_id"),
                suite_id=filters.get("suite_id"),
            )
            verification.comments = f"Verification link: {get_settings().public_base_url}/verify/{token}"
        run.status = "sent"
        run.sent_at = utcnow()
        if preview_path:
            run.last_error = f"Email preview written to {preview_path}"
    except Exception as exc:
        run.status = "failed"
        run.last_error = str(exc)
