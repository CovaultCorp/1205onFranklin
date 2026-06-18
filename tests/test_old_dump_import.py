from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import select


@pytest.fixture()
def db_context(tmp_path, monkeypatch):
    db_path = tmp_path / "old_dump.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")

    import app.config
    import app.db

    app.config.get_settings.cache_clear()
    app.db.configure_database(f"sqlite:///{db_path}")
    app.db.Base.metadata.drop_all(bind=app.db.engine)
    app.db.init_db()
    return app.db.SessionLocal


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Name", "Email", "Company", "Suite", "Status"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_old_dump_import_dry_run_rolls_back(db_context, tmp_path):
    from scripts.import_unifi_old_dump import import_old_dump, read_old_dump
    from app.models import Company, UnifiUser, User

    csv_path = _write_csv(
        tmp_path / "all_unifi_users.csv",
        [{"Name": "Ada Lovelace", "Email": "ADA@EXAMPLE.COM", "Company": "Acme", "Suite": "1200", "Status": "Active"}],
    )
    rows, warnings = read_old_dump(csv_path, placeholder_emails=False)
    assert warnings == []

    with db_context() as session:
        summary = import_old_dump(session, rows)
        session.rollback()

    with db_context() as session:
        assert summary.companies_created == 1
        assert summary.users_created == 1
        assert summary.unifi_snapshots_created == 1
        assert session.scalar(select(Company)) is None
        assert session.scalar(select(User)) is None
        assert session.scalar(select(UnifiUser)) is None


def test_old_dump_import_commit_creates_registry_and_snapshot_records(db_context, tmp_path):
    from scripts.import_unifi_old_dump import import_old_dump, read_old_dump
    from app.models import Company, CompanySuite, Suite, UnifiUser, User, UserSuiteAssignment

    csv_path = _write_csv(
        tmp_path / "all_unifi_users.csv",
        [{"Name": "Ada Lovelace", "Email": "ada@example.com", "Company": "Acme", "Suite": "1200", "Status": "active"}],
    )
    rows, _warnings = read_old_dump(csv_path, placeholder_emails=False)

    with db_context() as session:
        summary = import_old_dump(session, rows)
        session.commit()

        company = session.scalar(select(Company).where(Company.name == "Acme"))
        suite = session.scalar(select(Suite).where(Suite.suite_number == "1200"))
        user = session.scalar(select(User).where(User.email == "ada@example.com"))
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == "old-dump-email-ada@example.com"))
        assignment = session.scalar(select(UserSuiteAssignment).where(UserSuiteAssignment.user_id == user.id))
        occupancy = session.scalar(select(CompanySuite).where(CompanySuite.company_id == company.id, CompanySuite.suite_id == suite.id))

        assert summary.companies_created == 1
        assert summary.suites_created == 1
        assert summary.occupancies_created == 1
        assert summary.users_created == 1
        assert summary.assignments_created == 1
        assert summary.unifi_snapshots_created == 1
        assert user.first_name == "Ada"
        assert user.last_name == "Lovelace"
        assert user.company_id == company.id
        assert user.primary_suite_id == suite.id
        assert snapshot.local_user_id == user.id
        assert snapshot.raw_snapshot_json["company"] == "Acme"
        assert assignment.suite_id == suite.id
        assert occupancy.occupancy_status == "active"


def test_old_dump_import_blank_email_skips_user_but_keeps_snapshot(db_context, tmp_path):
    from scripts.import_unifi_old_dump import import_old_dump, read_old_dump
    from app.models import UnifiUser, User

    csv_path = _write_csv(
        tmp_path / "all_unifi_users.csv",
        [{"Name": "Lobby Phone", "Email": "", "Company": "Acme", "Suite": "100", "Status": "active"}],
    )
    rows, _warnings = read_old_dump(csv_path, placeholder_emails=False)

    with db_context() as session:
        summary = import_old_dump(session, rows)
        session.commit()

        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == "old-dump-row-2-lobby-phone"))
        assert summary.users_skipped_blank_email == 1
        assert summary.users_created == 0
        assert summary.unifi_snapshots_created == 1
        assert session.scalar(select(User)) is None
        assert snapshot is not None
        assert snapshot.email is None
        assert snapshot.local_user_id is None


def test_old_dump_import_placeholder_email_creates_user_for_blank_email(db_context, tmp_path):
    from scripts.import_unifi_old_dump import import_old_dump, read_old_dump
    from app.models import UnifiUser, User

    csv_path = _write_csv(
        tmp_path / "all_unifi_users.csv",
        [{"Name": "Lobby Phone", "Email": "", "Company": "Acme", "Suite": "100", "Status": "active"}],
    )
    rows, _warnings = read_old_dump(csv_path, placeholder_emails=True)

    with db_context() as session:
        summary = import_old_dump(session, rows, placeholder_emails=True)
        session.commit()

        expected_email = "unifi-lobby-phone-2@placeholder.local"
        user = session.scalar(select(User).where(User.email == expected_email))
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == f"old-dump-email-{expected_email}"))
        assert summary.users_created == 1
        assert summary.users_skipped_blank_email == 0
        assert user is not None
        assert snapshot.local_user_id == user.id
        assert snapshot.raw_snapshot_json["generated_placeholder_email"] is True


def test_old_dump_import_is_idempotent_and_updates_duplicate_email(db_context, tmp_path):
    from scripts.import_unifi_old_dump import import_old_dump, read_old_dump
    from app.models import UnifiUser, User

    first_csv = _write_csv(
        tmp_path / "first.csv",
        [{"Name": "Ada Lovelace", "Email": "ada@example.com", "Company": "Acme", "Suite": "1200", "Status": "active"}],
    )
    second_csv = _write_csv(
        tmp_path / "second.csv",
        [{"Name": "Ada Byron", "Email": "ada@example.com", "Company": "Acme", "Suite": "1200", "Status": "inactive"}],
    )

    with db_context() as session:
        import_old_dump(session, read_old_dump(first_csv, placeholder_emails=False)[0])
        session.commit()
        second_summary = import_old_dump(session, read_old_dump(second_csv, placeholder_emails=False)[0])
        session.commit()

        users = session.scalars(select(User)).all()
        snapshots = session.scalars(select(UnifiUser)).all()
        assert len(users) == 1
        assert len(snapshots) == 1
        assert second_summary.users_created == 0
        assert second_summary.users_updated == 1
        assert second_summary.unifi_snapshots_updated == 1
        assert users[0].last_name == "Byron"
        assert users[0].status == "inactive"


def test_old_dump_import_rejects_rows_missing_name_and_email(tmp_path):
    from scripts.import_unifi_old_dump import read_old_dump

    csv_path = _write_csv(
        tmp_path / "all_unifi_users.csv",
        [{"Name": "", "Email": "", "Company": "Acme", "Suite": "100", "Status": "active"}],
    )

    rows, warnings = read_old_dump(csv_path, placeholder_emails=False)
    assert rows == []
    assert "rejected because both Name and Email are blank" in warnings[0]
