from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import VerificationRequest


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_verification_request(
    session: Session,
    *,
    recipient_email: str,
    report_run_id: int | None = None,
    company_id: int | None = None,
    suite_id: int | None = None,
) -> tuple[VerificationRequest, str]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=get_settings().report_verification_expiration_days)
    record = VerificationRequest(
        report_run_id=report_run_id,
        company_id=company_id,
        suite_id=suite_id,
        recipient_email=recipient_email,
        verification_token_hash=hash_token(token),
        expires_at=expires_at,
    )
    session.add(record)
    session.flush()
    return record, token


def get_verification_by_token(session: Session, token: str) -> VerificationRequest | None:
    return session.scalar(
        select(VerificationRequest).where(VerificationRequest.verification_token_hash == hash_token(token))
    )


def is_expired(record: VerificationRequest) -> bool:
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < datetime.now(timezone.utc)

