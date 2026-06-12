from __future__ import annotations

import importlib
from pathlib import Path

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
        from app.models import Company, Suite, User

        company = Company(name="Globex")
        suite = Suite(suite_number="500")
        session.add_all([company, suite])
        session.flush()
        session.add(
            User(
                first_name="Grace",
                last_name="Hopper",
                email="grace@example.com",
                company_id=company.id,
                primary_suite_id=suite.id,
                status="active",
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
        assert run.status == "sent"
        assert Path(run.output_csv_path).read_text(encoding="utf-8").startswith("Full name,Email")
        assert verification is not None
        assert verification.status == "pending"

    assert list((export_dir / "email_previews").glob("*.html"))


@pytest.mark.asyncio
async def test_unifi_write_guard_blocks_phase1_writes(monkeypatch):
    monkeypatch.setenv("ENABLE_WRITES", "false")
    import app.config
    from app.unifi_client import UniFiAccessClient, WritesDisabledError

    app.config.get_settings.cache_clear()
    client = UniFiAccessClient()
    with pytest.raises(WritesDisabledError):
        await client.create_user({"email": "blocked@example.com"})

