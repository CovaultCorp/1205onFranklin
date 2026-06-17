from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_session
from app.import_export import build_bootstrap_reference_zip, commit_import_batch, create_bootstrap_import_batch, export_all_unifi_users_csv
from app.models import (
    AccessProfile,
    AccessRequest,
    Company,
    CompanySuite,
    Conflict,
    ImportBatch,
    ImportBatchRow,
    PortalAccount,
    ReportRun,
    Suite,
    SyncJob,
    UnifiUser,
    User,
    UserSuiteAssignment,
    utcnow,
)
from app.reconcile import run_unifi_reconciliation
from app.security import require_admin
from app.unifi_client import UniFiAccessClient

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def _csv_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _list_values(value: str) -> list[str]:
    normalized = value.replace("\n", ";").replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _optional_int(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@router.get("", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    stale_cutoff = utcnow() - timedelta(days=90)
    stats = {
        "active_users": session.scalar(select(func.count(User.id)).where(User.status == "active")) or 0,
        "missing_company": session.scalar(select(func.count(User.id)).where(User.company_id.is_(None))) or 0,
        "missing_suite": session.scalar(select(func.count(User.id)).where(User.primary_suite_id.is_(None))) or 0,
        "stale_verification": session.scalar(
            select(func.count(User.id)).where(User.status == "active", (User.last_verified_at.is_(None)) | (User.last_verified_at < stale_cutoff))
        )
        or 0,
        "pending_requests": session.scalar(
            select(func.count(AccessRequest.id)).where(AccessRequest.status.in_(["submitted", "pending_approval"]))
        )
        or 0,
        "open_conflicts": session.scalar(select(func.count(Conflict.id)).where(Conflict.status == "open")) or 0,
        "sync_failures": session.scalar(select(func.count(SyncJob.id)).where(SyncJob.status == "failed")) or 0,
        "unifi_snapshots": session.scalar(select(func.count(UnifiUser.id))) or 0,
        "unmatched_unifi_snapshots": session.scalar(
            select(func.count(UnifiUser.id)).where(UnifiUser.local_user_id.is_(None))
        )
        or 0,
    }
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "account": account,
            "stats": stats,
            "recent_reports": session.scalars(select(ReportRun).order_by(ReportRun.created_at.desc()).limit(5)).all(),
            "recent_sync_jobs": session.scalars(select(SyncJob).order_by(SyncJob.created_at.desc()).limit(5)).all(),
        },
    )


@router.get("/requests", response_class=HTMLResponse)
def list_requests(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "admin/requests.html",
        {"account": account, "requests": session.scalars(select(AccessRequest).order_by(AccessRequest.created_at.desc())).all()},
    )


@router.get("/requests/{request_id}", response_class=HTMLResponse)
def request_detail(request: Request, request_id: int, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    access_request = session.get(AccessRequest, request_id)
    return templates.TemplateResponse(
        request,
        "admin/request_detail.html",
        {
            "account": account,
            "access_request": access_request,
            "companies": session.scalars(select(Company).order_by(Company.name)).all(),
            "suites": session.scalars(select(Suite).order_by(Suite.suite_number)).all(),
            "profiles": session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all(),
        },
    )


@router.post("/requests/{request_id}/approve")
def approve_request(
    request: Request,
    request_id: int,
    requested_for_company_id: int | None = Form(None),
    requested_for_suite_id: int | None = Form(None),
    requested_access_profile_id: int | None = Form(None),
    admin_notes: str = Form(""),
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    access_request = session.get(AccessRequest, request_id)
    if access_request is None:
        return RedirectResponse("/admin/requests", status_code=303)
    before = {"status": access_request.status}
    access_request.requested_for_company_id = requested_for_company_id
    access_request.requested_for_suite_id = requested_for_suite_id
    access_request.requested_access_profile_id = requested_access_profile_id
    access_request.admin_notes = admin_notes or None
    access_request.status = "pending_sync"
    access_request.approved_by_account_id = account.id
    access_request.approved_at = utcnow()
    job = SyncJob(
        access_request_id=access_request.id,
        job_type="dry_run",
        status="pending",
        proposed_actions={
            "request_id": access_request.id,
            "request_type": access_request.request_type,
            "target_email": access_request.requested_for_email,
            "message": "Phase 1 dry run only. No UniFi write API will be called.",
        },
    )
    session.add(job)
    audit(
        session,
        action="access_request.approved",
        target_type="AccessRequest",
        target_id=access_request.id,
        actor=account,
        request=request,
        before=before,
        after={"status": access_request.status, "sync_job": "dry_run"},
    )
    session.commit()
    return RedirectResponse(f"/admin/requests/{access_request.id}", status_code=303)


@router.post("/requests/{request_id}/deny")
def deny_request(
    request: Request,
    request_id: int,
    denial_reason: str = Form(...),
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    access_request = session.get(AccessRequest, request_id)
    if access_request:
        before = {"status": access_request.status}
        access_request.status = "denied"
        access_request.denial_reason = denial_reason
        access_request.denied_by_account_id = account.id
        access_request.denied_at = utcnow()
        audit(session, action="access_request.denied", target_type="AccessRequest", target_id=request_id, actor=account, request=request, before=before, after={"status": "denied"})
        session.commit()
    return RedirectResponse(f"/admin/requests/{request_id}", status_code=303)


@router.post("/requests/{request_id}/needs-info")
def needs_info(request_id: int, admin_notes: str = Form(""), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    access_request = session.get(AccessRequest, request_id)
    if access_request:
        access_request.status = "needs_info"
        access_request.admin_notes = admin_notes or None
        session.commit()
    return RedirectResponse(f"/admin/requests/{request_id}", status_code=303)


@router.post("/requests/{request_id}/sync")
def dry_run_sync(request_id: int, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    job = session.scalar(select(SyncJob).where(SyncJob.access_request_id == request_id).order_by(SyncJob.created_at.desc()))
    if job:
        job.status = "succeeded"
        job.attempt_count += 1
        job.result_json = {"dry_run": True, "message": "No UniFi writes attempted in Phase 1."}
        job.completed_at = utcnow()
        session.commit()
    return RedirectResponse(f"/admin/requests/{request_id}", status_code=303)


@router.get("/users", response_class=HTMLResponse)
def users(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "admin/users.html", {"account": account, "users": session.scalars(select(User).order_by(User.last_name, User.first_name)).all()})


@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_detail(request: Request, user_id: int, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    user = session.get(User, user_id)
    unifi_user = session.scalar(select(UnifiUser).where(UnifiUser.local_user_id == user_id))
    return templates.TemplateResponse(
        request,
        "admin/user_detail.html",
        {
            "account": account,
            "user": user,
            "unifi_user": unifi_user,
            "companies": session.scalars(select(Company).order_by(Company.name)).all(),
            "suites": session.scalars(select(Suite).order_by(Suite.suite_number)).all(),
            "profiles": session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all(),
        },
    )


@router.post("/users/{user_id}/update")
def update_user_detail(
    request: Request,
    user_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    employee_number: str = Form(""),
    company_id: str = Form(""),
    primary_suite_id: str = Form(""),
    access_profile_id: str = Form(""),
    title: str = Form(""),
    phone: str = Form(""),
    department: str = Form(""),
    status: str = Form("pending"),
    desired_unifi_access_policy_ids: str = Form(""),
    desired_unifi_access_policy_names: str = Form(""),
    desired_unifi_user_group_ids: str = Form(""),
    desired_unifi_user_group_names: str = Form(""),
    notes: str = Form(""),
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    user = session.get(User, user_id)
    if user is None:
        return RedirectResponse("/admin/users", status_code=303)
    before = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "employee_number": user.employee_number,
        "company_id": user.company_id,
        "primary_suite_id": user.primary_suite_id,
        "access_profile_id": user.access_profile_id,
        "status": user.status,
        "desired_unifi_access_policy_ids": user.desired_unifi_access_policy_ids or [],
        "desired_unifi_user_group_ids": user.desired_unifi_user_group_ids or [],
    }
    user.first_name = first_name
    user.last_name = last_name
    user.email = email.strip().lower()
    user.employee_number = employee_number.strip() or None
    user.company_id = _optional_int(company_id)
    user.primary_suite_id = _optional_int(primary_suite_id)
    user.access_profile_id = _optional_int(access_profile_id)
    user.title = title.strip() or None
    user.phone = phone.strip() or None
    user.department = department.strip() or None
    user.status = status
    user.desired_unifi_access_policy_ids = _list_values(desired_unifi_access_policy_ids)
    user.desired_unifi_access_policy_names = _list_values(desired_unifi_access_policy_names)
    user.desired_unifi_user_group_ids = _list_values(desired_unifi_user_group_ids)
    user.desired_unifi_user_group_names = _list_values(desired_unifi_user_group_names)
    user.notes = notes.strip() or None
    if user.primary_suite_id:
        existing = session.scalar(
            select(UserSuiteAssignment).where(
                UserSuiteAssignment.user_id == user.id,
                UserSuiteAssignment.suite_id == user.primary_suite_id,
                UserSuiteAssignment.assignment_type == "primary",
                UserSuiteAssignment.active.is_(True),
            )
        )
        if existing:
            existing.company_id = user.company_id
        else:
            session.add(
                UserSuiteAssignment(
                    user_id=user.id,
                    suite_id=user.primary_suite_id,
                    company_id=user.company_id,
                    assignment_type="primary",
                    active=True,
                )
            )
    audit(
        session,
        action="user.updated",
        target_type="User",
        target_id=user.id,
        actor=account,
        request=request,
        before=before,
        after={
            "email": user.email,
            "company_id": user.company_id,
            "primary_suite_id": user.primary_suite_id,
            "status": user.status,
            "desired_unifi_access_policy_ids": user.desired_unifi_access_policy_ids or [],
            "desired_unifi_user_group_ids": user.desired_unifi_user_group_ids or [],
        },
    )
    session.commit()
    return RedirectResponse(f"/admin/users/{user.id}", status_code=303)


@router.post("/users/{user_id}/unifi-snapshot/update")
def update_user_unifi_snapshot(
    request: Request,
    user_id: int,
    email: str = Form(""),
    email_status: str = Form(""),
    employee_number: str = Form(""),
    suite_number: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    full_name: str = Form(""),
    phone: str = Form(""),
    username: str = Form(""),
    alias: str = Form(""),
    status: str = Form(""),
    onboard_time: str = Form(""),
    access_policy_ids: str = Form(""),
    access_policy_names: str = Form(""),
    group_ids: str = Form(""),
    group_names: str = Form(""),
    nfc_card_count: str = Form(""),
    touch_pass_status: str = Form(""),
    touch_pass_last_activity: str = Form(""),
    license_plate_count: str = Form(""),
    raw_user_json_file: str = Form(""),
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    unifi_user = session.scalar(select(UnifiUser).where(UnifiUser.local_user_id == user_id))
    if unifi_user is None:
        return RedirectResponse(f"/admin/users/{user_id}", status_code=303)
    before = {
        "email": unifi_user.email,
        "group_ids": unifi_user.group_ids or [],
        "group_names": unifi_user.group_names or [],
        "access_policy_ids": unifi_user.access_policy_ids or [],
    }
    unifi_user.email = email.strip().lower() or None
    unifi_user.email_status = email_status.strip() or None
    unifi_user.employee_number = employee_number.strip() or None
    unifi_user.suite_number = suite_number.strip() or None
    unifi_user.first_name = first_name.strip() or None
    unifi_user.last_name = last_name.strip() or None
    unifi_user.full_name = full_name.strip() or None
    unifi_user.phone = phone.strip() or None
    unifi_user.username = username.strip() or None
    unifi_user.alias = alias.strip() or None
    unifi_user.status = status.strip().lower() or None
    unifi_user.onboard_time = onboard_time.strip() or None
    unifi_user.access_policy_ids = _list_values(access_policy_ids)
    unifi_user.access_policy_names = _list_values(access_policy_names)
    unifi_user.group_ids = _list_values(group_ids)
    unifi_user.group_names = _list_values(group_names)
    unifi_user.nfc_card_count = _optional_int(nfc_card_count)
    unifi_user.touch_pass_status = touch_pass_status.strip() or None
    unifi_user.touch_pass_last_activity = touch_pass_last_activity.strip() or None
    unifi_user.license_plate_count = _optional_int(license_plate_count)
    unifi_user.raw_user_json_file = raw_user_json_file.strip() or None
    audit(
        session,
        action="unifi_snapshot.updated_locally",
        target_type="UnifiUser",
        target_id=unifi_user.id,
        actor=account,
        request=request,
        before=before,
        after={
            "email": unifi_user.email,
            "group_ids": unifi_user.group_ids or [],
            "group_names": unifi_user.group_names or [],
            "access_policy_ids": unifi_user.access_policy_ids or [],
        },
    )
    session.commit()
    return RedirectResponse(f"/admin/users/{user_id}", status_code=303)


@router.get("/companies", response_class=HTMLResponse)
def companies(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "admin/companies.html", {"account": account, "companies": session.scalars(select(Company).order_by(Company.name)).all()})


@router.post("/companies")
def create_company(name: str = Form(...), legal_name: str = Form(""), primary_contact_email: str = Form(""), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    session.add(Company(name=name, legal_name=legal_name or None, primary_contact_email=primary_contact_email or None))
    session.commit()
    return RedirectResponse("/admin/companies", status_code=303)


@router.post("/companies/{company_id}/update")
def update_company(company_id: int, name: str = Form(...), status: str = Form("active"), notes: str = Form(""), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    company = session.get(Company, company_id)
    if company:
        company.name = name
        company.status = status
        company.notes = notes or None
        session.commit()
    return RedirectResponse("/admin/companies", status_code=303)


@router.get("/suites", response_class=HTMLResponse)
def suites(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "admin/suites.html", {"account": account, "suites": session.scalars(select(Suite).order_by(Suite.suite_number)).all()})


@router.post("/suites")
def create_suite(suite_number: str = Form(...), floor: str = Form(""), building_area: str = Form(""), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    session.add(Suite(suite_number=suite_number, floor=floor or None, building_area=building_area or None))
    session.commit()
    return RedirectResponse("/admin/suites", status_code=303)


@router.post("/suites/{suite_id}/update")
def update_suite(suite_id: int, suite_number: str = Form(...), status: str = Form("active"), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    suite = session.get(Suite, suite_id)
    if suite:
        suite.suite_number = suite_number
        suite.status = status
        session.commit()
    return RedirectResponse("/admin/suites", status_code=303)


@router.get("/company-suites", response_class=HTMLResponse)
def company_suites(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "admin/company_suites.html",
        {
            "account": account,
            "company_suites": session.scalars(select(CompanySuite).order_by(CompanySuite.created_at.desc())).all(),
            "companies": session.scalars(select(Company).order_by(Company.name)).all(),
            "suites": session.scalars(select(Suite).order_by(Suite.suite_number)).all(),
        },
    )


@router.post("/company-suites")
def create_company_suite(company_id: int = Form(...), suite_id: int = Form(...), occupancy_status: str = Form("active"), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    session.add(CompanySuite(company_id=company_id, suite_id=suite_id, occupancy_status=occupancy_status))
    session.commit()
    return RedirectResponse("/admin/company-suites", status_code=303)


@router.get("/access-profiles", response_class=HTMLResponse)
def access_profiles(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "admin/access_profiles.html", {"account": account, "profiles": session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all()})


@router.post("/access-profiles")
def create_access_profile(name: str = Form(...), description: str = Form(""), unifi_access_policy_ids: str = Form(""), unifi_user_group_ids: str = Form(""), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    session.add(AccessProfile(name=name, description=description or None, unifi_access_policy_ids=_csv_ids(unifi_access_policy_ids), unifi_user_group_ids=_csv_ids(unifi_user_group_ids)))
    session.commit()
    return RedirectResponse("/admin/access-profiles", status_code=303)


@router.post("/access-profiles/{profile_id}/update")
def update_access_profile(profile_id: int, name: str = Form(...), active: bool = Form(False), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    profile = session.get(AccessProfile, profile_id)
    if profile:
        profile.name = name
        profile.active = active
        session.commit()
    return RedirectResponse("/admin/access-profiles", status_code=303)


@router.get("/conflicts", response_class=HTMLResponse)
def conflicts(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "admin/conflicts.html",
        {
            "account": account,
            "conflicts": session.scalars(select(Conflict).order_by(Conflict.created_at.desc())).all(),
            "open_count": session.scalar(select(func.count(Conflict.id)).where(Conflict.status == "open")) or 0,
        },
    )


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: int, status: str = Form("resolved"), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    conflict = session.get(Conflict, conflict_id)
    if conflict:
        conflict.status = status
        conflict.resolved_by_account_id = account.id
        conflict.resolved_at = utcnow()
        session.commit()
    return RedirectResponse("/admin/conflicts", status_code=303)


@router.get("/sync-jobs", response_class=HTMLResponse)
def sync_jobs(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    last_reconcile = session.scalar(select(SyncJob).where(SyncJob.job_type == "reconcile").order_by(SyncJob.created_at.desc()))
    return templates.TemplateResponse(
        request,
        "admin/sync_jobs.html",
        {
            "account": account,
            "sync_jobs": session.scalars(select(SyncJob).order_by(SyncJob.created_at.desc())).all(),
            "last_reconcile": last_reconcile,
        },
    )


@router.post("/reconcile/run")
async def run_reconcile(session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    job, _summary = await run_unifi_reconciliation(session)
    session.commit()
    import_batch_id = (job.result_json or {}).get("import_batch_id")
    if import_batch_id:
        return RedirectResponse(f"/admin/import-batches/{import_batch_id}", status_code=303)
    return RedirectResponse("/admin/sync-jobs", status_code=303)


@router.get("/bootstrap", response_class=HTMLResponse)
def bootstrap_users(
    request: Request,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    unmatched = session.scalars(
        select(UnifiUser).where(UnifiUser.local_user_id.is_(None)).order_by(UnifiUser.email, UnifiUser.unifi_user_id)
    ).all()
    return templates.TemplateResponse(
        request,
        "admin/bootstrap.html",
        {
            "account": account,
            "unmatched": unmatched,
            "companies": session.scalars(select(Company).order_by(Company.name)).all(),
            "suites": session.scalars(select(Suite).order_by(Suite.suite_number)).all(),
            "profiles": session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all(),
            "recent_batches": session.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(10)).all(),
        },
    )


@router.get("/bootstrap/export")
async def export_bootstrap_users(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    unifi_client = UniFiAccessClient()
    csv_text = export_all_unifi_users_csv(
        session,
        unifi_access_policies=await unifi_client.list_access_policies(),
        unifi_user_groups=await unifi_client.list_user_groups(),
    )
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="all_unifi_users.csv"'},
    )


@router.get("/bootstrap/reference-export")
async def export_bootstrap_reference(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    unifi_client = UniFiAccessClient()
    archive = build_bootstrap_reference_zip(
        session,
        unifi_access_policies=await unifi_client.list_access_policies(),
        unifi_user_groups=await unifi_client.list_user_groups(),
    )
    return Response(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="bootstrap_reference_export.zip"'},
    )


@router.post("/bootstrap/import")
async def import_bootstrap_users_compat(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    return await preview_bootstrap_users(request, file, session, account)


@router.post("/bootstrap/import/preview")
async def import_bootstrap_users(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    return await preview_bootstrap_users(request, file, session, account)


async def preview_bootstrap_users(
    request: Request,
    file: UploadFile,
    session: Session,
    account: PortalAccount,
):
    csv_text = (await file.read()).decode("utf-8-sig")
    unifi_client = UniFiAccessClient()
    batch = create_bootstrap_import_batch(
        session,
        csv_text,
        unifi_access_policies=await unifi_client.list_access_policies(),
        unifi_user_groups=await unifi_client.list_user_groups(),
        actor_account_id=account.id,
        filename=file.filename,
    )
    session.commit()
    return RedirectResponse(f"/admin/import-batches/{batch.id}", status_code=303)


@router.get("/import-batches/{batch_id}", response_class=HTMLResponse)
def import_batch_detail(
    request: Request,
    batch_id: int,
    action: str = "all",
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        return RedirectResponse("/admin/bootstrap", status_code=303)
    row_query = select(ImportBatchRow).where(ImportBatchRow.import_batch_id == batch.id).order_by(ImportBatchRow.id)
    if action != "all":
        row_query = row_query.where(ImportBatchRow.action == action)
    rows = session.scalars(row_query).all()
    has_errors = bool(batch.summary_json.get("error_count")) or any(row.validation_errors_json for row in batch.rows)
    return templates.TemplateResponse(
        request,
        "admin/import_batch_detail.html",
        {
            "account": account,
            "batch": batch,
            "rows": rows,
            "active_filter": action,
            "has_errors": has_errors,
        },
    )


@router.post("/import-batches/{batch_id}/commit")
def commit_import_batch_route(
    request: Request,
    batch_id: int,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        return RedirectResponse("/admin/bootstrap", status_code=303)
    commit_import_batch(
        session,
        batch,
        actor_account_id=account.id,
        actor_email=account.email,
        ip_address=request.client.host if request.client else None,
    )
    session.commit()
    return RedirectResponse(f"/admin/import-batches/{batch.id}", status_code=303)


@router.post("/import-batches/{batch_id}/cancel")
def cancel_import_batch(
    batch_id: int,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    batch = session.get(ImportBatch, batch_id)
    if batch and batch.status == "preview":
        batch.status = "cancelled"
        batch.last_error = None
        session.commit()
    return RedirectResponse(f"/admin/import-batches/{batch_id}", status_code=303)
