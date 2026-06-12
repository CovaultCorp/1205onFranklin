from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import PortalAccount
from app.security import COOKIE_NAME, create_session_token, has_admin, hash_password, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, session: Session = Depends(get_session)):
    if not has_admin(session):
        return RedirectResponse("/setup-admin", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login")
def login(email: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    account = session.scalar(select(PortalAccount).where(PortalAccount.email == email.lower(), PortalAccount.active))
    if not account or not verify_password(password, account.password_hash):
        return RedirectResponse("/login", status_code=303)
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(COOKIE_NAME, create_session_token(account.id), httponly=True, samesite="lax")
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/setup-admin", response_class=HTMLResponse)
def setup_admin_form(request: Request, session: Session = Depends(get_session)):
    if has_admin(session):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "auth/setup_admin.html", {"error": None})


@router.post("/setup-admin")
def setup_admin(
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    if has_admin(session):
        return RedirectResponse("/login", status_code=303)
    account = PortalAccount(email=email.lower(), password_hash=hash_password(password), role="admin")
    session.add(account)
    session.commit()
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(COOKIE_NAME, create_session_token(account.id), httponly=True, samesite="lax")
    return response
