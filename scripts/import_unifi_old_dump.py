from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Company, CompanySuite, Suite, UnifiUser, User, UserSuiteAssignment, utcnow

"""
Import an old UniFi dump CSV with columns:

    Name, Email, Company, Suite, Status

Dry-run is the default and writes nothing:

    python scripts/import_unifi_old_dump.py all_unifi_users.csv
    python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit
    python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit --placeholder-emails
"""

EXPECTED_COLUMNS = {"Name", "Email", "Company", "Suite", "Status"}
PLACEHOLDER_DOMAIN = "placeholder.local"


@dataclass
class ImportSummary:
    rows_seen: int = 0
    rows_rejected: int = 0
    companies_created: int = 0
    suites_created: int = 0
    occupancies_created: int = 0
    users_created: int = 0
    users_updated: int = 0
    users_skipped_blank_email: int = 0
    assignments_created: int = 0
    assignments_updated: int = 0
    unifi_snapshots_created: int = 0
    unifi_snapshots_updated: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OldDumpRow:
    row_number: int
    name: str
    email: str
    company_name: str
    suite_number: str
    status: str
    generated_placeholder: bool = False


def normalize_whitespace(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_email(value: Any) -> str:
    return normalize_whitespace(value).lower()


def normalize_status(value: Any) -> str:
    normalized = normalize_whitespace(value).lower()
    if normalized in {"inactive", "disabled", "deactivated", "offboarded"}:
        return "inactive"
    return "active"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def placeholder_email(name: str, row_number: int) -> str:
    return f"unifi-{slugify(name)}-{row_number}@{PLACEHOLDER_DOMAIN}"


def split_name(full_name: str) -> tuple[str, str]:
    parts = normalize_whitespace(full_name).split()
    if not parts:
        return "Unknown", "Unknown"
    if len(parts) == 1:
        return parts[0][:120], "Unknown"
    return " ".join(parts[:-1])[:120], parts[-1][:120]


def read_old_dump(path: Path, *, placeholder_emails: bool) -> tuple[list[OldDumpRow], list[str]]:
    warnings: list[str] = []
    rows: list[OldDumpRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = EXPECTED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required column(s): {', '.join(sorted(missing))}")
        for row_number, raw in enumerate(reader, start=2):
            name = normalize_whitespace(raw.get("Name"))
            original_email = normalize_email(raw.get("Email"))
            if not name and not original_email:
                warnings.append(f"Row {row_number}: rejected because both Name and Email are blank.")
                continue
            company_name = normalize_whitespace(raw.get("Company"))
            suite_number = normalize_whitespace(raw.get("Suite"))
            if not company_name:
                warnings.append(f"Row {row_number}: blank company.")
            if not suite_number:
                warnings.append(f"Row {row_number}: blank suite.")
            generated_placeholder = False
            email = original_email
            if not email and placeholder_emails:
                email = placeholder_email(name or "unknown", row_number)
                generated_placeholder = True
            rows.append(
                OldDumpRow(
                    row_number=row_number,
                    name=name,
                    email=email,
                    company_name=company_name,
                    suite_number=suite_number,
                    status=normalize_status(raw.get("Status")),
                    generated_placeholder=generated_placeholder,
                )
            )
    return rows, warnings


def import_old_dump(
    session: Session,
    rows: list[OldDumpRow],
    *,
    placeholder_emails: bool = False,
) -> ImportSummary:
    summary = ImportSummary(rows_seen=len(rows))

    for row in rows:
        company = _get_or_create_company(session, row.company_name, summary) if row.company_name else None
        suite = _get_or_create_suite(session, row.suite_number, summary) if row.suite_number else None
        if company and suite:
            _get_or_create_company_suite(session, company, suite, summary)

        user: User | None = None
        if row.email:
            user = _get_or_create_user(session, row, company, suite, summary)
            if suite:
                _get_or_create_assignment(session, user, company, suite, summary)
        else:
            summary.users_skipped_blank_email += 1
            if not placeholder_emails:
                summary.warnings.append(f"Row {row.row_number}: skipped local User creation because Email is blank.")

        _get_or_create_unifi_snapshot(session, row, user, company, suite, summary)

    return summary


def _get_or_create_company(session: Session, name: str, summary: ImportSummary) -> Company:
    company = session.scalar(select(Company).where(Company.name == name))
    if company:
        return company
    company = Company(name=name, legal_name=None, status="active", notes="Imported from old UniFi user dump.")
    session.add(company)
    session.flush()
    summary.companies_created += 1
    return company


def _get_or_create_suite(session: Session, suite_number: str, summary: ImportSummary) -> Suite:
    suite = session.scalar(select(Suite).where(Suite.suite_number == suite_number))
    if suite:
        return suite
    suite = Suite(suite_number=suite_number, status="active", description="Imported from old UniFi user dump.")
    session.add(suite)
    session.flush()
    summary.suites_created += 1
    return suite


def _get_or_create_company_suite(session: Session, company: Company, suite: Suite, summary: ImportSummary) -> CompanySuite:
    occupancy = session.scalar(
        select(CompanySuite).where(CompanySuite.company_id == company.id, CompanySuite.suite_id == suite.id)
    )
    if occupancy:
        occupancy.occupancy_status = "active"
        return occupancy
    occupancy = CompanySuite(
        company_id=company.id,
        suite_id=suite.id,
        occupancy_status="active",
        notes="Imported from old UniFi user dump.",
    )
    session.add(occupancy)
    session.flush()
    summary.occupancies_created += 1
    return occupancy


def _get_or_create_user(
    session: Session,
    row: OldDumpRow,
    company: Company | None,
    suite: Suite | None,
    summary: ImportSummary,
) -> User:
    first_name, last_name = split_name(row.name or row.email)
    user = session.scalar(select(User).where(User.email == row.email))
    if user:
        user.first_name = first_name
        user.last_name = last_name
        user.company_id = company.id if company else None
        user.primary_suite_id = suite.id if suite else None
        user.status = row.status
        if row.generated_placeholder and not user.notes:
            user.notes = "Imported from old UniFi user dump with generated placeholder email."
        summary.users_updated += 1
        return user

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=row.email,
        employee_number=None,
        company_id=company.id if company else None,
        primary_suite_id=suite.id if suite else None,
        access_profile_id=None,
        desired_unifi_access_policy_ids=[],
        desired_unifi_access_policy_names=[],
        desired_unifi_user_group_ids=[],
        desired_unifi_user_group_names=[],
        title=None,
        phone=None,
        department=None,
        status=row.status,
        notes=(
            "Imported from old UniFi user dump with generated placeholder email."
            if row.generated_placeholder
            else "Imported from old UniFi user dump."
        ),
        last_verified_at=None,
        last_verified_by=None,
    )
    session.add(user)
    session.flush()
    summary.users_created += 1
    return user


def _get_or_create_assignment(
    session: Session,
    user: User,
    company: Company | None,
    suite: Suite,
    summary: ImportSummary,
) -> UserSuiteAssignment:
    assignment = session.scalar(
        select(UserSuiteAssignment).where(
            UserSuiteAssignment.user_id == user.id,
            UserSuiteAssignment.suite_id == suite.id,
            UserSuiteAssignment.assignment_type == "primary",
        )
    )
    if assignment:
        assignment.company_id = company.id if company else None
        assignment.active = True
        summary.assignments_updated += 1
        return assignment
    assignment = UserSuiteAssignment(
        user_id=user.id,
        suite_id=suite.id,
        company_id=company.id if company else None,
        assignment_type="primary",
        active=True,
    )
    session.add(assignment)
    session.flush()
    summary.assignments_created += 1
    return assignment


def _snapshot_id(row: OldDumpRow) -> str:
    if row.email:
        return f"old-dump-email-{row.email}"
    return f"old-dump-row-{row.row_number}-{slugify(row.name)}"


def _get_or_create_unifi_snapshot(
    session: Session,
    row: OldDumpRow,
    user: User | None,
    company: Company | None,
    suite: Suite | None,
    summary: ImportSummary,
) -> UnifiUser:
    unifi_user_id = _snapshot_id(row)
    first_name, last_name = split_name(row.name or row.email)
    raw_snapshot = {
        "source": "old_unifi_dump",
        "row_number": row.row_number,
        "name": row.name,
        "email": row.email,
        "company": row.company_name,
        "suite": row.suite_number,
        "status": row.status,
        "generated_placeholder_email": row.generated_placeholder,
    }
    snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == unifi_user_id))
    if snapshot:
        summary.unifi_snapshots_updated += 1
    else:
        snapshot = UnifiUser(unifi_user_id=unifi_user_id)
        session.add(snapshot)
        summary.unifi_snapshots_created += 1

    snapshot.local_user_id = user.id if user else None
    snapshot.email = row.email or None
    snapshot.first_name = first_name
    snapshot.last_name = last_name
    snapshot.full_name = row.name or f"{first_name} {last_name}"
    snapshot.suite_number = suite.suite_number if suite else (row.suite_number or None)
    snapshot.status = row.status
    snapshot.raw_snapshot_json = raw_snapshot
    snapshot.raw_user_json_file = f"old_unifi_dump:{row.row_number}"
    snapshot.last_seen_at = utcnow()
    snapshot.last_synced_at = utcnow()
    if company:
        raw_snapshot["local_company_id"] = company.id
    if suite:
        raw_snapshot["local_suite_id"] = suite.id
    session.flush()
    return snapshot


def print_summary(summary: ImportSummary, *, committed: bool) -> None:
    mode = "COMMIT" if committed else "DRY RUN"
    print(f"Old UniFi dump import summary ({mode})")
    print(f"Rows seen: {summary.rows_seen}")
    print(f"Rows rejected: {summary.rows_rejected}")
    print(f"Companies created: {summary.companies_created}")
    print(f"Suites created: {summary.suites_created}")
    print(f"Company-suite occupancies created: {summary.occupancies_created}")
    print(f"Users created: {summary.users_created}")
    print(f"Users updated: {summary.users_updated}")
    print(f"Users skipped due to blank email: {summary.users_skipped_blank_email}")
    print(f"Assignments created: {summary.assignments_created}")
    print(f"Assignments updated: {summary.assignments_updated}")
    print(f"UniFi snapshots created: {summary.unifi_snapshots_created}")
    print(f"UniFi snapshots updated: {summary.unifi_snapshots_updated}")
    if summary.warnings:
        print("\nWarnings:")
        for warning in summary.warnings:
            print(f"- {warning}")
    if summary.errors:
        print("\nErrors:")
        for error in summary.errors:
            print(f"- {error}")
    if not committed:
        print("\nDry run only. Re-run with --commit to write changes.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely import an old UniFi all_unifi_users.csv dump.")
    parser.add_argument("csv_path", type=Path, help="Path to all_unifi_users.csv")
    parser.add_argument("--commit", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument(
        "--placeholder-emails",
        action="store_true",
        help=f"Create local Users for blank-email rows using deterministic @{PLACEHOLDER_DOMAIN} addresses.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.csv_path.exists():
        print(f"CSV file not found: {args.csv_path}", file=sys.stderr)
        return 2

    init_db()
    rows, warnings = read_old_dump(args.csv_path, placeholder_emails=args.placeholder_emails)
    with SessionLocal() as session:
        summary = import_old_dump(session, rows, placeholder_emails=args.placeholder_emails)
        summary.warnings = warnings + summary.warnings
        summary.rows_rejected = len([warning for warning in warnings if "rejected" in warning])
        if args.commit:
            session.commit()
        else:
            session.rollback()
        print_summary(summary, committed=args.commit)
    return 0 if not summary.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
