from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class WritesDisabledError(RuntimeError):
    pass


class UniFiAccessClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.unifi_access_token}"}

    async def list_users(self) -> list[dict[str, Any]]:
        if not self.settings.unifi_access_token:
            return []
        async with httpx.AsyncClient(verify=self.settings.unifi_access_verify_ssl, timeout=30) as client:
            response = await client.get(
                f"{self.settings.unifi_access_base_url.rstrip('/')}/api/v1/developer/users",
                headers=self._headers(),
                params={"page_num": 1, "page_size": self.settings.unifi_access_page_size},
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("data", payload if isinstance(payload, list) else [])

    async def get_user(self, unifi_user_id: str) -> dict[str, Any] | None:
        users = await self.list_users()
        return next((user for user in users if str(user.get("id")) == unifi_user_id), None)

    async def list_access_policies(self) -> list[dict[str, Any]]:
        return []

    async def list_user_groups(self) -> list[dict[str, Any]]:
        return []

    def _ensure_writes_enabled(self) -> None:
        if not self.settings.enable_writes:
            raise WritesDisabledError("UniFi writes are disabled. Set ENABLE_WRITES=true to allow write calls.")

    async def create_user(self, payload: dict[str, Any]) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 1.")

    async def update_user(self, unifi_user_id: str, payload: dict[str, Any]) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 1.")

    async def set_user_status(self, unifi_user_id: str, status: str) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 1.")

    async def assign_access_policies(self, unifi_user_id: str, policy_ids: list[str]) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 1.")

