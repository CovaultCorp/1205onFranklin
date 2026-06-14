from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessProfile, Company, Conflict, Suite, SyncJob, UnifiUser, User, utcnow
from app.unifi_client import UniFiAccessClient

ACTIVE_UNIFI_STATUSES = {"active", "enabled", "normal"}
INACTIVE_UNIFI_STATUSES = {"inactive", "deactivated", "disabled", "suspended"}


@dataclass
class ReconciliationSummary:
    unifi_users_seen: int = 0
    snapshots_upserted: int = 0
    matched_users: int = 0
    conflicts_created: int = 0
    conflicts_existing: int = 0
    proposed_actions: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "unifi_users_seen": self.unifi_users_seen,
            "snapshots_upserted": self.snapshots_upserted,
            "matched_users": self.matched_users,
            "conflicts_created": self.conflicts_created,
            "conflicts_existing": self.conflicts_existing,
            "proposed_action_count": len(self.proposed_actions),
        }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _lower(value: Any) -> str | None:
    text = _text(value)
    return text.lower() if text else None


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _unifi_id(payload: dict[str, Any]) -> str:
    value = _first_present(payload, ("id", "user_id", "userId"))
    if value is None:
        raise ValueError("UniFi user payload is missing an id")
    return str(value)


def _employee_number(payload: dict[str, Any]) -> str | None:
    return _text(_first_present(payload, ("employeeNumber", "employee_number", "employeeNo")))


def _first_name(payload: dict[str, Any]) -> str | None:
    return _text(_first_present(payload, ("firstName", "first_name", "first")))


def _last_name(payload: dict[str, Any]) -> str | None:
    return _text(_first_present(payload, ("lastName", "last_name", "last")))


def _email(payload: dict[str, Any]) -> str | None:
    return _lower(_first_present(payload, ("email", "mail")))


def _status(payload: dict[str, Any]) -> str | None:
    return _lower(_first_present(payload, ("status", "state")))


def _ids_from_collection(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        ids: list[str] = []
        for item in value:
            if isinstance(item, dict):
                item_id = _first_present(item, ("id", "policy_id", "policyId", "group_id", "groupId"))
                if item_id is not None:
                    ids.append(str(item_id))
            elif item is not None:
                ids.append(str(item))
        return sorted(set(ids))
    if isinstance(value, dict):
        item_id = _first_present(value, ("id", "policy_id", "policyId"))
        return [str(item_id)] if item_id is not None else []
    return [str(value)]


def _access_policy_ids(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("access_policy", "accessPolicy", "access_policies", "accessPolicies", "access_policy_ids", "accessPolicyIds"):
        ids.extend(_ids_from_collection(payload.get(key)))
    return sorted(set(ids))


def _is_unifi_active(status: str | None) -> bool:
    return (status or "").lower() in ACTIVE_UNIFI_STATUSES


def _desired_policy_ids(session: Session, local_user: User) -> list[str]:
    profile = local_user.access_profile
    if local_user.primary_suite_id is not None:
        profile = profile or session.scalar(
            select(AccessProfile).where(
                AccessProfile.active.is_(True),
                AccessProfile.default_for_suite_id == local_user.primary_suite_id,
            )
        )
    if profile is None and local_user.company_id is not None:
        profile = session.scalar(
            select(AccessProfile).where(
                AccessProfile.active.is_(True),
                AccessProfile.default_for_company_id == local_user.company_id,
            )
        )
    return sorted(set(profile.unifi_access_policy_ids if profile else []))


def _snapshot_state(snapshot: UnifiUser) -> dict[str, Any]:
    return {
        "unifi_user_id": snapshot.unifi_user_id,
        "email": snapshot.email,
        "employee_number": snapshot.employee_number,
        "first_name": snapshot.first_name,
        "last_name": snapshot.last_name,
        "status": snapshot.status,
        "access_policy_ids": snapshot.access_policy_ids or [],
    }


def _local_state(local_user: User | None) -> dict[str, Any] | None:
    if local_user is None:
        return None
    return {
        "id": local_user.id,
        "email": local_user.email,
        "employee_number": local_user.employee_number,
        "first_name": local_user.first_name,
        "last_name": local_user.last_name,
        "status": local_user.status,
        "company_id": local_user.company_id,
        "primary_suite_id": local_user.primary_suite_id,
        "access_profile_id": local_user.access_profile_id,
    }


def _find_existing_open_conflict(
    session: Session,
    *,
    conflict_type: str,
    local_user_id: int | None,
    unifi_user_id: int | None,
) -> Conflict | None:
    return session.scalar(
        select(Conflict).where(
            Conflict.status == "open",
            Conflict.conflict_type == conflict_type,
            Conflict.local_user_id.is_(local_user_id) if local_user_id is None else Conflict.local_user_id == local_user_id,
            Conflict.unifi_user_id.is_(unifi_user_id) if unifi_user_id is None else Conflict.unifi_user_id == unifi_user_id,
        )
    )


def _record_conflict(
    session: Session,
    summary: ReconciliationSummary,
    *,
    conflict_type: str,
    description: str,
    local_user: User | None,
    snapshot: UnifiUser | None,
    local_state: dict[str, Any] | None = None,
    unifi_state: dict[str, Any] | None = None,
) -> Conflict:
    existing = _find_existing_open_conflict(
        session,
        conflict_type=conflict_type,
        local_user_id=local_user.id if local_user else None,
        unifi_user_id=snapshot.id if snapshot else None,
    )
    if existing:
        summary.conflicts_existing += 1
        return existing
    conflict = Conflict(
        local_user_id=local_user.id if local_user else None,
        unifi_user_id=snapshot.id if snapshot else None,
        conflict_type=conflict_type,
        description=description,
        local_state_json=local_state if local_state is not None else _local_state(local_user),
        unifi_state_json=unifi_state if unifi_state is not None else (_snapshot_state(snapshot) if snapshot else None),
        status="open",
    )
    session.add(conflict)
    session.flush()
    summary.conflicts_created += 1
    return conflict


def _upsert_snapshot(session: Session, payload: dict[str, Any], local_user: User | None) -> UnifiUser:
    unifi_user_id = _unifi_id(payload)
    snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == unifi_user_id))
    now = utcnow()
    if snapshot is None:
        snapshot = UnifiUser(unifi_user_id=unifi_user_id)
        session.add(snapshot)
    snapshot.local_user_id = local_user.id if local_user else snapshot.local_user_id
    snapshot.email = _email(payload)
    snapshot.employee_number = _employee_number(payload)
    snapshot.first_name = _first_name(payload)
    snapshot.last_name = _last_name(payload)
    snapshot.status = _status(payload)
    snapshot.access_policy_ids = _access_policy_ids(payload)
    snapshot.raw_snapshot_json = payload
    snapshot.last_seen_at = now
    snapshot.last_synced_at = now
    session.flush()
    return snapshot


def _find_local_match(
    session: Session,
    payload: dict[str, Any],
    existing_snapshot: UnifiUser | None,
) -> tuple[User | None, str | None]:
    if existing_snapshot and existing_snapshot.local_user_id:
        mapped = session.get(User, existing_snapshot.local_user_id)
        if mapped:
            return mapped, "unifi_user_id"

    employee_number = _employee_number(payload)
    if employee_number:
        user = session.scalar(select(User).where(User.employee_number == employee_number))
        if user:
            return user, "employee_number"

    email = _email(payload)
    if email:
        user = session.scalar(select(User).where(User.email == email))
        if user:
            return user, "email"

    return None, None


def _add_proposed_action(summary: ReconciliationSummary, action: str, reason: str, *, local_user: User | None = None, snapshot: UnifiUser | None = None, details: dict[str, Any] | None = None) -> None:
    summary.proposed_actions.append(
        {
            "action": action,
            "reason": reason,
            "dry_run": True,
            "local_user_id": local_user.id if local_user else None,
            "unifi_user_id": snapshot.unifi_user_id if snapshot else None,
            "details": details or {},
        }
    )


def _detect_duplicate_unifi_values(
    session: Session,
    summary: ReconciliationSummary,
    snapshots: list[UnifiUser],
) -> None:
    by_email: dict[str, list[UnifiUser]] = {}
    by_employee: dict[str, list[UnifiUser]] = {}
    for snapshot in snapshots:
        if snapshot.email:
            by_email.setdefault(snapshot.email, []).append(snapshot)
        if snapshot.employee_number:
            by_employee.setdefault(snapshot.employee_number, []).append(snapshot)

    for email, matching in by_email.items():
        if len(matching) > 1:
            for snapshot in matching:
                _record_conflict(
                    session,
                    summary,
                    conflict_type="duplicate_email",
                    description=f"Duplicate UniFi email {email}",
                    local_user=None,
                    snapshot=snapshot,
                    unifi_state={"email": email, "unifi_user_ids": [item.unifi_user_id for item in matching]},
                )
    for employee_number, matching in by_employee.items():
        if len(matching) > 1:
            for snapshot in matching:
                _record_conflict(
                    session,
                    summary,
                    conflict_type="duplicate_employee_number",
                    description=f"Duplicate UniFi employee number {employee_number}",
                    local_user=None,
                    snapshot=snapshot,
                    unifi_state={"employee_number": employee_number, "unifi_user_ids": [item.unifi_user_id for item in matching]},
                )


def _detect_matched_conflicts(
    session: Session,
    summary: ReconciliationSummary,
    *,
    local_user: User,
    snapshot: UnifiUser,
) -> None:
    if local_user.company_id is None:
        _record_conflict(
            session,
            summary,
            conflict_type="unifi_user_no_local_company",
            description=f"Matched UniFi user {snapshot.unifi_user_id} has no local company assignment.",
            local_user=local_user,
            snapshot=snapshot,
        )
        _add_proposed_action(summary, "review_company_assignment", "Matched user has no local company.", local_user=local_user, snapshot=snapshot)
    elif local_user.company and local_user.company.status != "active":
        _record_conflict(
            session,
            summary,
            conflict_type="user_in_inactive_company",
            description=f"Local user {local_user.email} belongs to inactive company {local_user.company.name}.",
            local_user=local_user,
            snapshot=snapshot,
        )

    if local_user.primary_suite_id is None:
        _record_conflict(
            session,
            summary,
            conflict_type="unifi_user_no_local_suite",
            description=f"Matched UniFi user {snapshot.unifi_user_id} has no local suite assignment.",
            local_user=local_user,
            snapshot=snapshot,
        )
        _add_proposed_action(summary, "review_suite_assignment", "Matched user has no local suite.", local_user=local_user, snapshot=snapshot)
    elif local_user.primary_suite and local_user.primary_suite.status != "active":
        _record_conflict(
            session,
            summary,
            conflict_type="user_in_inactive_suite",
            description=f"Local user {local_user.email} is assigned to inactive suite {local_user.primary_suite.suite_number}.",
            local_user=local_user,
            snapshot=snapshot,
        )

    local_active = local_user.status == "active"
    unifi_active = _is_unifi_active(snapshot.status)
    if local_active != unifi_active:
        _record_conflict(
            session,
            summary,
            conflict_type="status_mismatch",
            description=f"Status mismatch for {local_user.email}: local={local_user.status}, unifi={snapshot.status}.",
            local_user=local_user,
            snapshot=snapshot,
        )
        _add_proposed_action(
            summary,
            "review_status_mismatch",
            "Local and UniFi active states differ.",
            local_user=local_user,
            snapshot=snapshot,
            details={"local_status": local_user.status, "unifi_status": snapshot.status},
        )

    if snapshot.email and _lower(local_user.email) != snapshot.email:
        _record_conflict(
            session,
            summary,
            conflict_type="name_email_mismatch",
            description=f"Email mismatch for mapped user {local_user.id}: local={local_user.email}, unifi={snapshot.email}.",
            local_user=local_user,
            snapshot=snapshot,
        )
    if (
        snapshot.first_name
        and snapshot.last_name
        and (snapshot.first_name.lower() != local_user.first_name.lower() or snapshot.last_name.lower() != local_user.last_name.lower())
    ):
        _record_conflict(
            session,
            summary,
            conflict_type="name_email_mismatch",
            description=f"Name mismatch for {local_user.email}: local={local_user.first_name} {local_user.last_name}, unifi={snapshot.first_name} {snapshot.last_name}.",
            local_user=local_user,
            snapshot=snapshot,
        )

    desired_policy_ids = _desired_policy_ids(session, local_user)
    if desired_policy_ids and desired_policy_ids != sorted(snapshot.access_policy_ids or []):
        _record_conflict(
            session,
            summary,
            conflict_type="access_policy_mismatch",
            description=f"Access policy mismatch for {local_user.email}.",
            local_user=local_user,
            snapshot=snapshot,
            local_state={**(_local_state(local_user) or {}), "desired_access_policy_ids": desired_policy_ids},
        )
        _add_proposed_action(
            summary,
            "review_access_policy_assignment",
            "Desired local access profile differs from UniFi snapshot.",
            local_user=local_user,
            snapshot=snapshot,
            details={"desired_access_policy_ids": desired_policy_ids, "unifi_access_policy_ids": snapshot.access_policy_ids or []},
        )


async def run_unifi_reconciliation(
    session: Session,
    *,
    client: UniFiAccessClient | None = None,
) -> tuple[SyncJob, ReconciliationSummary]:
    client = client or UniFiAccessClient()
    summary = ReconciliationSummary()
    payloads = await client.list_users(expand_access_policy=True)
    summary.unifi_users_seen = len(payloads)

    matched_local_ids: set[int] = set()
    snapshots: list[UnifiUser] = []

    for payload in payloads:
        existing_snapshot = session.scalar(select(UnifiUser).where(UnifiUser.unifi_user_id == _unifi_id(payload)))
        local_user, match_method = _find_local_match(session, payload, existing_snapshot)
        snapshot = _upsert_snapshot(session, payload, local_user)
        summary.snapshots_upserted += 1
        snapshots.append(snapshot)
        if local_user:
            matched_local_ids.add(local_user.id)
            summary.matched_users += 1
            _detect_matched_conflicts(session, summary, local_user=local_user, snapshot=snapshot)
            if existing_snapshot is None or existing_snapshot.local_user_id != local_user.id:
                _add_proposed_action(
                    summary,
                    "link_unifi_snapshot",
                    f"Matched by {match_method}.",
                    local_user=local_user,
                    snapshot=snapshot,
                )
        elif _is_unifi_active(snapshot.status):
            _record_conflict(
                session,
                summary,
                conflict_type="unifi_active_user_not_found_locally",
                description=f"Active UniFi user {snapshot.unifi_user_id} was not found in the local registry.",
                local_user=None,
                snapshot=snapshot,
            )
            _add_proposed_action(summary, "review_unmatched_unifi_user", "Active UniFi user is not in local registry.", snapshot=snapshot)

    _detect_duplicate_unifi_values(session, summary, snapshots)

    local_active_users = session.scalars(select(User).where(User.status == "active")).all()
    for local_user in local_active_users:
        if local_user.id not in matched_local_ids:
            _record_conflict(
                session,
                summary,
                conflict_type="local_active_user_not_found_in_unifi",
                description=f"Local active user {local_user.email} was not found in UniFi snapshots.",
                local_user=local_user,
                snapshot=None,
            )
            _add_proposed_action(summary, "review_missing_unifi_user", "Local active user was not found in UniFi.", local_user=local_user)

    job = SyncJob(
        job_type="reconcile",
        status="succeeded",
        proposed_actions={
            "dry_run": True,
            "message": "Phase 2 read-only reconciliation. No UniFi write API calls were made.",
            "actions": summary.proposed_actions,
        },
        result_json=summary.as_dict(),
        attempt_count=1,
        completed_at=utcnow(),
    )
    session.add(job)
    session.flush()
    return job, summary
