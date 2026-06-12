from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Company, PortalAccount, ReportRun, Suite
from app.reports import generate_report, send_report
from app.security import require_admin

router = APIRouter(prefix="/admin/reports")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def reports_home(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "reports/index.html", {"account": account})


@router.get("/company-users", response_class=HTMLResponse)
def company_users_form(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "reports/company_users.html", {"account": account, "companies": session.scalars(select(Company).order_by(Company.name)).all()})


@router.post("/company-users/preview")
def company_users_preview(company_id: int = Form(...), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = generate_report(session, report_type="company_users", requested_by_account_id=account.id, company_id=company_id)
    session.commit()
    return RedirectResponse(f"/admin/reports/runs/{run.id}", status_code=303)


@router.post("/company-users/send")
def company_users_send(company_id: int = Form(...), recipient_email: str = Form(...), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = generate_report(session, report_type="company_users", requested_by_account_id=account.id, company_id=company_id, recipient_email=recipient_email)
    send_report(session, run, recipient_email)
    session.commit()
    return RedirectResponse(f"/admin/reports/runs/{run.id}", status_code=303)


@router.get("/suite-users", response_class=HTMLResponse)
def suite_users_form(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "reports/suite_users.html", {"account": account, "suites": session.scalars(select(Suite).order_by(Suite.suite_number)).all()})


@router.post("/suite-users/preview")
def suite_users_preview(suite_id: int = Form(...), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = generate_report(session, report_type="suite_users", requested_by_account_id=account.id, suite_id=suite_id)
    session.commit()
    return RedirectResponse(f"/admin/reports/runs/{run.id}", status_code=303)


@router.post("/suite-users/send")
def suite_users_send(suite_id: int = Form(...), recipient_email: str = Form(...), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = generate_report(session, report_type="suite_users", requested_by_account_id=account.id, suite_id=suite_id, recipient_email=recipient_email)
    send_report(session, run, recipient_email)
    session.commit()
    return RedirectResponse(f"/admin/reports/runs/{run.id}", status_code=303)


@router.get("/full-building", response_class=HTMLResponse)
def full_building_form(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "reports/full_building.html", {"account": account})


@router.post("/full-building/preview")
def full_building_preview(session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = generate_report(session, report_type="full_building_access", requested_by_account_id=account.id)
    session.commit()
    return RedirectResponse(f"/admin/reports/runs/{run.id}", status_code=303)


@router.post("/full-building/send")
def full_building_send(recipient_email: str = Form(...), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = generate_report(session, report_type="full_building_access", requested_by_account_id=account.id, recipient_email=recipient_email)
    send_report(session, run, recipient_email)
    session.commit()
    return RedirectResponse(f"/admin/reports/runs/{run.id}", status_code=303)


@router.get("/runs", response_class=HTMLResponse)
def report_runs(request: Request, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    return templates.TemplateResponse(request, "reports/runs.html", {"account": account, "runs": session.scalars(select(ReportRun).order_by(ReportRun.created_at.desc())).all()})


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def report_run_detail(request: Request, run_id: int, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = session.get(ReportRun, run_id)
    html = Path(run.output_html_path).read_text(encoding="utf-8") if run and run.output_html_path and Path(run.output_html_path).exists() else ""
    return templates.TemplateResponse(request, "reports/run_detail.html", {"account": account, "run": run, "report_html": html})


@router.post("/runs/{run_id}/resend")
def resend_report(run_id: int, recipient_email: str = Form(...), session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = session.get(ReportRun, run_id)
    if run:
        send_report(session, run, recipient_email)
        session.commit()
    return RedirectResponse(f"/admin/reports/runs/{run_id}", status_code=303)


@router.get("/runs/{run_id}/download-csv")
def download_csv(run_id: int, session: Session = Depends(get_session), account: PortalAccount = Depends(require_admin)):
    run = session.get(ReportRun, run_id)
    if not run or not run.output_csv_path:
        return RedirectResponse("/admin/reports/runs", status_code=303)
    return FileResponse(run.output_csv_path, filename=Path(run.output_csv_path).name, media_type="text/csv")
