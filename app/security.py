from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import PortalAccount

COOKIE_NAME = "bar_session"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return "pbkdf2_sha256$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_b64, digest_b64 = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
    expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return hmac.compare_digest(actual, expected)


def create_session_token(account_id: int) -> str:
    secret = get_settings().app_secret_key.encode("utf-8")
    expires = int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp())
    payload = f"{account_id}:{expires}"
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode("utf-8")).decode("ascii")


def read_session_token(token: str | None) -> int | None:
    if not token:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        account_id, expires, signature = decoded.rsplit(":", 2)
    except ValueError:
        return None
    payload = f"{account_id}:{expires}"
    expected = hmac.new(
        get_settings().app_secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    if int(expires) < int(datetime.now(timezone.utc).timestamp()):
        return None
    return int(account_id)


def get_current_account(
    request: Request, session: Session = Depends(get_session)
) -> PortalAccount | None:
    account_id = read_session_token(request.cookies.get(COOKIE_NAME))
    if not account_id:
        return None
    account = session.get(PortalAccount, account_id)
    if not account or not account.active:
        return None
    return account


def require_account(account: PortalAccount | None = Depends(get_current_account)) -> PortalAccount:
    if account is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return account


def require_admin(account: PortalAccount = Depends(require_account)) -> PortalAccount:
    if account.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return account


def has_admin(session: Session) -> bool:
    return session.scalar(select(PortalAccount.id).where(PortalAccount.role == "admin").limit(1)) is not None

