from __future__ import annotations

import csv
from io import StringIO

import pytest
from sqlalchemy import select


@pytest.fixture()
def db_context(tmp_path, monkeypatch):
    db_path = tmp_path / "bootstrap.db"
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


def _csv_text(rows: list[dict[str, str]]) -> str:
    from app.import_export import BOOTSTRAP_COLUMNS

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=BOOTSTRAP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def test_exports_only_unmatched_unifi_snapshots(db_context):
    from app.import_export import export_unmatched_unifi_users_csv
    from app.models import UnifiUser

    with db_context() as session:
        session.add_all(
            [
                UnifiUser(unifi_user_id="unmatched", email="u@example.com", first_name="Un", last_name="Matched", status="active"),
                UnifiUser(unifi_user_id="matched", local_user_id=99, email="m@example.com", status="active"),
            ]
        )
        session.commit()

        rows = list(csv.DictReader(StringIO(export_unmatched_unifi_users_csv(session))))

    assert len(rows) == 1
    assert rows[0]["unifi_user_id"] == "unmatched"
    assert rows[0]["local_status"] == "active"
    assert "access_profile_id" in rows[0]


def test_import_promotes_unmatched_snapshot_with_assignments_and_audit(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import AccessProfile, AuditLog, Company, Suite, UnifiUser, User, UserSuiteAssignment

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        profile = AccessProfile(name="Office Access", unifi_access_policy_ids=["policy-1"])
        snapshot = UnifiUser(
            unifi_user_id="u-1",
            email="ada@example.com",
            employee_number="E100",
            first_name="Ada",
            last_name="Lovelace",
            status="active",
        )
        session.add_all([company, suite, profile, snapshot])
        session.commit()

        summary = import_bootstrap_users_csv(
            session,
            _csv_text(
                [
                    {
                        "promote": "yes",
                        "unifi_user_id": "u-1",
                        "email": "ada@example.com",
                        "employee_number": "E100",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "unifi_status": "active",
                        "local_status": "active",
                        "company_id": str(company.id),
                        "company_name": "",
                        "suite_id": str(suite.id),
                        "suite_number": "",
                        "access_profile_id": str(profile.id),
                        "access_profile_name": "",
                        "title": "Engineer",
                        "department": "R&D",
                        "phone": "",
                        "notes": "Imported from UniFi bootstrap",
                    }
                ]
            ),
            actor_account_id=7,
            actor_email="admin@example.com",
        )
        session.commit()

        user = session.scalar(select(User).where(User.email == "ada@example.com"))
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == "u-1"))
        assignment = session.scalar(select(UserSuiteAssignment).where(UserSuiteAssignment.user_id == user.id))
        audit = session.scalar(select(AuditLog).where(AuditLog.action == "bootstrap.promote_unifi_user"))

        assert summary.users_created == 1
        assert summary.snapshots_linked == 1
        assert summary.errors == []
        assert user.company_id == company.id
        assert user.primary_suite_id == suite.id
        assert user.access_profile_id == profile.id
        assert user.title == "Engineer"
        assert snapshot.local_user_id == user.id
        assert assignment.suite_id == suite.id
        assert audit.actor_email == "admin@example.com"


def test_import_links_existing_user_without_duplicate_and_skips_linked_rows(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import AccessProfile, Company, Suite, UnifiUser, User

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        profile = AccessProfile(name="Office Access")
        existing = User(first_name="Ada", last_name="Existing", email="ada@example.com", employee_number="E100")
        snapshot = UnifiUser(unifi_user_id="u-1", email="ada@example.com", employee_number="E100", first_name="Ada", last_name="Lovelace")
        session.add_all([company, suite, profile, existing, snapshot])
        session.commit()

        row = {
            "promote": "yes",
            "unifi_user_id": "u-1",
            "email": "ada@example.com",
            "employee_number": "E100",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "unifi_status": "active",
            "local_status": "active",
            "company_id": str(company.id),
            "company_name": "",
            "suite_id": str(suite.id),
            "suite_number": "",
            "access_profile_id": str(profile.id),
            "access_profile_name": "",
            "title": "",
            "department": "",
            "phone": "",
            "notes": "",
        }
        first_summary = import_bootstrap_users_csv(session, _csv_text([row]))
        session.commit()
        second_summary = import_bootstrap_users_csv(session, _csv_text([row]))
        session.commit()

        users = session.scalars(select(User)).all()
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == "u-1"))

        assert len(users) == 1
        assert first_summary.users_created == 0
        assert first_summary.users_updated == 1
        assert first_summary.snapshots_linked == 1
        assert second_summary.rows_skipped == 1
        assert snapshot.local_user_id == existing.id


def test_import_reports_unresolved_assignment_errors(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import UnifiUser

    with db_context() as session:
        session.add(UnifiUser(unifi_user_id="u-1", email="ada@example.com", first_name="Ada", last_name="Lovelace"))
        session.commit()
        summary = import_bootstrap_users_csv(
            session,
            _csv_text(
                [
                    {
                        "promote": "yes",
                        "unifi_user_id": "u-1",
                        "email": "ada@example.com",
                        "employee_number": "",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "unifi_status": "active",
                        "local_status": "active",
                        "company_id": "",
                        "company_name": "Missing",
                        "suite_id": "",
                        "suite_number": "404",
                        "access_profile_id": "",
                        "access_profile_name": "Missing",
                        "title": "",
                        "department": "",
                        "phone": "",
                        "notes": "",
                    }
                ]
            ),
        )

    assert summary.users_created == 0
    assert summary.errors
