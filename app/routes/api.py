from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_session
from app.models import (
    AccessProfile,
    AccessRequest,
    Company,
    Conflict,
    PortalAccount,
    ReportRun,
    Suite,
    SyncJob,
    UnifiUser,
    User,
    utcnow,
)
from app.reports import generate_report, send_report
from app.security import COOKIE_NAME, create_session_token, get_current_account, has_admin, verify_password

router = APIRouter(prefix="/api")


class LoginIn(BaseModel):
    email: str
    password: str


class AccessRequestIn(BaseModel):
    request_type: str
    requested_for_first_name: str
    requested_for_last_name: str
    requested_for_email: str
    requested_for_employee_number: str | None = None
    requested_for_company_text: str | None = None
    requested_for_suite_text: str | None = None
    requested_for_department: str | None = None
    requested_start_date: date | None = None
    requested_end_date: date | None = None
    reason: str | None = None
    requester_name: str
    requester_email: str


class ApproveRequestIn(BaseModel):
    requested_for_company_id: int | None = None
    requested_for_suite_id: int | None = None
    requested_access_profile_id: int | None = None
    admin_notes: str | None = None


class DenyRequestIn(BaseModel):
    denial_reason: str


class NeedsInfoIn(BaseModel):
    admin_notes: str | None = None


class ReportGenerateIn(BaseModel):
    report_type: str
    company_id: int | None = None
    suite_id: int | None = None
    recipient_email: str | None = None
    send_email: bool = False


def _require_api_admin(account: PortalAccount | None = Depends(get_current_account)) -> PortalAccount:
    if account is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if account.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return account


def _account_json(account: PortalAccount | None) -> dict[str, Any] | None:
    if account is None:
        return None
    return {"id": account.id, "email": account.email, "role": account.role}


def _company_json(company: Company | None) -> dict[str, Any] | None:
    if company is None:
        return None
    return {"id": company.id, "name": company.name, "status": company.status}


def _suite_json(suite: Suite | None) -> dict[str, Any] | None:
    if suite is None:
        return None
    return {"id": suite.id, "suite_number": suite.suite_number, "floor": suite.floor, "status": suite.status}


def _profile_json(profile: AccessProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {"id": profile.id, "name": profile.name, "active": profile.active}


def _request_json(access_request: AccessRequest) -> dict[str, Any]:
    return {
        "id": access_request.id,
        "request_type": access_request.request_type,
        "status": access_request.status,
        "requested_for_first_name": access_request.requested_for_first_name,
        "requested_for_last_name": access_request.requested_for_last_name,
        "requested_for_email": access_request.requested_for_email,
        "requested_for_employee_number": access_request.requested_for_employee_number,
        "requested_for_company_text": access_request.requested_for_company_text,
        "requested_for_suite_text": access_request.requested_for_suite_text,
        "requested_for_department": access_request.requested_for_department,
        "requested_start_date": access_request.requested_start_date,
        "requested_end_date": access_request.requested_end_date,
        "reason": access_request.reason,
        "requester_name": access_request.requester_name,
        "requester_email": access_request.requester_email,
        "admin_notes": access_request.admin_notes,
        "denial_reason": access_request.denial_reason,
        "company": _company_json(access_request.company),
        "suite": _suite_json(access_request.suite),
        "access_profile": _profile_json(access_request.access_profile),
        "created_at": access_request.created_at,
        "updated_at": access_request.updated_at,
        "approved_at": access_request.approved_at,
        "denied_at": access_request.denied_at,
    }


def _user_json(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "name": f"{user.first_name} {user.last_name}",
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "employee_number": user.employee_number,
        "company": _company_json(user.company),
        "suite": _suite_json(user.primary_suite),
        "access_profile": _profile_json(user.access_profile),
        "department": user.department,
        "status": user.status,
        "last_verified_at": user.last_verified_at,
        "desired_unifi_access_policy_names": user.desired_unifi_access_policy_names or [],
        "desired_unifi_user_group_names": user.desired_unifi_user_group_names or [],
    }


def _report_json(run: ReportRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "report_type": run.report_type,
        "status": run.status,
        "recipient_email": run.recipient_email,
        "subject": run.subject,
        "filters_json": run.filters_json or {},
        "sent_at": run.sent_at,
        "last_error": run.last_error,
        "created_at": run.created_at,
    }


@router.get("/session")
def session_status(
    session: Session = Depends(get_session),
    account: PortalAccount | None = Depends(get_current_account),
):
    settings = get_settings()
    return {
        "account": _account_json(account),
        "has_admin": has_admin(session),
        "enable_writes": settings.enable_writes,
        "enable_email": settings.enable_email,
    }


@router.post("/auth/login")
def api_login(payload: LoginIn, response: Response, session: Session = Depends(get_session)):
    account = session.scalar(
        select(PortalAccount).where(PortalAccount.email == payload.email.lower(), PortalAccount.active)
    )
    if not account or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(account.id),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"account": _account_json(account)}


@router.post("/auth/logout")
def api_logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/access-requests", status_code=status.HTTP_201_CREATED)
def api_submit_access_request(
    payload: AccessRequestIn,
    request: Request,
    session: Session = Depends(get_session),
):
    access_request = AccessRequest(
        request_type=payload.request_type,
        requested_for_first_name=payload.requested_for_first_name,
        requested_for_last_name=payload.requested_for_last_name,
        requested_for_email=payload.requested_for_email.lower(),
        requested_for_employee_number=payload.requested_for_employee_number or None,
        requested_for_company_text=payload.requested_for_company_text or None,
        requested_for_suite_text=payload.requested_for_suite_text or None,
        requested_for_department=payload.requested_for_department or None,
        requested_start_date=payload.requested_start_date,
        requested_end_date=payload.requested_end_date,
        reason=payload.reason or None,
        status="submitted",
        requester_name=payload.requester_name,
        requester_email=payload.requester_email.lower(),
    )
    session.add(access_request)
    session.flush()
    audit(
        session,
        action="access_request.submitted",
        target_type="AccessRequest",
        target_id=access_request.id,
        request=request,
        after={"status": access_request.status},
    )
    session.commit()
    return {"request": _request_json(access_request)}


@router.get("/admin/dashboard")
def api_admin_dashboard(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    stale_cutoff = utcnow() - timedelta(days=90)
    stats = {
        "active_users": session.scalar(select(func.count(User.id)).where(User.status == "active")) or 0,
        "missing_company": session.scalar(select(func.count(User.id)).where(User.company_id.is_(None))) or 0,
        "missing_suite": session.scalar(select(func.count(User.id)).where(User.primary_suite_id.is_(None))) or 0,
        "stale_verification": session.scalar(
            select(func.count(User.id)).where(
                User.status == "active",
                (User.last_verified_at.is_(None)) | (User.last_verified_at < stale_cutoff),
            )
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
    return {
        "account": _account_json(account),
        "stats": stats,
        "recent_reports": [_report_json(run) for run in session.scalars(select(ReportRun).order_by(ReportRun.created_at.desc()).limit(5))],
        "recent_sync_jobs": [
            {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "created_at": job.created_at,
                "last_error": job.last_error,
            }
            for job in session.scalars(select(SyncJob).order_by(SyncJob.created_at.desc()).limit(5))
        ],
    }


@router.get("/admin/requests")
def api_admin_requests(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    return {
        "requests": [
            _request_json(access_request)
            for access_request in session.scalars(select(AccessRequest).order_by(AccessRequest.created_at.desc())).all()
        ]
    }


@router.get("/admin/requests/{request_id}")
def api_admin_request_detail(
    request_id: int,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    access_request = session.get(AccessRequest, request_id)
    if access_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    return {
        "request": _request_json(access_request),
        "companies": [_company_json(company) for company in session.scalars(select(Company).order_by(Company.name)).all()],
        "suites": [_suite_json(suite) for suite in session.scalars(select(Suite).order_by(Suite.suite_number)).all()],
        "profiles": [_profile_json(profile) for profile in session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all()],
    }


@router.post("/admin/requests/{request_id}/approve")
def api_approve_request(
    request_id: int,
    payload: ApproveRequestIn,
    request: Request,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    access_request = session.get(AccessRequest, request_id)
    if access_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    before = {"status": access_request.status}
    access_request.requested_for_company_id = payload.requested_for_company_id
    access_request.requested_for_suite_id = payload.requested_for_suite_id
    access_request.requested_access_profile_id = payload.requested_access_profile_id
    access_request.admin_notes = payload.admin_notes or None
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
    return {"request": _request_json(access_request), "sync_job_id": job.id}


@router.post("/admin/requests/{request_id}/deny")
def api_deny_request(
    request_id: int,
    payload: DenyRequestIn,
    request: Request,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    access_request = session.get(AccessRequest, request_id)
    if access_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    before = {"status": access_request.status}
    access_request.status = "denied"
    access_request.denial_reason = payload.denial_reason
    access_request.denied_by_account_id = account.id
    access_request.denied_at = utcnow()
    audit(
        session,
        action="access_request.denied",
        target_type="AccessRequest",
        target_id=request_id,
        actor=account,
        request=request,
        before=before,
        after={"status": "denied"},
    )
    session.commit()
    return {"request": _request_json(access_request)}


@router.post("/admin/requests/{request_id}/needs-info")
def api_needs_info_request(
    request_id: int,
    payload: NeedsInfoIn,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    access_request = session.get(AccessRequest, request_id)
    if access_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
    access_request.status = "needs_info"
    access_request.admin_notes = payload.admin_notes or None
    session.commit()
    return {"request": _request_json(access_request)}


@router.post("/admin/requests/{request_id}/sync")
def api_dry_run_sync(
    request_id: int,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    job = session.scalar(select(SyncJob).where(SyncJob.access_request_id == request_id).order_by(SyncJob.created_at.desc()))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync job not found")
    job.status = "succeeded"
    job.attempt_count += 1
    job.result_json = {"dry_run": True, "message": "No UniFi writes attempted in Phase 1."}
    job.completed_at = utcnow()
    session.commit()
    return {"sync_job": {"id": job.id, "status": job.status, "result_json": job.result_json}}


@router.get("/admin/users")
def api_admin_users(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    return {"users": [_user_json(user) for user in session.scalars(select(User).order_by(User.last_name, User.first_name)).all()]}


@router.get("/admin/lookups")
def api_admin_lookups(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    return {
        "companies": [_company_json(company) for company in session.scalars(select(Company).order_by(Company.name)).all()],
        "suites": [_suite_json(suite) for suite in session.scalars(select(Suite).order_by(Suite.suite_number)).all()],
        "profiles": [_profile_json(profile) for profile in session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all()],
    }


@router.get("/admin/reports/runs")
def api_report_runs(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    return {"runs": [_report_json(run) for run in session.scalars(select(ReportRun).order_by(ReportRun.created_at.desc())).all()]}


@router.get("/admin/reports/runs/{run_id}")
def api_report_run_detail(
    run_id: int,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report run not found")
    html = Path(run.output_html_path).read_text(encoding="utf-8") if run.output_html_path and Path(run.output_html_path).exists() else ""
    return {"run": _report_json(run), "report_html": html}


@router.get("/admin/reports/runs/{run_id}/download-csv")
def api_download_report_csv(
    run_id: int,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    run = session.get(ReportRun, run_id)
    if run is None or not run.output_csv_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report CSV not found")
    return FileResponse(run.output_csv_path, filename=Path(run.output_csv_path).name, media_type="text/csv")


@router.post("/admin/reports/generate")
def api_generate_report(
    payload: ReportGenerateIn,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    valid_types = {"company_users", "suite_users", "full_building_access"}
    if payload.report_type not in valid_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported report type")
    if payload.send_email and not payload.recipient_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recipient email is required")
    run = generate_report(
        session,
        report_type=payload.report_type,
        requested_by_account_id=account.id,
        company_id=payload.company_id,
        suite_id=payload.suite_id,
        recipient_email=payload.recipient_email,
    )
    if payload.send_email:
        send_report(session, run, payload.recipient_email)
    session.commit()
    return {"run": _report_json(run)}
