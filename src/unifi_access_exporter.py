from __future__ import annotations

import csv
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.unifi_normalization import (
    as_text as str_or_empty,
    first_present,
    ids as extract_ids,
    list_values as list_objects,
    names as extract_names,
    normalize_unifi_user,
    sanitize_for_snapshot as sanitize_for_export,
)

try:
    import requests
except ImportError:  # pragma: no cover - dependency is installed in Docker/runtime
    requests = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - lets stdlib-only unit tests import the module
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

try:
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except ImportError:  # pragma: no cover - fallback for local test environments without deps
    def retry(*_args: Any, **_kwargs: Any):
        def decorator(func: Any) -> Any:
            return func
        return decorator

    def retry_if_exception_type(*_args: Any, **_kwargs: Any) -> None:
        return None

    def stop_after_attempt(*_args: Any, **_kwargs: Any) -> None:
        return None

    def wait_exponential(*_args: Any, **_kwargs: Any) -> None:
        return None


API_PATH = "/api/v1/developer/users"
CSV_FIELDS = [
    "id",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "email_status",
    "employee_number",
    "suite_number",
    "phone",
    "username",
    "alias",
    "status",
    "onboard_time",
    "access_policy_ids",
    "access_policy_names",
    "group_ids",
    "group_names",
    "nfc_card_count",
    "touch_pass_status",
    "touch_pass_last_activity",
    "license_plate_count",
    "raw_user_json_file",
]
LITE_CSV_FIELDS = [
    "first_name",
    "last_name",
    "full_name",
    "email",
    "employee_number",
    "suite_number",
    "status",
    "access_policy_names",
]

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
    "webhook",
)


class ConfigError(ValueError):
    pass


class ExporterError(RuntimeError):
    pass


class AuthError(ExporterError):
    pass


class TLSCertificateError(ExporterError):
    pass


class TransientHTTPError(ExporterError):
    pass


@dataclass(frozen=True)
class Config:
    base_url: str
    token: str
    verify_ssl: bool
    page_size: int
    output_dir: Path
    export_csv: bool
    export_json: bool
    log_level: str
    sync_mode: str
    source_of_truth: str
    enable_writes: bool


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"Invalid boolean value: {value!r}")


def load_config() -> Config:
    load_dotenv()

    base_url = os.getenv("UNIFI_ACCESS_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("UNIFI_ACCESS_TOKEN", "").strip()
    page_size_raw = os.getenv("UNIFI_ACCESS_PAGE_SIZE", "100").strip()
    sync_mode = os.getenv("SYNC_MODE", "export_only").strip().lower()
    enable_writes = parse_bool(os.getenv("ENABLE_WRITES"), default=False)

    if not base_url:
        raise ConfigError("UNIFI_ACCESS_BASE_URL is required")
    if not token or token == "replace_me":
        raise ConfigError("UNIFI_ACCESS_TOKEN is required")

    try:
        page_size = int(page_size_raw)
    except ValueError as exc:
        raise ConfigError("UNIFI_ACCESS_PAGE_SIZE must be an integer") from exc
    if page_size < 1 or page_size > 1000:
        raise ConfigError("UNIFI_ACCESS_PAGE_SIZE must be between 1 and 1000")

    if sync_mode != "export_only" and not enable_writes:
        raise ConfigError("Non-export sync modes require ENABLE_WRITES=true")
    if enable_writes:
        raise ConfigError("Write/sync behavior is not implemented in this version")

    return Config(
        base_url=base_url,
        token=token,
        verify_ssl=parse_bool(os.getenv("UNIFI_ACCESS_VERIFY_SSL"), default=True),
        page_size=page_size,
        output_dir=Path(os.getenv("OUTPUT_DIR", "./exports")),
        export_csv=parse_bool(os.getenv("EXPORT_CSV"), default=True),
        export_json=parse_bool(os.getenv("EXPORT_JSON"), default=True),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        sync_mode=sync_mode,
        source_of_truth=os.getenv("SOURCE_OF_TRUTH", "unifi_access").strip(),
        enable_writes=enable_writes,
    )


class UniFiAccessClient:
    def __init__(self, config: Config, session: Any | None = None) -> None:
        if requests is None and session is None:
            raise RuntimeError("The 'requests' package is required to call the UniFi Access API")
        self.config = config
        self.session = session or requests.Session()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(TransientHTTPError),
    )
    def get_users_page(self, page_num: int) -> dict[str, Any] | list[Any]:
        url = f"{self.config.base_url}{API_PATH}"
        params: list[tuple[str, Any]] = [
            ("page_num", page_num),
            ("page_size", self.config.page_size),
            ("expand[]", "access_policy"),
        ]
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.token}",
        }

        try:
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=(5, 30),
                verify=self.config.verify_ssl,
            )
        except Exception as exc:
            if requests is not None and isinstance(exc, requests.exceptions.SSLError):
                raise TLSCertificateError(
                    "TLS certificate validation failed. If this is a trusted local console "
                    "with a self-signed certificate, set UNIFI_ACCESS_VERIFY_SSL=false."
                ) from exc
            if requests is not None and isinstance(
                exc,
                (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
            ):
                raise TransientHTTPError(f"Transient connection failure: {exc}") from exc
            raise ExporterError(f"Failed to call UniFi Access API: {exc}") from exc

        if response.status_code in {401, 403}:
            raise AuthError("UniFi Access API authentication failed. Check token and read/view user permissions.")
        if response.status_code in {408, 409, 425, 429} or 500 <= response.status_code < 600:
            raise TransientHTTPError(f"Transient API failure: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ExporterError(f"UniFi Access API request failed: HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ExporterError("UniFi Access API returned invalid JSON") from exc

        return payload

    def fetch_all_users(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        page_num = 1

        while True:
            payload = self.get_users_page(page_num)
            page_users = extract_users(payload)
            if not page_users:
                break
            users.extend(page_users)

            if not should_fetch_next_page(payload, page_num, len(page_users), self.config.page_size):
                break
            page_num += 1

        return users


def extract_users(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "users", "items", "results", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = extract_users(value)
            if nested:
                return nested
    return []


def should_fetch_next_page(
    payload: dict[str, Any] | list[Any],
    page_num: int,
    returned_count: int,
    page_size: int,
) -> bool:
    if returned_count < page_size:
        return False
    if not isinstance(payload, dict):
        return returned_count == page_size

    metadata_sources = [
        payload,
        payload.get("meta"),
        payload.get("metadata"),
        payload.get("pagination"),
        payload.get("page"),
    ]
    metadata = [source for source in metadata_sources if isinstance(source, dict)]

    for source in metadata:
        has_more = first_present(source, ("has_more", "hasMore", "next", "next_page", "nextPage"))
        if isinstance(has_more, bool):
            return has_more
        if has_more is None:
            continue
        if isinstance(has_more, (str, int)):
            return bool(has_more)

    for source in metadata:
        total_pages = first_present(source, ("total_pages", "totalPages", "page_count", "pageCount"))
        if total_pages is not None:
            try:
                return page_num < int(total_pages)
            except (TypeError, ValueError):
                pass

    for source in metadata:
        total = first_present(source, ("total", "total_count", "totalCount"))
        if total is not None:
            try:
                return page_num * page_size < int(total)
            except (TypeError, ValueError):
                pass

    return True


def normalize_user(user: dict[str, Any], raw_user_json_file: str = "") -> dict[str, Any]:
    normalized = normalize_unifi_user(user, raw_file=raw_user_json_file)
    row = dict(normalized)
    for key in ("access_policy_ids", "access_policy_names", "group_ids", "group_names"):
        row[key] = join_values(row[key])
    row["nfc_card_count"] = str(row["nfc_card_count"])
    row["license_plate_count"] = str(row["license_plate_count"])
    return row


def join_values(values: Iterable[str]) -> str:
    return ";".join(values)


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_lite_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=LITE_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def export_users(config: Config, users: list[dict[str, Any]]) -> tuple[Path | None, Path | None, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = config.output_dir / f"unifi_access_users_raw_{timestamp}.json"
    normalized_path = config.output_dir / f"unifi_access_users_normalized_{timestamp}.json"
    csv_path = config.output_dir / f"unifi_access_users_{timestamp}.csv"
    lite_csv_path = config.output_dir / f"Unifi_Acess_Users_Lite_{timestamp}.csv"

    raw_filename = raw_path.name
    normalized_users = [normalize_user(user, raw_user_json_file=raw_filename) for user in users]
    sanitized_raw = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "source": "unifi_access",
        "count": len(users),
        "users": sanitize_for_export(users),
    }

    write_json(raw_path, sanitized_raw)
    written_json_path = write_json(normalized_path, normalized_users) if config.export_json else None
    written_csv_path = write_csv(csv_path, normalized_users) if config.export_csv else None
    if config.export_csv:
        write_lite_csv(lite_csv_path, normalized_users)

    return written_csv_path, written_json_path, raw_path


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main() -> int:
    try:
        config = load_config()
        configure_logging(config.log_level)
        client = UniFiAccessClient(config)
        users = client.fetch_all_users()
        csv_path, json_path, raw_path = export_users(config, users)

        print(f"Exported {len(users)} users")
        print(f"CSV path: {csv_path if csv_path else 'disabled'}")
        print(f"JSON path: {json_path if json_path else 'disabled'}")
        print(f"Raw path: {raw_path}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
