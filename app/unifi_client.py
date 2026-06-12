from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class WritesDisabledError(RuntimeError):
    pass


class UniFiAccessClient:
    def __init__(self, settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings or get_settings()
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.unifi_access_token}"}

    async def _get_json(self, path: str, *, params: list[tuple[str, Any]] | dict[str, Any] | None = None) -> Any:
        if not self.settings.unifi_access_token:
            return {"data": []}
        async with httpx.AsyncClient(
            verify=self.settings.unifi_access_verify_ssl,
            timeout=30,
            transport=self.transport,
        ) as client:
            response = await client.get(
                f"{self.settings.unifi_access_base_url.rstrip('/')}{path}",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _items_from_payload(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    async def _list_paginated(self, path: str, *, params: list[tuple[str, Any]] | None = None) -> list[dict[str, Any]]:
        if not self.settings.unifi_access_token:
            return []
        page_size = self.settings.unifi_access_page_size
        all_items: list[dict[str, Any]] = []
        page_num = 1
        while True:
            page_params = list(params or [])
            page_params.extend([("page_num", page_num), ("page_size", page_size)])
            payload = await self._get_json(path, params=page_params)
            items = self._items_from_payload(payload)
            all_items.extend(items)
            if len(items) < page_size:
                break
            page_num += 1
        return all_items

    async def list_users(self, expand_access_policy: bool = True) -> list[dict[str, Any]]:
        if not self.settings.unifi_access_token:
            return []
        params: list[tuple[str, Any]] = []
        if expand_access_policy:
            params.extend([("expand[]", "access_policy"), ("expand[]", "groups")])
        return await self._list_paginated("/api/v1/developer/users", params=params)

    async def get_user(self, unifi_user_id: str) -> dict[str, Any] | None:
        if not self.settings.unifi_access_token:
            return None
        payload = await self._get_json(f"/api/v1/developer/users/{unifi_user_id}")
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload if isinstance(payload, dict) else None

    async def list_access_policies(self) -> list[dict[str, Any]]:
        return await self._list_paginated("/api/v1/developer/access_policies")

    async def list_user_groups(self) -> list[dict[str, Any]]:
        return await self._list_paginated("/api/v1/developer/user_groups")

    def _ensure_writes_enabled(self) -> None:
        if not self.settings.enable_writes:
            raise WritesDisabledError("UniFi writes are disabled. Set ENABLE_WRITES=true to allow write calls.")

    async def create_user(self, payload: dict[str, Any]) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 2.")

    async def update_user(self, unifi_user_id: str, payload: dict[str, Any]) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 2.")

    async def set_user_status(self, unifi_user_id: str, status: str) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 2.")

    async def assign_access_policies(self, unifi_user_id: str, policy_ids: list[str]) -> None:
        self._ensure_writes_enabled()
        raise NotImplementedError("UniFi write behavior is not implemented in Phase 2.")
