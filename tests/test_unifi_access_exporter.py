from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.unifi_access_exporter import (
    Config,
    ConfigError,
    UniFiAccessClient,
    load_config,
    normalize_user,
    write_csv,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def test_config() -> Config:
    return Config(
        base_url="https://unifi.local:12445",
        token="token-value",
        verify_ssl=False,
        page_size=2,
        output_dir=Path("exports"),
        export_csv=True,
        export_json=True,
        log_level="INFO",
        sync_mode="export_only",
        source_of_truth="unifi_access",
        enable_writes=False,
    )


class ExporterTests(unittest.TestCase):
    def test_normalizes_sample_user(self) -> None:
        user = {
            "id": "u-1",
            "firstName": "Ada",
            "lastName": "Lovelace",
            "email": "ada@example.com",
            "employeeNumber": "E100",
            "status": "active",
            "onboardTime": "2026-01-02T03:04:05Z",
            "access_policy": [{"id": "p-1", "name": "Main Door"}],
            "groups": [{"id": "g-1", "name": "Engineering"}],
            "nfcCards": [{"id": "card-1"}, {"id": "card-2"}],
            "touchPass": {"status": "enabled", "lastActivity": "2026-01-03T00:00:00Z"},
            "licensePlates": [{"plate": "REDACTED"}],
        }

        row = normalize_user(user, raw_user_json_file="raw.json")

        self.assertEqual(row["id"], "u-1")
        self.assertEqual(row["full_name"], "Ada Lovelace")
        self.assertEqual(row["employee_number"], "E100")
        self.assertEqual(row["access_policy_ids"], "p-1")
        self.assertEqual(row["access_policy_names"], "Main Door")
        self.assertEqual(row["group_names"], "Engineering")
        self.assertEqual(row["nfc_card_count"], "2")
        self.assertEqual(row["touch_pass_status"], "enabled")
        self.assertEqual(row["license_plate_count"], "1")
        self.assertEqual(row["raw_user_json_file"], "raw.json")

    def test_pagination_fetches_until_short_page(self) -> None:
        session = FakeSession(
            [
                FakeResponse({"data": [{"id": "1"}, {"id": "2"}]}),
                FakeResponse({"data": [{"id": "3"}]}),
            ]
        )
        client = UniFiAccessClient(test_config(), session=session)

        users = client.fetch_all_users()

        self.assertEqual([user["id"] for user in users], ["1", "2", "3"])
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0]["params"][0], ("page_num", 1))
        self.assertIn(("expand[]", "access_policy"), session.calls[0]["params"])

    def test_csv_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            write_csv(
                path,
                [
                    {
                        "id": "u-1",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "full_name": "Ada Lovelace",
                        "email": "ada@example.com",
                        "employee_number": "E100",
                        "status": "active",
                        "onboard_time": "",
                        "access_policy_ids": "p-1",
                        "access_policy_names": "Main Door",
                        "group_ids": "",
                        "group_names": "",
                        "nfc_card_count": "0",
                        "touch_pass_status": "",
                        "touch_pass_last_activity": "",
                        "license_plate_count": "0",
                        "raw_user_json_file": "raw.json",
                    }
                ],
            )

            with path.open(newline="", encoding="utf-8") as csv_file:
                rows = list(csv.DictReader(csv_file))

        self.assertEqual(rows[0]["email"], "ada@example.com")
        self.assertEqual(rows[0]["access_policy_names"], "Main Door")

    def test_missing_token_validation(self) -> None:
        env = {
            "UNIFI_ACCESS_BASE_URL": "https://unifi.local:12445",
            "UNIFI_ACCESS_TOKEN": "",
            "UNIFI_ACCESS_PAGE_SIZE": "100",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError):
                load_config()


if __name__ == "__main__":
    unittest.main()
