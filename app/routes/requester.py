from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_session
from app.models import AccessRequest, BuildingProperty

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _entrypoint_property(session: Session) -> BuildingProperty:
    property_ = session.scalar(select(BuildingProperty).where(BuildingProperty.slug == "1205-franklin"))
    if property_ is None:
        property_ = BuildingProperty(
            slug="1205-franklin",
            name="ENTRY POINT",
            display_name="1205 on Franklin",
            address_line1="1205 Franklin",
            city="Tampa",
            state="FL",
            status="active",
            notes="Seed property for Entry Point at 1205 on Franklin.",
        )
        session.add(property_)
        session.flush()
    return property_


@router.get("/request", response_class=HTMLResponse)
def request_form(request: Request):
    return templates.TemplateResponse(request, "requester/request.html", {})


@router.post("/request")
def submit_request(
    request: Request,
    request_type: str = Form(...),
    requested_for_first_name: str = Form(...),
    requested_for_last_name: str = Form(...),
    requested_for_email: str = Form(...),
    requested_for_employee_number: str = Form(""),
    requested_for_company_text: str = Form(""),
    requested_for_suite_text: str = Form(""),
    requested_for_department: str = Form(""),
    requested_start_date: str = Form(""),
    requested_end_date: str = Form(""),
    reason: str = Form(""),
    requester_name: str = Form(...),
    requester_email: str = Form(...),
    session: Session = Depends(get_session),
):
    property_ = _entrypoint_property(session)
    access_request = AccessRequest(
        property_id=property_.id,
        request_type=request_type,
        requested_for_first_name=requested_for_first_name,
        requested_for_last_name=requested_for_last_name,
        requested_for_email=requested_for_email.lower(),
        requested_for_employee_number=requested_for_employee_number or None,
        requested_for_company_text=requested_for_company_text or None,
        requested_for_suite_text=requested_for_suite_text or None,
        requested_for_department=requested_for_department or None,
        requested_start_date=_date_or_none(requested_start_date),
        requested_end_date=_date_or_none(requested_end_date),
        reason=reason or None,
        status="submitted",
        requester_name=requester_name,
        requester_email=requester_email.lower(),
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
    return RedirectResponse(f"/request/thanks/{access_request.id}", status_code=303)


@router.get("/request/thanks/{request_id}", response_class=HTMLResponse)
def thanks(request: Request, request_id: int):
    return templates.TemplateResponse(request, "requester/thanks.html", {"request_id": request_id})
