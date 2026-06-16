from __future__ import annotations

import pytest

from app.unifi_normalization import normalize_unifi_user


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("email", "email@example.com"),
        ("user_email", "user_email@example.com"),
        ("userEmail", "userEmail@example.com"),
        ("mail", "mail@example.com"),
        ("email_address", "email_address@example.com"),
        ("emailAddress", "emailAddress@example.com"),
    ],
)
def test_email_fallbacks(key: str, value: str) -> None:
    assert normalize_unifi_user({"id": "u-1", key: value})["email"] == value.casefold()


def test_normalization_preserves_old_exporter_fields() -> None:
    normalized = normalize_unifi_user(
        {
            "uuid": "u-1",
            "givenName": "Ada",
            "surname": "Lovelace",
            "displayName": "Ada L.",
            "emailStatus": "verified",
            "employeeId": "120-EMP",
            "suiteNumber": "1400",
            "mobilePhone": "555-0100",
            "userName": "alovelace",
            "nickname": "Ada",
            "userStatus": "ACTIVE",
            "createdAt": "2026-01-02T03:04:05Z",
            "accessPolicies": [{"policyId": "p-1", "policyName": "Front Door"}],
            "departments": [{"groupId": "g-1", "groupName": "Employees"}],
            "accessCards": [{"id": "card-1"}, {"id": "card-2"}],
            "mobileCredential": {"state": "enabled", "lastUsedAt": "2026-01-03T00:00:00Z"},
            "vehicles": [{"plate": "REDACTED"}],
        },
        raw_file="raw.json",
    )

    assert normalized == {
        "id": "u-1",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "full_name": "Ada L.",
        "email": "",
        "email_status": "verified",
        "employee_number": "120-EMP",
        "suite_number": "1400",
        "phone": "555-0100",
        "username": "alovelace",
        "alias": "Ada",
        "status": "active",
        "onboard_time": "2026-01-02T03:04:05Z",
        "access_policy_ids": ["p-1"],
        "access_policy_names": ["Front Door"],
        "group_ids": ["g-1"],
        "group_names": ["Employees"],
        "nfc_card_count": 2,
        "touch_pass_status": "enabled",
        "touch_pass_last_activity": "2026-01-03T00:00:00Z",
        "license_plate_count": 1,
        "raw_user_json_file": "raw.json",
    }


def test_suite_number_prefers_explicit_field() -> None:
    normalized = normalize_unifi_user({"id": "u-1", "employeeNumber": "120999", "suite": "1500"})

    assert normalized["suite_number"] == "1500"


def test_suite_number_falls_back_to_first_three_digits_of_employee_number() -> None:
    normalized = normalize_unifi_user({"id": "u-1", "employeeNumber": "120999"})

    assert normalized["suite_number"] == "120"
