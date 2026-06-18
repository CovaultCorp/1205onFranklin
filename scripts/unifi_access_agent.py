from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.unifi_client import UniFiAccessClient

logger = logging.getLogger("entrypoint.unifi_agent")


def _endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/agent/snapshots"


async def _optional_resource(name: str, loader: Callable[[], Awaitable[list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    try:
        return await loader()
    except httpx.HTTPStatusError as exc:
        logger.warning("UniFi resource %s is unavailable: HTTP %s", name, exc.response.status_code)
        return []
    except httpx.HTTPError as exc:
        logger.warning("UniFi resource %s could not be read: %s", name, exc.__class__.__name__)
        return []


async def collect_snapshot(client: UniFiAccessClient) -> dict[str, Any]:
    users = await client.list_users(expand_access_policy=True)
    access_policies = await _optional_resource("access_policies", client.list_access_policies)
    user_groups = await _optional_resource("user_groups", client.list_user_groups)
    doors = await _optional_resource("doors", client.list_doors)
    door_groups = await _optional_resource("door_groups", client.list_door_groups)
    return {
        "agent_name": client.settings.unifi_agent_name,
        "source": client.settings.unifi_snapshot_source,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "users": users,
        "access_policies": access_policies,
        "user_groups": user_groups,
        "doors": doors,
        "door_groups": door_groups,
    }


async def post_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.entrypoint_api_base_url:
        raise RuntimeError("ENTRYPOINT_API_BASE_URL is required")
    if not settings.entrypoint_agent_token:
        raise RuntimeError("ENTRYPOINT_AGENT_TOKEN is required")

    attempts = max(1, settings.unifi_request_retries)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.unifi_request_timeout_seconds) as client:
                response = await client.post(
                    _endpoint(settings.entrypoint_api_base_url),
                    headers={
                        "Authorization": f"Bearer {settings.entrypoint_agent_token}",
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            logger.warning("Entry Point ingestion failed on attempt %s/%s: %s", attempt, attempts, exc.__class__.__name__)
            await asyncio.sleep(min(2 ** (attempt - 1), 5))
    raise last_error or RuntimeError("Entry Point ingestion failed")


async def run_once() -> dict[str, Any]:
    settings = get_settings()
    if not settings.unifi_access_token:
        raise RuntimeError("UNIFI_ACCESS_TOKEN is required")
    if not settings.unifi_access_verify_ssl:
        logger.warning("UNIFI_ACCESS_VERIFY_SSL=false; accepting the local console self-signed certificate by explicit configuration")

    client = UniFiAccessClient(settings=settings)
    payload = await collect_snapshot(client)
    logger.info(
        "Collected UniFi snapshot users=%s policies=%s groups=%s doors=%s door_groups=%s",
        len(payload["users"]),
        len(payload["access_policies"]),
        len(payload["user_groups"]),
        len(payload["doors"]),
        len(payload["door_groups"]),
    )
    result = await post_snapshot(payload)
    logger.info("Entry Point accepted UniFi snapshot status=%s", result.get("sync_run", {}).get("status"))
    return result


async def run_forever() -> None:
    settings = get_settings()
    interval = max(30, settings.sync_interval_seconds)
    while True:
        try:
            await run_once()
        except Exception as exc:
            logger.exception("Read-only UniFi sync cycle failed: %s", exc.__class__.__name__)
        await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only Entry Point UniFi Access LAN sync agent.")
    parser.add_argument("--once", action="store_true", help="Run one sync cycle and exit.")
    args = parser.parse_args()
    logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_forever())


if __name__ == "__main__":
    main()
