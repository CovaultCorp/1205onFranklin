from __future__ import annotations

import json
import re
from typing import Any, Iterable

SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "pin",
    "hash",
    "credential",
    "private_key",
    "auth",
    "cookie",
    "session",
    "card",
    "license_plate",
    "licenseplate",
    "plate",
    "webhook",
)


def first_present(source: dict[str, Any], keys: Iterable[str]) -> Any:
    if not isinstance(source, dict):
        return None
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return None


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value).strip()


def list_values(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def ids(items: Iterable[Any]) -> list[str]:
    values: list[str] = []
    for item in items:
        if isinstance(item, dict):
            value = first_present(item, ("id", "policy_id", "policyId", "group_id", "groupId", "uuid"))
        else:
            value = item
        text = as_text(value)
        if text:
            values.append(text)
    return values


def names(items: Iterable[Any]) -> list[str]:
    values: list[str] = []
    for item in items:
        if isinstance(item, dict):
            value = first_present(item, ("name", "display_name", "displayName", "policy_name", "policyName", "group_name", "groupName"))
        else:
            value = item
        text = as_text(value)
        if text:
            values.append(text)
    return values


def suite_number(user: dict[str, Any]) -> str:
    explicit = as_text(first_present(user, ("suite_number", "suiteNumber", "suite")))
    if explicit:
        return explicit
    employee_number = as_text(first_present(user, ("employee_number", "employeeNumber", "employee_id", "employeeId")))
    match = re.search(r"\d{3}", employee_number)
    return match.group(0) if match else ""


def normalize_unifi_user(user: dict[str, Any], raw_file: str | None = None) -> dict[str, Any]:
    first_name = as_text(first_present(user, ("first_name", "firstName", "given_name", "givenName")))
    last_name = as_text(first_present(user, ("last_name", "lastName", "family_name", "familyName", "surname")))
    full_name = as_text(first_present(user, ("full_name", "fullName", "name", "display_name", "displayName")))
    if not full_name:
        full_name = " ".join(part for part in (first_name, last_name) if part)

    access_policies = list_values(first_present(user, ("access_policy", "access_policies", "accessPolicy", "accessPolicies")))
    groups = list_values(first_present(user, ("groups", "user_groups", "userGroups", "departments", "department")))
    nfc_cards = list_values(first_present(user, ("nfc_cards", "nfcCards", "cards", "access_cards", "accessCards")))
    license_plates = list_values(first_present(user, ("license_plates", "licensePlates", "vehicles", "plates")))
    touch_pass = first_present(user, ("touch_pass", "touchPass", "mobile_credential", "mobileCredential"))
    touch_pass_obj = touch_pass if isinstance(touch_pass, dict) else {}

    return {
        "id": as_text(first_present(user, ("id", "user_id", "userId", "uuid"))),
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": as_text(first_present(user, ("email", "user_email", "userEmail", "mail", "email_address", "emailAddress"))).casefold(),
        "email_status": as_text(first_present(user, ("email_status", "emailStatus"))),
        "employee_number": as_text(first_present(user, ("employee_number", "employeeNumber", "employee_id", "employeeId"))),
        "suite_number": suite_number(user),
        "phone": as_text(first_present(user, ("phone", "phone_number", "phoneNumber", "mobile", "mobile_phone", "mobilePhone"))),
        "username": as_text(first_present(user, ("username", "user_name", "userName"))),
        "alias": as_text(first_present(user, ("alias", "nickname"))),
        "status": as_text(first_present(user, ("status", "state", "user_status", "userStatus"))).casefold(),
        "onboard_time": as_text(first_present(user, ("onboard_time", "onboardTime", "created_at", "createdAt"))),
        "access_policy_ids": ids(access_policies),
        "access_policy_names": names(access_policies),
        "group_ids": ids(groups),
        "group_names": names(groups),
        "nfc_card_count": len(nfc_cards),
        "touch_pass_status": as_text(first_present(touch_pass_obj, ("status", "state"))),
        "touch_pass_last_activity": as_text(first_present(touch_pass_obj, ("last_activity", "lastActivity", "last_used_at", "lastUsedAt"))),
        "license_plate_count": len(license_plates),
        "raw_user_json_file": raw_file or "",
    }


def sanitize_for_snapshot(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            sanitized[key] = "[REDACTED]" if _is_sensitive_key(key) else sanitize_for_snapshot(nested)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_snapshot(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
