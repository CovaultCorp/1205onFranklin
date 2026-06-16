from __future__ import annotations

import csv
from io import BytesIO, StringIO
import zipfile

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
    writer = csv.DictWriter(output, fieldnames=BOOTSTRAP_COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def test_reference_export_zip_contains_expected_files_and_all_unifi_users(db_context):
    from app.import_export import build_bootstrap_reference_zip
    from app.models import Company, Suite, UnifiUser, User

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        session.add_all([company, suite])
        session.flush()
        linked = User(
            first_name="Linked",
            last_name="User",
            email="linked@example.com",
            company_id=company.id,
            primary_suite_id=suite.id,
            desired_unifi_access_policy_ids=["policy-2"],
            desired_unifi_access_policy_names=["Suite 1200"],
            desired_unifi_user_group_ids=["group-2"],
            desired_unifi_user_group_names=["Managers"],
            status="active",
        )
        session.add(linked)
        session.flush()
        session.add_all(
            [
                UnifiUser(
                    unifi_user_id="unlinked",
                    email="u@example.com",
                    email_status="verified",
                    first_name="Un",
                    last_name="Linked",
                    full_name="Un Linked",
                    suite_number="120",
                    phone="555-0100",
                    username="ulinked",
                    alias="Un",
                    status="active",
                    access_policy_ids=["policy-1"],
                    access_policy_names=["Front Door"],
                    group_ids=["group-1"],
                    group_names=["Employees"],
                    nfc_card_count=2,
                    touch_pass_status="enabled",
                    touch_pass_last_activity="2026-01-03T00:00:00Z",
                    license_plate_count=1,
                    raw_user_json_file="raw.json",
                ),
                UnifiUser(
                    unifi_user_id="linked",
                    local_user_id=linked.id,
                    email="linked@example.com",
                    status="active",
                    access_policy_ids=["policy-2"],
                    access_policy_names=["Suite 1200"],
                    group_ids=["group-2"],
                    group_names=["Managers"],
                ),
            ]
        )
        session.commit()
        archive_bytes = build_bootstrap_reference_zip(
            session,
            unifi_access_policies=[{"id": "policy-1", "name": "Front Door"}, {"id": "policy-2", "name": "Suite 1200"}],
            unifi_user_groups=[{"id": "group-1", "name": "Employees"}, {"id": "group-2", "name": "Managers"}],
        )

    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        assert set(archive.namelist()) == {
            "all_unifi_users.csv",
            "companies.csv",
            "suites.csv",
            "unifi_access_policies.csv",
            "unifi_user_groups.csv",
        }
        rows = list(csv.DictReader(StringIO(archive.read("all_unifi_users.csv").decode("utf-8"))))

    assert {row["unifi_user_id"] for row in rows} == {"unlinked", "linked"}
    linked_row = next(row for row in rows if row["unifi_user_id"] == "linked")
    unlinked_row = next(row for row in rows if row["unifi_user_id"] == "unlinked")
    assert linked_row["is_linked"] == "yes"
    assert linked_row["company_name"] == "Acme"
    assert linked_row["local_suite_number"] == "1200"
    assert linked_row["desired_unifi_access_policy_names"] == "Suite 1200"
    assert unlinked_row["id"] == "unlinked"
    assert unlinked_row["email_status"] == "verified"
    assert unlinked_row["suite_number"] == "120"
    assert unlinked_row["phone"] == "555-0100"
    assert unlinked_row["username"] == "ulinked"
    assert unlinked_row["alias"] == "Un"
    assert unlinked_row["access_policy_ids"] == "policy-1"
    assert unlinked_row["access_policy_names"] == "Front Door"
    assert unlinked_row["group_ids"] == "group-1"
    assert unlinked_row["group_names"] == "Employees"
    assert unlinked_row["nfc_card_count"] == "2"
    assert unlinked_row["touch_pass_status"] == "enabled"
    assert unlinked_row["touch_pass_last_activity"] == "2026-01-03T00:00:00Z"
    assert unlinked_row["license_plate_count"] == "1"
    assert unlinked_row["raw_user_json_file"] == "raw.json"


def test_policy_and_group_csv_generation(db_context):
    from app.import_export import build_bootstrap_reference_zip

    with db_context() as session:
        archive_bytes = build_bootstrap_reference_zip(
            session,
            unifi_access_policies=[{"id": "policy-1", "name": "Front Door", "description": "Main", "status": "active"}],
            unifi_user_groups=[{"id": "group-1", "name": "Employees", "description": "Staff", "status": "active"}],
        )

    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        assert "policy-1,Front Door,Main,active" in archive.read("unifi_access_policies.csv").decode("utf-8")
        assert "group-1,Employees,Staff,active" in archive.read("unifi_user_groups.csv").decode("utf-8")


def test_import_promotes_unlinked_snapshot_by_id_with_assignments_and_audit(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import AuditLog, Company, Suite, UnifiUser, User, UserSuiteAssignment

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        snapshot = UnifiUser(
            unifi_user_id="u-1",
            email="ada@example.com",
            employee_number="E100",
            first_name="Ada",
            last_name="Lovelace",
            status="active",
        )
        session.add_all([company, suite, snapshot])
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
                        "company_id": str(company.id),
                        "local_suite_id": str(suite.id),
                        "desired_unifi_access_policy_ids": "policy-1",
                        "desired_unifi_user_group_ids": "group-1",
                        "notes": "Imported from UniFi bootstrap",
                    }
                ]
            ),
            unifi_access_policies=[{"id": "policy-1", "name": "Front Door"}],
            unifi_user_groups=[{"id": "group-1", "name": "Employees"}],
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
        assert user.access_profile_id is None
        assert user.desired_unifi_access_policy_ids == ["policy-1"]
        assert user.desired_unifi_access_policy_names == ["Front Door"]
        assert user.desired_unifi_user_group_ids == ["group-1"]
        assert user.desired_unifi_user_group_names == ["Employees"]
        assert user.status == "active"
        assert snapshot.local_user_id == user.id
        assert assignment.suite_id == suite.id
        assert audit.actor_email == "admin@example.com"


def test_import_promotes_by_name_lookup(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import Company, Suite, UnifiUser, User

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        snapshot = UnifiUser(
            unifi_user_id="u-1",
            email="ada@example.com",
            employee_number="E100",
            first_name="Ada",
            last_name="Lovelace",
            status="active",
        )
        session.add_all([company, suite, snapshot])
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
                        "company_name": " acme ",
                        "local_suite_number": "1200",
                        "desired_unifi_access_policy_names": "front door",
                        "desired_unifi_user_group_names": "employees",
                    }
                ]
            ),
            unifi_access_policies=[{"id": "policy-1", "name": "Front Door"}],
            unifi_user_groups=[{"id": "group-1", "name": "Employees"}],
        )
        session.commit()

        user = session.scalar(select(User).where(User.email == "ada@example.com"))

        assert summary.users_created == 1
        assert summary.errors == []
        assert user.company_id == company.id
        assert user.primary_suite_id == suite.id
        assert user.desired_unifi_access_policy_ids == ["policy-1"]
        assert user.desired_unifi_user_group_ids == ["group-1"]


def test_import_accepts_old_exporter_suite_number_field(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import Company, Suite, UnifiUser, User

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="120")
        snapshot = UnifiUser(unifi_user_id="u-1", email="ada@example.com", employee_number="120999", suite_number="120")
        session.add_all([company, suite, snapshot])
        session.commit()

        summary = import_bootstrap_users_csv(
            session,
            _csv_text(
                [
                    {
                        "promote": "yes",
                        "id": "u-1",
                        "email": "ada@example.com",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "company_name": "Acme",
                        "suite_number": "120",
                    }
                ]
            ),
        )
        session.commit()

        user = session.scalar(select(User).where(User.email == "ada@example.com"))
        assert summary.errors == []
        assert user.primary_suite_id == suite.id


def test_import_updates_linked_user_when_update_existing_is_yes(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import Company, Suite, UnifiUser, User

    with db_context() as session:
        company = Company(name="Acme")
        old_suite = Suite(suite_number="1100")
        new_suite = Suite(suite_number="1200")
        session.add_all([company, old_suite, new_suite])
        session.flush()
        existing = User(
            first_name="Ada",
            last_name="Old",
            email="ada@example.com",
            employee_number="E100",
            company_id=company.id,
            primary_suite_id=old_suite.id,
            desired_unifi_access_policy_ids=["old-policy"],
            desired_unifi_access_policy_names=["Old Policy"],
        )
        session.add(existing)
        session.flush()
        session.add(UnifiUser(unifi_user_id="u-1", local_user_id=existing.id, email="ada@example.com", employee_number="E100"))
        session.commit()

        summary = import_bootstrap_users_csv(
            session,
            _csv_text(
                [
                    {
                        "update_existing": "yes",
                        "unifi_user_id": "u-1",
                        "email": "ada@example.com",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "company_name": "Acme",
                        "local_suite_number": "1200",
                        "desired_unifi_access_policy_names": "Front Door",
                    }
                ]
            ),
            unifi_access_policies=[{"id": "policy-1", "name": "Front Door"}],
        )
        session.commit()

        user = session.get(User, existing.id)
        assert summary.users_updated == 1
        assert summary.errors == []
        assert user.last_name == "Lovelace"
        assert user.primary_suite_id == new_suite.id
        assert user.desired_unifi_access_policy_ids == ["policy-1"]


def test_import_links_existing_user_without_duplicate_and_skips_unmarked_rows(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import Company, Suite, UnifiUser, User

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        existing = User(first_name="Ada", last_name="Existing", email="ada@example.com", employee_number="E100")
        snapshot = UnifiUser(unifi_user_id="u-1", email="ada@example.com", employee_number="E100", first_name="Ada", last_name="Lovelace")
        session.add_all([company, suite, existing, snapshot])
        session.commit()

        row = {
            "promote": "yes",
            "unifi_user_id": "u-1",
            "email": "ada@example.com",
            "employee_number": "E100",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company_id": str(company.id),
            "local_suite_id": str(suite.id),
        }
        first_summary = import_bootstrap_users_csv(session, _csv_text([row, {"unifi_user_id": "u-1"}]))
        session.commit()
        second_summary = import_bootstrap_users_csv(session, _csv_text([row]))
        session.commit()

        users = session.scalars(select(User)).all()
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == "u-1"))

        assert len(users) == 1
        assert first_summary.users_created == 0
        assert first_summary.users_updated == 1
        assert first_summary.rows_skipped == 1
        assert first_summary.snapshots_linked == 1
        assert second_summary.rows_skipped == 1
        assert snapshot.local_user_id == existing.id


def test_import_reports_missing_reference_errors_without_importing_row(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import Company, UnifiUser, User

    with db_context() as session:
        session.add_all([Company(name="Acme"), UnifiUser(unifi_user_id="u-1", email="ada@example.com")])
        session.commit()
        summary = import_bootstrap_users_csv(
            session,
            _csv_text(
                [
                    {
                        "promote": "yes",
                        "unifi_user_id": "u-1",
                        "email": "ada@example.com",
                        "company_name": "Acme",
                        "suite_number": "404",
                        "desired_unifi_access_policy_names": "Missing Policy",
                    }
                ]
            ),
            unifi_access_policies=[{"id": "policy-1", "name": "Front Door"}],
        )

        assert summary.users_created == 0
        assert any("suite name '404' was not found" in error for error in summary.errors)
        assert any("UniFi Access Policy name 'Missing Policy' was not found" in error for error in summary.errors)
        assert session.scalar(select(User).where(User.email == "ada@example.com")) is None


def test_import_reports_ambiguous_name_errors_without_importing_row(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import Company, Suite, UnifiUser, User

    with db_context() as session:
        session.add_all(
            [
                Company(name="Acme"),
                Company(name=" acme "),
                Suite(suite_number="1200"),
                UnifiUser(unifi_user_id="u-1", email="ada@example.com", first_name="Ada", last_name="Lovelace", status="active"),
            ]
        )
        session.commit()
        summary = import_bootstrap_users_csv(
            session,
            _csv_text(
                [
                    {
                        "promote": "yes",
                        "unifi_user_id": "u-1",
                        "email": "ada@example.com",
                        "company_name": "ACME",
                        "local_suite_number": "1200",
                        "desired_unifi_access_policy_names": "front door",
                    }
                ]
            ),
            unifi_access_policies=[{"id": "policy-1", "name": "Front Door"}, {"id": "policy-2", "name": " front door "}],
        )

        assert summary.users_created == 0
        assert any("company name 'ACME' is ambiguous" in error for error in summary.errors)
        assert any("UniFi Access Policy name 'front door' is ambiguous" in error for error in summary.errors)
        assert session.scalar(select(User).where(User.email == "ada@example.com")) is None


def test_import_reports_missing_email_as_row_error(db_context):
    from app.import_export import import_bootstrap_users_csv
    from app.models import Company, Suite, UnifiUser, User

    with db_context() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        session.add_all([company, suite, UnifiUser(unifi_user_id="u-1", first_name="Ada", last_name="Lovelace")])
        session.commit()

        summary = import_bootstrap_users_csv(
            session,
            _csv_text([{"promote": "yes", "unifi_user_id": "u-1", "company_id": str(company.id), "local_suite_id": str(suite.id)}]),
        )

        assert summary.users_created == 0
        assert summary.errors == ["Row 2: email is required to create a new local registry user."]
        assert session.scalar(select(User)) is None
