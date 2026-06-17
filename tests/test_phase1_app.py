from __future__ import annotations

import io
import importlib
import csv
from pathlib import Path
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def app_context(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    export_dir = tmp_path / "exports"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_EMAIL", "false")
    monkeypatch.setenv("ENABLE_WRITES", "false")
    monkeypatch.setenv("UNIFI_ACCESS_TOKEN", "")

    import app.config
    import app.db
    import app.main

    app.config.get_settings.cache_clear()
    app.db.configure_database(f"sqlite:///{db_path}")
    app.db.Base.metadata.drop_all(bind=app.db.engine)
    app.db.init_db()
    importlib.reload(app.main)
    client = TestClient(app.main.app)
    return client, app.db.SessionLocal, export_dir


def create_admin_and_login(client: TestClient) -> None:
    response = client.post(
        "/setup-admin",
        data={"email": "admin@example.com", "password": "long-enough-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_admin_auth_required_and_first_admin_setup(app_context):
    client, session_factory, _ = app_context

    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    create_admin_and_login(client)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Admin Dashboard" in response.text


def test_company_suite_and_occupancy_creation(app_context):
    client, session_factory, _ = app_context
    create_admin_and_login(client)

    assert client.post("/admin/companies", data={"name": "Acme", "legal_name": "", "primary_contact_email": ""}).status_code == 200
    assert client.post("/admin/suites", data={"suite_number": "1200", "floor": "12", "building_area": "Tower"}).status_code == 200

    with session_factory() as session:
        from app.models import Company, CompanySuite, Suite

        company = session.scalar(select(Company).where(Company.name == "Acme"))
        suite = session.scalar(select(Suite).where(Suite.suite_number == "1200"))
        assert company is not None
        assert suite is not None

    assert client.post("/admin/company-suites", data={"company_id": company.id, "suite_id": suite.id, "occupancy_status": "active"}).status_code == 200
    with session_factory() as session:
        assert session.scalar(select(CompanySuite).where(CompanySuite.company_id == company.id, CompanySuite.suite_id == suite.id)) is not None


def test_access_request_approval_creates_dry_run_sync_job(app_context):
    client, session_factory, _ = app_context
    create_admin_and_login(client)

    response = client.post(
        "/request",
        data={
            "request_type": "new_access",
            "requested_for_first_name": "Ada",
            "requested_for_last_name": "Lovelace",
            "requested_for_email": "ada@example.com",
            "requester_name": "Manager",
            "requester_email": "manager@example.com",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with session_factory() as session:
        from app.models import AccessRequest

        access_request = session.scalar(select(AccessRequest))
        assert access_request.status == "submitted"
        request_id = access_request.id

    response = client.post(f"/admin/requests/{request_id}/approve", data={}, follow_redirects=False)
    assert response.status_code == 303

    with session_factory() as session:
        from app.models import AccessRequest, AuditLog, SyncJob

        access_request = session.get(AccessRequest, request_id)
        job = session.scalar(select(SyncJob).where(SyncJob.access_request_id == request_id))
        audit = session.scalar(select(AuditLog).where(AuditLog.action == "access_request.approved"))
        assert access_request.status == "pending_sync"
        assert job is not None
        assert job.job_type == "dry_run"
        assert "No UniFi write" in job.proposed_actions["message"]
        assert audit is not None


def test_report_generation_email_preview_and_verification(app_context):
    client, session_factory, export_dir = app_context
    create_admin_and_login(client)

    with session_factory() as session:
        from app.models import Company, Suite, UnifiUser, User

        company = Company(name="Globex")
        suite = Suite(suite_number="500")
        session.add_all([company, suite])
        session.flush()
        user = User(
            first_name="Grace",
            last_name="Hopper",
            email="grace@example.com",
            company_id=company.id,
            primary_suite_id=suite.id,
            status="active",
            desired_unifi_access_policy_names=["Suite 500"],
            desired_unifi_user_group_names=["Employees"],
        )
        session.add(user)
        session.flush()
        session.add(
            UnifiUser(
                local_user_id=user.id,
                unifi_user_id="u-grace",
                email="grace@example.com",
                status="active",
                access_policy_ids=["policy-1"],
                raw_snapshot_json={
                    "access_policy": [{"id": "policy-1", "name": "Front Door"}],
                    "groups": [{"id": "group-1", "name": "Staff"}],
                },
            )
        )
        session.commit()
        company_id = company.id

    response = client.post(
        "/admin/reports/company-users/send",
        data={"company_id": company_id, "recipient_email": "owner@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with session_factory() as session:
        from app.models import ReportRun, VerificationRequest

        run = session.scalar(select(ReportRun))
        verification = session.scalar(select(VerificationRequest))
        csv_text = Path(run.output_csv_path).read_text(encoding="utf-8")
        assert run.status == "sent"
        assert csv_text.startswith("Full name,Email")
        assert "Current UniFi Access Policies" in csv_text
        assert "Front Door" in csv_text
        assert "Suite 500" in csv_text
        assert "Staff" in csv_text
        assert "Employees" in csv_text
        assert verification is not None
        assert verification.status == "pending"

    assert list((export_dir / "email_previews").glob("*.html"))


def test_admin_bootstrap_export_and_import(app_context):
    client, session_factory, _ = app_context
    create_admin_and_login(client)

    with session_factory() as session:
        from app.models import Company, Suite, UnifiUser

        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        snapshot = UnifiUser(
            unifi_user_id="u-1",
            email="ada@example.com",
            employee_number="E100",
            first_name="Ada",
            last_name="Lovelace",
                status="active",
                access_policy_ids=["policy-1"],
                access_policy_names=["Front Door"],
                group_ids=["group-1"],
                group_names=["Employees"],
            )
        session.add_all([company, suite, snapshot])
        session.commit()
        company_id = company.id
        suite_id = suite.id

    response = client.get("/admin/bootstrap")
    assert response.status_code == 200
    assert "AccessProfile is a local optional template concept" in response.text

    response = client.get("/admin/bootstrap/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="all_unifi_users.csv"'
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["unifi_user_id"] == "u-1"
    assert rows[0]["id"] == "u-1"
    assert rows[0]["access_policy_names"] == "Front Door"
    assert rows[0]["group_names"] == "Employees"

    response = client.get("/admin/bootstrap/reference-export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            "all_unifi_users.csv",
            "companies.csv",
            "suites.csv",
            "unifi_access_policies.csv",
            "unifi_user_groups.csv",
        }

    from app.import_export import BOOTSTRAP_COLUMNS

    csv_output = io.StringIO()
    writer = csv.DictWriter(csv_output, fieldnames=BOOTSTRAP_COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "unifi_user_id": "u-1",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "employee_number": "E100",
            "promote": "yes",
            "company_id": str(company_id),
            "local_suite_id": str(suite_id),
            "desired_unifi_access_policy_ids": "policy-1",
            "desired_unifi_user_group_ids": "group-1",
            "notes": "Imported from bootstrap",
        }
    )
    csv_text = csv_output.getvalue()

    response = client.post(
        "/admin/bootstrap/import",
        files={"file": ("bootstrap.csv", csv_text, "text/csv")},
    )
    assert response.status_code == 200
    assert "Import Batch" in response.text
    assert "Ada Lovelace" in response.text

    with session_factory() as session:
        from app.models import ImportBatch, UnifiUser, User

        batch = session.scalar(select(ImportBatch).where(ImportBatch.source == "bootstrap_csv"))
        user = session.scalar(select(User).where(User.email == "ada@example.com"))
        assert batch is not None
        assert batch.status == "preview"
        assert batch.summary_json["create_count"] == 1
        assert user is None

    response = client.post(f"/admin/import-batches/{batch.id}/commit", follow_redirects=True)
    assert response.status_code == 200
    assert "committed" in response.text

    with session_factory() as session:
        from app.models import UnifiUser, User

        user = session.scalar(select(User).where(User.email == "ada@example.com"))
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == "u-1"))
        assert user is not None
        assert user.access_profile_id is None
        assert user.desired_unifi_access_policy_ids == ["policy-1"]
        assert user.desired_unifi_user_group_ids == ["group-1"]
        assert snapshot.local_user_id == user.id


def test_import_batch_commit_requires_admin(app_context):
    client, session_factory, _ = app_context
    with session_factory() as session:
        from app.models import ImportBatch

        batch = ImportBatch(source="bootstrap_csv", status="preview", summary_json={})
        session.add(batch)
        session.commit()
        batch_id = batch.id

    response = client.post(f"/admin/import-batches/{batch_id}/commit", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_base_template_dark_mode_and_css_theme(app_context):
    client, _session_factory, _ = app_context
    create_admin_and_login(client)

    response = client.get("/admin")
    assert response.status_code == 200
    assert "data-theme=\"light\"" in response.text
    assert "prefers-color-scheme: dark" in response.text
    assert "localStorage.setItem(\"theme\"" in response.text
    css = client.get("/static/styles.css").text
    assert "html[data-theme=\"dark\"]" in css
    assert ".field-changed" in css
    assert ".diff-before" in css
    assert ".btn-primary" in css


def test_admin_user_detail_displays_and_updates_fields(app_context):
    client, session_factory, _ = app_context
    create_admin_and_login(client)

    with session_factory() as session:
        from app.models import Company, Suite, UnifiUser, User

        company = Company(name="Acme")
        suite = Suite(suite_number="1200")
        session.add_all([company, suite])
        session.flush()
        user = User(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            employee_number="E100",
            company_id=company.id,
            primary_suite_id=suite.id,
            status="active",
        )
        session.add(user)
        session.flush()
        session.add(
            UnifiUser(
                local_user_id=user.id,
                unifi_user_id="u-1",
                email="ada@example.com",
                group_ids=["group-1"],
                group_names=["Employees"],
            )
        )
        session.commit()
        user_id = user.id
        company_id = company.id
        suite_id = suite.id

    response = client.get(f"/admin/users/{user_id}")
    assert response.status_code == 200
    assert "Current UniFi User Group Names" in response.text
    assert "Employees" in response.text

    response = client.post(
        f"/admin/users/{user_id}/update",
        data={
            "first_name": "Ada",
            "last_name": "Byron",
            "email": "ada@example.com",
            "employee_number": "E100",
            "company_id": str(company_id),
            "primary_suite_id": str(suite_id),
            "access_profile_id": "",
            "title": "Engineer",
            "phone": "555-0100",
            "department": "Math",
            "status": "active",
            "desired_unifi_access_policy_ids": "policy-1",
            "desired_unifi_access_policy_names": "Front Door",
            "desired_unifi_user_group_ids": "group-2",
            "desired_unifi_user_group_names": "Managers",
            "notes": "Updated locally",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    response = client.post(
        f"/admin/users/{user_id}/unifi-snapshot/update",
        data={
            "email": "ada@example.com",
            "email_status": "verified",
            "employee_number": "E100",
            "suite_number": "1200",
            "first_name": "Ada",
            "last_name": "Byron",
            "full_name": "Ada Byron",
            "phone": "555-0100",
            "username": "abyron",
            "alias": "Ada",
            "status": "active",
            "onboard_time": "2026-01-01T00:00:00Z",
            "access_policy_ids": "policy-1",
            "access_policy_names": "Front Door",
            "group_ids": "group-2",
            "group_names": "Managers",
            "nfc_card_count": "1",
            "touch_pass_status": "enabled",
            "touch_pass_last_activity": "2026-01-02T00:00:00Z",
            "license_plate_count": "0",
            "raw_user_json_file": "raw.json",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    with session_factory() as session:
        from app.models import UnifiUser, User

        user = session.get(User, user_id)
        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.local_user_id == user_id))

        assert user.last_name == "Byron"
        assert user.desired_unifi_user_group_names == ["Managers"]
        assert snapshot.group_ids == ["group-2"]
        assert snapshot.group_names == ["Managers"]


@pytest.mark.anyio
async def test_unifi_write_guard_blocks_phase1_writes(monkeypatch):
    monkeypatch.setenv("ENABLE_WRITES", "false")
    import app.config
    from app.unifi_client import UniFiAccessClient, WritesDisabledError

    app.config.get_settings.cache_clear()
    client = UniFiAccessClient()
    with pytest.raises(WritesDisabledError):
        await client.create_user({"email": "blocked@example.com"})
