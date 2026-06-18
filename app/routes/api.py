from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import get_session, safe_database_identity
from app.models import (
    AccessProfile,
    AccessRequest,
    AuditLog,
    BuildingProperty,
    Company,
    CompanySuite,
    Conflict,
    ImportBatch,
    PortalAccount,
    ReportRun,
    Suite,
    SyncRun,
    SyncRunLog,
    SyncSnapshot,
    SyncJob,
    StagedAccessChange,
    UnifiAccessPolicy,
    UnifiDoor,
    UnifiDoorGroup,
    UnifiUser,
    UnifiUserGroup,
    User,
    utcnow,
)
from app.reports import generate_report, send_report
from app.security import COOKIE_NAME, create_session_token, get_current_account, has_admin, verify_password
from app.unifi_normalization import normalize_unifi_user, sanitize_for_snapshot

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


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


class AgentSnapshotIn(BaseModel):
    agent_name: str | None = None
    source: str | None = None
    observed_at: datetime | None = None
    users: list[dict[str, Any]] = []
    access_policies: list[dict[str, Any]] = []
    user_groups: list[dict[str, Any]] = []
    doors: list[dict[str, Any]] = []
    door_groups: list[dict[str, Any]] = []


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


def _property_json(property_: BuildingProperty | None) -> dict[str, Any] | None:
    if property_ is None:
        return None
    return {
        "id": property_.id,
        "slug": property_.slug,
        "name": property_.name,
        "display_name": property_.display_name,
        "address_line1": property_.address_line1,
        "city": property_.city,
        "state": property_.state,
        "postal_code": property_.postal_code,
        "status": property_.status,
    }


def _company_json(company: Company | None) -> dict[str, Any] | None:
    if company is None:
        return None
    return {
        "id": company.id,
        "name": company.name,
        "legal_name": company.legal_name,
        "status": company.status,
        "primary_contact_name": company.primary_contact_name,
        "primary_contact_email": company.primary_contact_email,
        "phone": company.phone,
        "notes": company.notes,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


def _suite_json(suite: Suite | None) -> dict[str, Any] | None:
    if suite is None:
        return None
    return {
        "id": suite.id,
        "suite_number": suite.suite_number,
        "floor": suite.floor,
        "building_area": suite.building_area,
        "description": suite.description,
        "status": suite.status,
        "created_at": suite.created_at,
        "updated_at": suite.updated_at,
    }


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


def _require_agent_token(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = settings.entrypoint_agent_token.strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent ingestion is not configured")
    token = ""
    if authorization:
        scheme, _, value = authorization.partition(" ")
        token = value.strip() if scheme.lower() == "bearer" else authorization.strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")


def _payload_id(payload: dict[str, Any], keys: tuple[str, ...] = ("id", "uuid")) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _payload_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip() or None
    return None


def _upsert_named_unifi_record(
    session: Session,
    *,
    model: type[UnifiAccessPolicy] | type[UnifiUserGroup] | type[UnifiDoorGroup] | type[UnifiDoor],
    id_field: str,
    property_id: int,
    payload: dict[str, Any],
    now: datetime,
) -> Any | None:
    external_id = _payload_id(
        payload,
        ("id", "uuid", "policy_id", "policyId", "group_id", "groupId", "door_id", "doorId", "door_group_id", "doorGroupId"),
    )
    if not external_id:
        return None
    record = session.scalar(select(model).where(getattr(model, "property_id") == property_id, getattr(model, id_field) == external_id))
    if record is None:
        record = model(property_id=property_id, **{id_field: external_id})
        session.add(record)
    record.name = _payload_text(payload, "name", "display_name", "displayName", "policy_name", "policyName", "group_name", "groupName")
    if hasattr(record, "full_name"):
        record.full_name = _payload_text(payload, "full_name", "fullName")
    if hasattr(record, "description"):
        record.description = _payload_text(payload, "description")
    if hasattr(record, "status"):
        record.status = _payload_text(payload, "status", "state")
    record.raw_snapshot_json = sanitize_for_snapshot(payload)
    record.last_seen_at = now
    return record


def _upsert_agent_unifi_user(session: Session, *, property_id: int, payload: dict[str, Any], now: datetime) -> UnifiUser | None:
    normalized = normalize_unifi_user(payload)
    unifi_user_id = normalized["id"]
    if not unifi_user_id:
        return None

    snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == unifi_user_id))
    local_user: User | None = None
    if snapshot and snapshot.local_user_id:
        local_user = session.get(User, snapshot.local_user_id)
    if local_user is None and normalized["employee_number"]:
        local_user = session.scalar(select(User).where(User.employee_number == normalized["employee_number"]))
    if local_user is None and normalized["email"]:
        local_user = session.scalar(select(User).where(User.email == normalized["email"]))

    if snapshot is None:
        snapshot = UnifiUser(unifi_user_id=unifi_user_id)
        session.add(snapshot)
    snapshot.property_id = property_id
    if local_user is not None:
        snapshot.local_user_id = local_user.id
        if local_user.property_id is None:
            local_user.property_id = property_id
    snapshot.email = normalized["email"] or None
    snapshot.email_status = normalized["email_status"] or None
    snapshot.employee_number = normalized["employee_number"] or None
    snapshot.suite_number = normalized["suite_number"] or None
    snapshot.first_name = normalized["first_name"] or None
    snapshot.last_name = normalized["last_name"] or None
    snapshot.full_name = normalized["full_name"] or None
    snapshot.phone = normalized["phone"] or None
    snapshot.username = normalized["username"] or None
    snapshot.alias = normalized["alias"] or None
    snapshot.status = normalized["status"] or None
    snapshot.onboard_time = normalized["onboard_time"] or None
    snapshot.access_policy_ids = normalized["access_policy_ids"]
    snapshot.access_policy_names = normalized["access_policy_names"]
    snapshot.group_ids = normalized["group_ids"]
    snapshot.group_names = normalized["group_names"]
    snapshot.nfc_card_count = normalized["nfc_card_count"]
    snapshot.touch_pass_status = normalized["touch_pass_status"] or None
    snapshot.touch_pass_last_activity = normalized["touch_pass_last_activity"] or None
    snapshot.license_plate_count = normalized["license_plate_count"]
    snapshot.raw_user_json_file = normalized["raw_user_json_file"] or None
    snapshot.raw_snapshot_json = sanitize_for_snapshot(payload)
    snapshot.last_seen_at = now
    snapshot.last_synced_at = now
    return snapshot


def _profile_json(profile: AccessProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "active": profile.active,
        "unifi_access_policy_ids": profile.unifi_access_policy_ids or [],
        "unifi_user_group_ids": profile.unifi_user_group_ids or [],
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


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


def _user_json(user: User, snapshot: UnifiUser | None = None) -> dict[str, Any]:
    current_policy_names = snapshot.access_policy_names if snapshot else []
    current_group_names = snapshot.group_names if snapshot else []
    data_source = "Entry Point + UniFi Access" if snapshot else "Entry Point"
    return {
        "id": user.id,
        "name": f"{user.first_name} {user.last_name}",
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "employee_number": user.employee_number,
        "company": _company_json(user.company),
        "suite": _suite_json(user.primary_suite),
        "property": _property_json(user.property),
        "access_profile": _profile_json(user.access_profile),
        "department": user.department,
        "status": user.status,
        "last_verified_at": user.last_verified_at,
        "data_source": data_source,
        "unifi_user_id": snapshot.unifi_user_id if snapshot else None,
        "unifi_status": snapshot.status if snapshot else None,
        "credential_summary": _credential_summary(snapshot),
        "last_synced_at": snapshot.last_synced_at if snapshot else None,
        "onboard_time": snapshot.onboard_time if snapshot else None,
        "nfc_card_count": snapshot.nfc_card_count if snapshot else None,
        "touch_pass_status": snapshot.touch_pass_status if snapshot else None,
        "unifi_suite_number": snapshot.suite_number if snapshot else None,
        "desired_unifi_access_policy_names": user.desired_unifi_access_policy_names or [],
        "desired_unifi_user_group_names": user.desired_unifi_user_group_names or [],
        "current_unifi_access_policy_names": current_policy_names or [],
        "current_unifi_user_group_names": current_group_names or [],
    }


def _credential_summary(snapshot: UnifiUser | None) -> str:
    if snapshot is None:
        return "Not synced"
    parts: list[str] = []
    if snapshot.nfc_card_count:
        parts.append(f"NFC {snapshot.nfc_card_count}")
    if snapshot.touch_pass_status:
        parts.append(f"Touch Pass {snapshot.touch_pass_status}")
    if snapshot.license_plate_count:
        parts.append(f"Plates {snapshot.license_plate_count}")
    return ", ".join(parts) if parts else "No credentials observed"


def _snapshot_user_json(snapshot: UnifiUser) -> dict[str, Any]:
    full_name = snapshot.full_name or " ".join(part for part in (snapshot.first_name, snapshot.last_name) if part).strip()
    return {
        "id": f"unifi-{snapshot.id}",
        "name": full_name or snapshot.email or snapshot.unifi_user_id,
        "first_name": snapshot.first_name,
        "last_name": snapshot.last_name,
        "email": snapshot.email or "",
        "employee_number": snapshot.employee_number,
        "company": None,
        "suite": None,
        "property": _property_json(snapshot.property),
        "access_profile": None,
        "department": None,
        "status": snapshot.status or "unknown",
        "last_verified_at": None,
        "data_source": "UniFi Access",
        "unifi_user_id": snapshot.unifi_user_id,
        "unifi_status": snapshot.status,
        "credential_summary": _credential_summary(snapshot),
        "last_synced_at": snapshot.last_synced_at,
        "onboard_time": snapshot.onboard_time,
        "nfc_card_count": snapshot.nfc_card_count,
        "touch_pass_status": snapshot.touch_pass_status,
        "unifi_suite_number": snapshot.suite_number,
        "desired_unifi_access_policy_names": [],
        "desired_unifi_user_group_names": [],
        "current_unifi_access_policy_names": snapshot.access_policy_names or [],
        "current_unifi_user_group_names": snapshot.group_names or [],
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


def _conflict_severity(conflict: Conflict) -> str:
    high = {"duplicate_email", "duplicate_employee_number", "local_active_missing_unifi"}
    medium = {"status_mismatch", "access_policy_mismatch", "name_email_mismatch"}
    if conflict.conflict_type in high:
        return "high"
    if conflict.conflict_type in medium:
        return "medium"
    return "low"


def _conflict_json(conflict: Conflict) -> dict[str, Any]:
    return {
        "id": conflict.id,
        "local_user_id": conflict.local_user_id,
        "unifi_user_id": conflict.unifi_user_id,
        "conflict_type": conflict.conflict_type,
        "description": conflict.description,
        "severity": _conflict_severity(conflict),
        "status": conflict.status,
        "created_at": conflict.created_at,
        "updated_at": conflict.updated_at,
        "resolved_at": conflict.resolved_at,
    }


def _sync_job_json(job: SyncJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "access_request_id": job.access_request_id,
        "job_type": job.job_type,
        "status": job.status,
        "proposed_actions": job.proposed_actions or {},
        "result_json": job.result_json or {},
        "attempt_count": job.attempt_count,
        "last_error": job.last_error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,
    }


def _audit_log_json(log: AuditLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "actor_email": log.actor_email,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "created_at": log.created_at,
    }


def _occupancy_json(occupancy: CompanySuite, active_user_count: int = 0) -> dict[str, Any]:
    return {
        "id": occupancy.id,
        "company": _company_json(occupancy.company),
        "suite": _suite_json(occupancy.suite),
        "occupancy_status": occupancy.occupancy_status,
        "start_date": occupancy.start_date,
        "end_date": occupancy.end_date,
        "notes": occupancy.notes,
        "active_user_count": active_user_count,
        "created_at": occupancy.created_at,
        "updated_at": occupancy.updated_at,
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


@router.post("/agent/snapshots", status_code=status.HTTP_202_ACCEPTED)
def api_agent_snapshots(
    payload: AgentSnapshotIn,
    session: Session = Depends(get_session),
    _: None = Depends(_require_agent_token),
):
    property_ = _entrypoint_property(session)
    settings = get_settings()
    now = utcnow()
    observed_at = payload.observed_at or now
    run = SyncRun(
        property_id=property_.id,
        source=payload.source or settings.unifi_snapshot_source,
        agent_name=payload.agent_name or settings.unifi_agent_name,
        status="received",
        started_at=now,
        observed_at=observed_at,
        summary_json={},
    )
    session.add(run)
    session.flush()

    counts = {
        "users_seen": len(payload.users),
        "users_upserted": 0,
        "access_policies_upserted": 0,
        "user_groups_upserted": 0,
        "doors_upserted": 0,
        "door_groups_upserted": 0,
        "snapshots_stored": 0,
    }

    for user_payload in payload.users:
        snapshot = _upsert_agent_unifi_user(session, property_id=property_.id, payload=user_payload, now=now)
        normalized = normalize_unifi_user(user_payload)
        session.add(
            SyncSnapshot(
                property_id=property_.id,
                sync_run_id=run.id,
                snapshot_type="unifi_user",
                external_id=normalized["id"] or None,
                normalized_json=normalized,
                raw_snapshot_json=sanitize_for_snapshot(user_payload),
                observed_at=observed_at,
            )
        )
        counts["snapshots_stored"] += 1
        if snapshot is not None:
            counts["users_upserted"] += 1

    for policy_payload in payload.access_policies:
        record = _upsert_named_unifi_record(
            session,
            model=UnifiAccessPolicy,
            id_field="unifi_policy_id",
            property_id=property_.id,
            payload=policy_payload,
            now=now,
        )
        session.add(
            SyncSnapshot(
                property_id=property_.id,
                sync_run_id=run.id,
                snapshot_type="unifi_access_policy",
                external_id=_payload_id(policy_payload, ("id", "uuid", "policy_id", "policyId")),
                normalized_json={"id": _payload_id(policy_payload, ("id", "uuid", "policy_id", "policyId")), "name": _payload_text(policy_payload, "name", "policyName")},
                raw_snapshot_json=sanitize_for_snapshot(policy_payload),
                observed_at=observed_at,
            )
        )
        counts["snapshots_stored"] += 1
        if record is not None:
            counts["access_policies_upserted"] += 1

    for group_payload in payload.user_groups:
        record = _upsert_named_unifi_record(
            session,
            model=UnifiUserGroup,
            id_field="unifi_group_id",
            property_id=property_.id,
            payload=group_payload,
            now=now,
        )
        session.add(
            SyncSnapshot(
                property_id=property_.id,
                sync_run_id=run.id,
                snapshot_type="unifi_user_group",
                external_id=_payload_id(group_payload, ("id", "uuid", "group_id", "groupId")),
                normalized_json={"id": _payload_id(group_payload, ("id", "uuid", "group_id", "groupId")), "name": _payload_text(group_payload, "name", "groupName")},
                raw_snapshot_json=sanitize_for_snapshot(group_payload),
                observed_at=observed_at,
            )
        )
        counts["snapshots_stored"] += 1
        if record is not None:
            counts["user_groups_upserted"] += 1

    door_groups_by_unifi_id: dict[str, UnifiDoorGroup] = {}
    for door_group_payload in payload.door_groups:
        record = _upsert_named_unifi_record(
            session,
            model=UnifiDoorGroup,
            id_field="unifi_door_group_id",
            property_id=property_.id,
            payload=door_group_payload,
            now=now,
        )
        external_id = _payload_id(door_group_payload, ("id", "uuid", "door_group_id", "doorGroupId"))
        if record is not None and external_id:
            door_groups_by_unifi_id[external_id] = record
        session.add(
            SyncSnapshot(
                property_id=property_.id,
                sync_run_id=run.id,
                snapshot_type="unifi_door_group",
                external_id=external_id,
                normalized_json={"id": external_id, "name": _payload_text(door_group_payload, "name")},
                raw_snapshot_json=sanitize_for_snapshot(door_group_payload),
                observed_at=observed_at,
            )
        )
        counts["snapshots_stored"] += 1
        if record is not None:
            counts["door_groups_upserted"] += 1

    for door_payload in payload.doors:
        record = _upsert_named_unifi_record(
            session,
            model=UnifiDoor,
            id_field="unifi_door_id",
            property_id=property_.id,
            payload=door_payload,
            now=now,
        )
        door_group_unifi_id = _payload_id(door_payload, ("door_group_id", "doorGroupId"))
        if record is not None and door_group_unifi_id in door_groups_by_unifi_id:
            record.door_group_id = door_groups_by_unifi_id[door_group_unifi_id].id
        external_id = _payload_id(door_payload, ("id", "uuid", "door_id", "doorId"))
        session.add(
            SyncSnapshot(
                property_id=property_.id,
                sync_run_id=run.id,
                snapshot_type="unifi_door",
                external_id=external_id,
                normalized_json={"id": external_id, "name": _payload_text(door_payload, "name"), "status": _payload_text(door_payload, "status", "state")},
                raw_snapshot_json=sanitize_for_snapshot(door_payload),
                observed_at=observed_at,
            )
        )
        counts["snapshots_stored"] += 1
        if record is not None:
            counts["doors_upserted"] += 1

    run.status = "succeeded"
    run.completed_at = utcnow()
    run.summary_json = counts
    session.add(SyncRunLog(sync_run_id=run.id, level="info", message="Agent snapshot accepted", context_json=counts))
    session.commit()
    return {"sync_run": {"id": run.id, "status": run.status, "summary": counts}, "property": _property_json(property_)}


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
    property_ = _entrypoint_property(session)
    access_request = AccessRequest(
        property_id=property_.id,
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
    property_ = _entrypoint_property(session)
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
        "unifi_access_policies": session.scalar(select(func.count(UnifiAccessPolicy.id))) or 0,
        "unifi_user_groups": session.scalar(select(func.count(UnifiUserGroup.id))) or 0,
        "unifi_doors": session.scalar(select(func.count(UnifiDoor.id))) or 0,
        "sync_runs": session.scalar(select(func.count(SyncRun.id))) or 0,
        "staged_access_changes": session.scalar(select(func.count(StagedAccessChange.id))) or 0,
        "unmatched_unifi_snapshots": session.scalar(
            select(func.count(UnifiUser.id)).where(UnifiUser.local_user_id.is_(None))
        )
        or 0,
    }
    return {
        "account": _account_json(account),
        "property": _property_json(property_),
        "stats": stats,
        "recent_requests": [
            _request_json(access_request)
            for access_request in session.scalars(select(AccessRequest).order_by(AccessRequest.created_at.desc()).limit(8))
        ],
        "recent_conflicts": [
            _conflict_json(conflict)
            for conflict in session.scalars(select(Conflict).order_by(Conflict.created_at.desc()).limit(8))
        ],
        "recent_reports": [_report_json(run) for run in session.scalars(select(ReportRun).order_by(ReportRun.created_at.desc()).limit(5))],
        "recent_sync_jobs": [_sync_job_json(job) for job in session.scalars(select(SyncJob).order_by(SyncJob.created_at.desc()).limit(8))],
        "analytics": {
            "sync_activity": [
                {"label": "Pending", "value": session.scalar(select(func.count(SyncJob.id)).where(SyncJob.status == "pending")) or 0},
                {"label": "Succeeded", "value": session.scalar(select(func.count(SyncJob.id)).where(SyncJob.status == "succeeded")) or 0},
                {"label": "Failed", "value": session.scalar(select(func.count(SyncJob.id)).where(SyncJob.status == "failed")) or 0},
            ],
            "conflict_summary": [
                {
                    "label": severity.title(),
                    "value": sum(1 for conflict in session.scalars(select(Conflict)).all() if _conflict_severity(conflict) == severity),
                }
                for severity in ["high", "medium", "low"]
            ],
            "verification_status": [
                {"label": "Current", "value": stats["active_users"] - stats["stale_verification"]},
                {"label": "Stale", "value": stats["stale_verification"]},
            ],
        },
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
    property_ = _entrypoint_property(session)
    before = {"status": access_request.status}
    access_request.property_id = access_request.property_id or property_.id
    access_request.requested_for_company_id = payload.requested_for_company_id
    access_request.requested_for_suite_id = payload.requested_for_suite_id
    access_request.requested_access_profile_id = payload.requested_access_profile_id
    access_request.admin_notes = payload.admin_notes or None
    access_request.status = "pending_sync"
    access_request.approved_by_account_id = account.id
    access_request.approved_at = utcnow()
    job = SyncJob(
        property_id=property_.id,
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
    session.flush()
    session.add(
        StagedAccessChange(
            property_id=property_.id,
            sync_job_id=job.id,
            access_request_id=access_request.id,
            local_user_id=access_request.requested_for_user_id,
            unifi_user_id=None,
            change_type=access_request.request_type,
            status="staged",
            proposed_before_json=None,
            proposed_after_json={
                "request_id": access_request.id,
                "email": access_request.requested_for_email,
                "company_id": access_request.requested_for_company_id,
                "suite_id": access_request.requested_for_suite_id,
                "access_profile_id": access_request.requested_access_profile_id,
                "dry_run": True,
            },
        )
    )
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
    db_identity = safe_database_identity()
    total_users = session.scalar(select(func.count(User.id))) or 0
    active_users = session.scalar(select(func.count(User.id)).where(User.status == "active")) or 0
    snapshot_count = session.scalar(select(func.count(UnifiUser.id))) or 0
    unmatched_snapshot_count = (
        session.scalar(select(func.count(UnifiUser.id)).where(UnifiUser.local_user_id.is_(None))) or 0
    )
    users = session.scalars(select(User).order_by(User.last_name, User.first_name)).all()
    logger.info(
        "admin users fetch db_driver=%s db_host=%s db_name=%s filters=%s users_found=%s active_users=%s "
        "unifi_snapshots=%s unmatched_unifi_snapshots=%s",
        db_identity["driver"],
        db_identity["host"],
        db_identity["database"],
        "none",
        len(users),
        active_users,
        snapshot_count,
        unmatched_snapshot_count,
    )

    user_rows = []
    linked_snapshot_ids: set[int] = set()
    for user in users:
        snapshot = session.scalar(
            select(UnifiUser)
            .where((UnifiUser.local_user_id == user.id) | (func.lower(UnifiUser.email) == user.email.lower()))
            .order_by(UnifiUser.local_user_id.desc(), UnifiUser.last_seen_at.desc().nullslast())
            .limit(1)
        )
        if snapshot is not None:
            linked_snapshot_ids.add(snapshot.id)
        user_rows.append(_user_json(user, snapshot))

    unmatched_query = select(UnifiUser).where(UnifiUser.local_user_id.is_(None)).order_by(
        UnifiUser.full_name, UnifiUser.email, UnifiUser.unifi_user_id
    )
    if linked_snapshot_ids:
        unmatched_query = unmatched_query.where(UnifiUser.id.not_in(linked_snapshot_ids))
    unmatched_snapshots = session.scalars(unmatched_query).all()
    for snapshot in unmatched_snapshots:
        user_rows.append(_snapshot_user_json(snapshot))

    return {
        "users": user_rows,
        "meta": {
            "total_users": total_users,
            "unifi_snapshots": snapshot_count,
            "unmatched_unifi_snapshots": unmatched_snapshot_count,
            "rows_returned": len(user_rows),
            "filters": {},
        },
    }


@router.get("/admin/companies")
def api_admin_companies(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    companies = []
    for company in session.scalars(select(Company).order_by(Company.name)).all():
        item = _company_json(company) or {}
        item["active_user_count"] = session.scalar(
            select(func.count(User.id)).where(User.company_id == company.id, User.status == "active")
        ) or 0
        item["suite_count"] = session.scalar(select(func.count(CompanySuite.id)).where(CompanySuite.company_id == company.id)) or 0
        companies.append(item)
    return {"companies": companies}


@router.get("/admin/suites")
def api_admin_suites(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    suites = []
    for suite in session.scalars(select(Suite).order_by(Suite.suite_number)).all():
        item = _suite_json(suite) or {}
        occupancy = session.scalar(
            select(CompanySuite).where(CompanySuite.suite_id == suite.id, CompanySuite.occupancy_status == "active")
        )
        item["assigned_company"] = _company_json(occupancy.company) if occupancy else None
        item["active_user_count"] = session.scalar(
            select(func.count(User.id)).where(User.primary_suite_id == suite.id, User.status == "active")
        ) or 0
        suites.append(item)
    return {"suites": suites}


@router.get("/admin/occupancy")
def api_admin_occupancy(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    rows = []
    for occupancy in session.scalars(select(CompanySuite).order_by(CompanySuite.created_at.desc())).all():
        active_count = session.scalar(
            select(func.count(User.id)).where(
                User.company_id == occupancy.company_id,
                User.primary_suite_id == occupancy.suite_id,
                User.status == "active",
            )
        ) or 0
        rows.append(_occupancy_json(occupancy, active_count))
    return {"occupancy": rows}


@router.get("/admin/access-profiles")
def api_admin_access_profiles(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    profiles = []
    for profile in session.scalars(select(AccessProfile).order_by(AccessProfile.name)).all():
        item = _profile_json(profile) or {}
        item["assignment_count"] = session.scalar(select(func.count(User.id)).where(User.access_profile_id == profile.id)) or 0
        profiles.append(item)
    return {"profiles": profiles}


@router.get("/admin/conflicts")
def api_admin_conflicts(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    return {"conflicts": [_conflict_json(conflict) for conflict in session.scalars(select(Conflict).order_by(Conflict.created_at.desc())).all()]}


@router.post("/admin/conflicts/{conflict_id}/resolve")
def api_resolve_conflict(
    conflict_id: int,
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    conflict = session.get(Conflict, conflict_id)
    if conflict is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")
    conflict.status = "resolved"
    conflict.resolved_by_account_id = account.id
    conflict.resolved_at = utcnow()
    session.commit()
    return {"conflict": _conflict_json(conflict)}


@router.get("/admin/sync-jobs")
def api_admin_sync_jobs(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    return {"sync_jobs": [_sync_job_json(job) for job in session.scalars(select(SyncJob).order_by(SyncJob.created_at.desc())).all()]}


@router.get("/admin/bootstrap")
def api_admin_bootstrap(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    unmatched = session.scalars(select(UnifiUser).where(UnifiUser.local_user_id.is_(None)).order_by(UnifiUser.email, UnifiUser.unifi_user_id)).all()
    batches = session.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(12)).all()
    return {
        "unmatched_count": len(unmatched),
        "unmatched": [
            {
                "id": user.id,
                "unifi_user_id": user.unifi_user_id,
                "name": user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip(),
                "email": user.email,
                "employee_number": user.employee_number,
                "suite_number": user.suite_number,
                "status": user.status,
                "last_seen_at": user.last_seen_at,
            }
            for user in unmatched
        ],
        "recent_batches": [
            {
                "id": batch.id,
                "source": batch.source,
                "status": batch.status,
                "filename": batch.filename,
                "summary_json": batch.summary_json or {},
                "created_at": batch.created_at,
                "committed_at": batch.committed_at,
            }
            for batch in batches
        ],
    }


@router.get("/admin/audit-logs")
def api_admin_audit_logs(
    session: Session = Depends(get_session),
    account: PortalAccount = Depends(_require_api_admin),
):
    return {"audit_logs": [_audit_log_json(log) for log in session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(250)).all()]}


@router.get("/admin/settings")
def api_admin_settings(
    account: PortalAccount = Depends(_require_api_admin),
):
    settings = get_settings()
    return {
        "settings": {
            "public_base_url": settings.public_base_url,
            "auth_mode": settings.auth_mode,
            "enable_writes": settings.enable_writes,
            "enable_email": settings.enable_email,
            "enable_scheduled_reports": settings.enable_scheduled_reports,
            "report_default_type": settings.report_default_type,
            "report_timezone": settings.report_timezone,
        }
    }


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
