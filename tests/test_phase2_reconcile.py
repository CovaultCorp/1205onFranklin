from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select


@pytest.fixture()
def db_context(tmp_path, monkeypatch):
    db_path = tmp_path / "phase2.db"
    export_dir = tmp_path / "exports"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("EXPORT_DIR", str(export_dir))
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_WRITES", "false")
    monkeypatch.setenv("UNIFI_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("UNIFI_ACCESS_BASE_URL", "https://unifi.test")
    monkeypatch.setenv("UNIFI_ACCESS_PAGE_SIZE", "2")

    import app.config
    import app.db

    app.config.get_settings.cache_clear()
    app.db.configure_database(f"sqlite:///{db_path}")
    app.db.Base.metadata.drop_all(bind=app.db.engine)
    app.db.init_db()
    return app.db.SessionLocal, export_dir


class FakeUniFiClient:
    def __init__(self, users):
        self.users = users
        self.write_calls = 0

    async def list_users(self, expand_access_policy: bool = True):
        assert expand_access_policy is True
        return self.users

    async def create_user(self, payload):
        self.write_calls += 1
        raise AssertionError("reconciliation must not call write methods")


@pytest.mark.anyio
async def test_unifi_read_methods_paginate_and_fetch_resources(monkeypatch):
    monkeypatch.setenv("UNIFI_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("UNIFI_ACCESS_BASE_URL", "https://unifi.test")
    monkeypatch.setenv("UNIFI_ACCESS_PAGE_SIZE", "2")
    import app.config
    from app.unifi_client import UniFiAccessClient

    app.config.get_settings.cache_clear()
    requested_urls: list[str] = []
    requested_params: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        requested_params.append(request.url.query.decode("utf-8"))
        if request.url.path == "/api/v1/developer/users/abc":
            return httpx.Response(200, json={"data": {"id": "abc", "email": "abc@example.com"}})
        if request.url.path == "/api/v1/developer/access_policies":
            return httpx.Response(200, json={"data": [{"id": "policy-1"}]})
        if request.url.path == "/api/v1/developer/user_groups":
            return httpx.Response(200, json={"data": [{"id": "group-1"}]})
        if "page_num=1" in request.url.query.decode("utf-8"):
            return httpx.Response(200, json={"data": [{"id": "u1"}, {"id": "u2"}]})
        return httpx.Response(200, json={"data": [{"id": "u3"}]})

    client = UniFiAccessClient(transport=httpx.MockTransport(handler))

    users = await client.list_users()
    user = await client.get_user("abc")
    policies = await client.list_access_policies()
    groups = await client.list_user_groups()

    assert [item["id"] for item in users] == ["u1", "u2", "u3"]
    assert user["email"] == "abc@example.com"
    assert policies == [{"id": "policy-1"}]
    assert groups == [{"id": "group-1"}]
    assert any("expand%5B%5D=access_policy" in params for params in requested_params)
    assert any("expand%5B%5D=groups" in params for params in requested_params)
    assert any(url.endswith("/api/v1/developer/access_policies?page_num=1&page_size=2") for url in requested_urls)


@pytest.mark.anyio
async def test_reconciliation_matches_by_mapping_employee_then_email(db_context):
    session_factory, _ = db_context
    from app.models import Company, Suite, UnifiUser, User
    from app.reconcile import run_unifi_reconciliation

    with session_factory() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="100")
        session.add_all([company, suite])
        session.flush()
        mapped = User(first_name="Mapped", last_name="User", email="mapped-local@example.com", employee_number="M1", company_id=company.id, primary_suite_id=suite.id, status="active")
        employee = User(first_name="Employee", last_name="Match", email="employee@example.com", employee_number="E1", company_id=company.id, primary_suite_id=suite.id, status="active")
        email = User(first_name="Email", last_name="Match", email="email@example.com", employee_number="E2", company_id=company.id, primary_suite_id=suite.id, status="active")
        session.add_all([mapped, employee, email])
        session.flush()
        session.add(UnifiUser(local_user_id=mapped.id, unifi_user_id="mapped-unifi", email="old@example.com"))
        session.commit()

        job, summary = await run_unifi_reconciliation(
            session,
            client=FakeUniFiClient(
                [
                    {"id": "mapped-unifi", "email": "changed@example.com", "employeeNumber": "DIFFERENT", "firstName": "Mapped", "lastName": "User", "status": "active"},
                    {"id": "employee-unifi", "email": "other@example.com", "employeeNumber": "E1", "firstName": "Employee", "lastName": "Match", "status": "active"},
                    {"id": "email-unifi", "email": "email@example.com", "employeeNumber": "OTHER", "firstName": "Email", "lastName": "Match", "status": "active"},
                ]
            ),
        )
        session.commit()

        snapshots = {item.unifi_user_id: item for item in session.scalars(select(UnifiUser)).all()}
        assert snapshots["mapped-unifi"].local_user_id == mapped.id
        assert snapshots["employee-unifi"].local_user_id == employee.id
        assert snapshots["email-unifi"].local_user_id == email.id
        assert summary.matched_users == 3
        assert job.job_type == "reconcile"
        assert job.proposed_actions["dry_run"] is True


@pytest.mark.anyio
async def test_reconciliation_detects_conflicts_idempotently_and_creates_dry_run_job(db_context):
    session_factory, _ = db_context
    from app.models import AccessProfile, Company, Conflict, Suite, SyncJob, UnifiUser, User
    from app.reconcile import run_unifi_reconciliation

    users = [
        {"id": "u-missing-local", "email": "external@example.com", "employeeNumber": "X1", "firstName": "External", "lastName": "User", "status": "active"},
        {"id": "u-policy", "email": "policy@example.com", "employeeNumber": "P1", "firstName": "Policy", "lastName": "User", "status": "active", "access_policy": [{"id": "wrong-policy"}]},
        {"id": "u-no-company", "email": "nocompany@example.com", "employeeNumber": "NC1", "firstName": "No", "lastName": "Company", "status": "active"},
        {"id": "u-inactive-suite", "email": "inactive-suite@example.com", "employeeNumber": "IS1", "firstName": "Inactive", "lastName": "Suite", "status": "active"},
        {"id": "u-dup-a", "email": "dup@example.com", "employeeNumber": "DUP1", "firstName": "Dup", "lastName": "A", "status": "active"},
        {"id": "u-dup-b", "email": "dup@example.com", "employeeNumber": "DUP1", "firstName": "Dup", "lastName": "B", "status": "active"},
    ]

    with session_factory() as session:
        company = Company(name="Acme")
        inactive_company = Company(name="Closed Co", status="inactive")
        suite = Suite(suite_number="100")
        inactive_suite = Suite(suite_number="200", status="inactive")
        session.add_all([company, inactive_company, suite, inactive_suite])
        session.flush()
        session.add(AccessProfile(name="Acme Default", default_for_company_id=company.id, unifi_access_policy_ids=["expected-policy"]))
        session.add_all(
            [
                User(first_name="Policy", last_name="User", email="policy@example.com", employee_number="P1", company_id=company.id, primary_suite_id=suite.id, status="active"),
                User(first_name="No", last_name="Company", email="nocompany@example.com", employee_number="NC1", status="active"),
                User(first_name="Inactive", last_name="Suite", email="inactive-suite@example.com", employee_number="IS1", company_id=company.id, primary_suite_id=inactive_suite.id, status="active"),
                User(first_name="Local", last_name="Only", email="local-only@example.com", employee_number="L1", company_id=company.id, primary_suite_id=suite.id, status="active"),
                User(first_name="Closed", last_name="Company", email="closed@example.com", employee_number="C1", company_id=inactive_company.id, primary_suite_id=suite.id, status="active"),
            ]
        )
        session.commit()

        first_job, first_summary = await run_unifi_reconciliation(session, client=FakeUniFiClient(users))
        session.commit()
        second_job, second_summary = await run_unifi_reconciliation(session, client=FakeUniFiClient(users))
        session.commit()

        conflicts = session.scalars(select(Conflict)).all()
        conflict_types = {conflict.conflict_type for conflict in conflicts}
        assert "unifi_active_user_not_found_locally" in conflict_types
        assert "local_active_user_not_found_in_unifi" in conflict_types
        assert "unifi_user_no_local_company" in conflict_types
        assert "unifi_user_no_local_suite" in conflict_types
        assert "user_in_inactive_suite" in conflict_types
        assert "access_policy_mismatch" in conflict_types
        assert "duplicate_email" in conflict_types
        assert "duplicate_employee_number" in conflict_types
        assert first_summary.conflicts_created > 0
        assert second_summary.conflicts_created == 0
        assert second_summary.conflicts_existing >= first_summary.conflicts_created

        snapshots = session.scalars(select(UnifiUser)).all()
        assert len(snapshots) == len(users)
        jobs = session.scalars(select(SyncJob).where(SyncJob.job_type == "reconcile")).all()
        assert len(jobs) == 2
        assert first_job.proposed_actions["dry_run"] is True
        assert first_job.proposed_actions["actions"]
        assert second_job.result_json["conflicts_created"] == 0


@pytest.mark.anyio
async def test_reconciliation_does_not_call_write_methods(db_context):
    session_factory, _ = db_context
    from app.models import Company, Suite, User
    from app.reconcile import run_unifi_reconciliation

    fake_client = FakeUniFiClient(
        [{"id": "u1", "email": "ada@example.com", "employeeNumber": "E1", "firstName": "Ada", "lastName": "Lovelace", "status": "active"}]
    )
    with session_factory() as session:
        company = Company(name="Acme")
        suite = Suite(suite_number="100")
        session.add_all([company, suite])
        session.flush()
        session.add(User(first_name="Ada", last_name="Lovelace", email="ada@example.com", employee_number="E1", company_id=company.id, primary_suite_id=suite.id, status="active"))
        session.commit()
        await run_unifi_reconciliation(session, client=fake_client)
        session.commit()

    assert fake_client.write_calls == 0


@pytest.mark.anyio
async def test_reconciliation_stores_exporter_compatible_normalized_fields(db_context):
    session_factory, _ = db_context
    from app.models import UnifiUser
    from app.reconcile import run_unifi_reconciliation

    with session_factory() as session:
        job, summary = await run_unifi_reconciliation(
            session,
            client=FakeUniFiClient(
                [
                    {
                        "uuid": "u-compat",
                        "givenName": "Ada",
                        "familyName": "Lovelace",
                        "userEmail": "Ada@Example.com",
                        "emailStatus": "verified",
                        "employeeId": "120999",
                        "phoneNumber": "555-0100",
                        "userName": "alovelace",
                        "alias": "Countess",
                        "state": "active",
                        "onboardTime": "2026-01-02T03:04:05Z",
                        "accessPolicies": [{"policyId": "policy-1", "policyName": "Front Door"}],
                        "userGroups": [{"groupId": "group-1", "groupName": "Employees"}],
                        "nfcCards": [{"id": "card-1"}],
                        "touchPass": {"status": "enabled", "lastActivity": "2026-01-03T00:00:00Z"},
                        "licensePlates": [{"plate": "ABC"}],
                    }
                ]
            ),
        )
        session.commit()

        snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == "u-compat"))

        assert summary.email_key_counts == {"userEmail": 1}
        assert summary.users_without_email_key == 0
        assert job.result_json["email_key_counts"] == {"userEmail": 1}
        assert snapshot.email == "ada@example.com"
        assert snapshot.email_status == "verified"
        assert snapshot.suite_number == "120"
        assert snapshot.phone == "555-0100"
        assert snapshot.username == "alovelace"
        assert snapshot.alias == "Countess"
        assert snapshot.onboard_time == "2026-01-02T03:04:05Z"
        assert snapshot.access_policy_ids == ["policy-1"]
        assert snapshot.access_policy_names == ["Front Door"]
        assert snapshot.group_ids == ["group-1"]
        assert snapshot.group_names == ["Employees"]
        assert snapshot.nfc_card_count == 1
        assert snapshot.touch_pass_status == "enabled"
        assert snapshot.touch_pass_last_activity == "2026-01-03T00:00:00Z"
        assert snapshot.license_plate_count == 1
        assert snapshot.raw_snapshot_json["nfcCards"] == "[REDACTED]"
        assert snapshot.raw_snapshot_json["licensePlates"] == "[REDACTED]"


@pytest.mark.anyio
async def test_unifi_write_guard_still_blocks_writes(monkeypatch):
    monkeypatch.setenv("ENABLE_WRITES", "false")
    import app.config
    from app.unifi_client import UniFiAccessClient, WritesDisabledError

    app.config.get_settings.cache_clear()
    client = UniFiAccessClient()
    with pytest.raises(WritesDisabledError):
        await client.set_user_status("u1", "inactive")
