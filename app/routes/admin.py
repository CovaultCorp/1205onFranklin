from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_session
from app.import_export import build_bootstrap_reference_zip, export_all_unifi_users_csv, import_bootstrap_users_csv
from app.models import (
    AccessProfile,
    AccessRequest,
    Company,
    CompanySuite,
    Conflict,
    PortalAccount,
    ReportRun,
    Suite,
    SyncJob,
    UnifiUser,
    User,
    utcnow,
)
from app.reconcile import run_unifi_reconciliation
from app.security import require_admin
from app.unifi_client import UniFiAccessClient

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def _csv_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
    return templates.TemplateResponse(request, "admin/user_detail.html", {"account": account, "user": session.get(User, user_id)})


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
    await run_unifi_reconciliation(session)
    session.commit()
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
            "summary": None,
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


@router.post("/bootstrap/import", response_class=HTMLResponse)
async def import_bootstrap_users(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(require_admin),
):
    csv_text = (await file.read()).decode("utf-8-sig")
    unifi_client = UniFiAccessClient()
    summary = import_bootstrap_users_csv(
        session,
        csv_text,
        unifi_access_policies=await unifi_client.list_access_policies(),
        unifi_user_groups=await unifi_client.list_user_groups(),
        actor_account_id=account.id,
        actor_email=account.email,
        ip_address=request.client.host if request.client else None,
    )
    session.commit()
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
            "summary": summary,
        },
    )
