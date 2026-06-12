from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, PortalAccount


def audit(
    session: Session,
    *,
    action: str,
    target_type: str,
    target_id: int | str | None,
    actor: PortalAccount | None = None,
    request: Request | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    ip_address = request.client.host if request and request.client else None
    session.add(
        AuditLog(
            actor_account_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            before_json=before,
            after_json=after,
            ip_address=ip_address,
        )
    )

