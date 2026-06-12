from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import utcnow
from app.verification import get_verification_by_token, is_expired

router = APIRouter(prefix="/verify")
templates = Jinja2Templates(directory="app/templates")


@router.get("/{token}", response_class=HTMLResponse)
def verify_form(token: str, request: Request, session: Session = Depends(get_session)):
    record = get_verification_by_token(session, token)
    expired = True if record is None else is_expired(record)
    return templates.TemplateResponse(request, "verify/form.html", {"token": token, "record": record, "expired": expired})


@router.post("/{token}")
def verify_submit(
    token: str,
    status: str = Form(...),
    verified_by_name: str = Form(...),
    verified_by_email: str = Form(...),
    comments: str = Form(""),
    session: Session = Depends(get_session),
):
    record = get_verification_by_token(session, token)
    if record and not is_expired(record):
        record.status = status
        record.verified_by_name = verified_by_name
        record.verified_by_email = verified_by_email
        record.comments = comments or None
        record.verified_at = utcnow()
        session.commit()
    return RedirectResponse(f"/verify/{token}", status_code=303)
