from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://building_access:change_me@db:5432/building_access_registry"
    direct_url: str = ""
    entrypoint_agent_token: str = ""
    app_secret_key: str = "change_me"
    admin_email: str = "admin@example.com"
    admin_initial_password: str = ""
    public_base_url: str = "http://localhost:8080"
    auth_mode: str = "local"
    trust_proxy_headers: bool = False
    log_level: str = "INFO"
    export_dir: Path = Path("/app/exports")

    unifi_access_base_url: str = "https://192.168.1.1:12445"
    unifi_access_token: str = ""
    unifi_access_verify_ssl: bool = False
    unifi_access_page_size: int = 100
    unifi_agent_name: str = "1205-local-lan-agent"
    unifi_snapshot_source: str = "local_lan_agent"
    enable_writes: bool = False
    sync_interval_seconds: int = 300

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Building Access Registry"
    smtp_use_tls: bool = True
    enable_email: bool = False

    report_default_recipients: str = ""
    report_verification_expiration_days: int = 14
    enable_scheduled_reports: bool = False
    report_schedule_cron: str = "0 8 1 * *"
    report_timezone: str = "America/New_York"
    report_default_type: str = "full_building_access"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

