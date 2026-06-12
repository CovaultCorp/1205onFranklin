from __future__ import annotations

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import PortalAccount
from app.security import hash_password


def seed_initial_admin() -> None:
    settings = get_settings()
    if not settings.admin_initial_password:
        return
    with SessionLocal() as session:
        existing = session.scalar(select(PortalAccount).where(PortalAccount.role == "admin").limit(1))
        if existing:
            return
        session.add(
            PortalAccount(
                email=settings.admin_email.lower(),
                password_hash=hash_password(settings.admin_initial_password),
                role="admin",
            )
        )
        session.commit()

